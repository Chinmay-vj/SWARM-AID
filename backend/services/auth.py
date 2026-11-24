"""Human login with rotating refresh tokens, machine tokens and principal resolution."""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.config import BackendSettings
from backend.core.errors import Conflict, NotAuthenticated, RateLimited, Unprocessable
from backend.core.permissions import GlobalRole, MachineKind, MissionRole, Principal
from backend.core.security import (
    HUMAN_AUDIENCE,
    MACHINE_AUDIENCE,
    TokenService,
    fingerprint,
    hash_secret,
    new_secret,
    verify_secret,
)
from backend.database.models import MachineCredential, MissionMembership, RefreshToken, User
from backend.database.session import Database
from backend.services import audit

USERNAME_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789._-")


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime


class LoginRateLimiter:
    """In-process sliding window. Single-process only; documented as a limitation."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self.lock:
            window = self.hits[key]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= self.per_minute:
                raise RateLimited("too many attempts; retry later")
            window.append(now)


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise Unprocessable("password must contain at least 12 characters", code="weak_password")


def normalize_username(username: str) -> str:
    name = username.strip().lower()
    if not 3 <= len(name) <= 64 or not set(name) <= USERNAME_CHARS:
        raise Unprocessable("username must be 3-64 characters of a-z, 0-9, '.', '_' or '-'")
    return name


class AuthService:
    def __init__(self, db: Database, settings: BackendSettings) -> None:
        self.db = db
        self.settings = settings
        self.tokens = TokenService(settings)
        self.limiter = LoginRateLimiter(settings.login_attempts_per_minute)
        self.failures = 0

    # ----- accounts -------------------------------------------------------------------------
    def create_user(
        self,
        session: Session,
        username: str,
        password: str,
        role: GlobalRole,
        display_name: str | None = None,
    ) -> User:
        validate_password(password)
        name = normalize_username(username)
        if session.scalar(select(User.id).where(User.username == name)):
            raise Conflict("username already exists", code="duplicate_username")
        user = User(
            username=name,
            display_name=display_name or name,
            password_hash=hash_secret(password),
            global_role=role.value,
        )
        session.add(user)
        try:
            session.flush()
        except IntegrityError as exc:
            raise Conflict("username already exists", code="duplicate_username") from exc
        return user

    # ----- human tokens ---------------------------------------------------------------------
    def _issue_pair(self, session: Session, user: User, family: UUID) -> TokenPair:
        access, access_claims = self.tokens.issue(
            str(user.id),
            HUMAN_AUDIENCE,
            "access",
            timedelta(minutes=self.settings.access_token_minutes),
        )
        jti = uuid4()
        refresh, refresh_claims = self.tokens.issue(
            str(user.id),
            HUMAN_AUDIENCE,
            "refresh",
            timedelta(minutes=self.settings.refresh_token_minutes),
            token_id=jti,
            extra={"fam": str(family)},
        )
        session.add(
            RefreshToken(
                id=jti,
                user_id=user.id,
                family_id=family,
                token_hash=fingerprint(refresh),
                expires_at=refresh_claims.expires_at,
            )
        )
        return TokenPair(access, refresh, access_claims.expires_at, refresh_claims.expires_at)

    def login(self, username: str, password: str, client: str) -> TokenPair:
        name = username.strip().lower()
        self.limiter.check(f"{client}/{name}")
        with self.db.transaction() as session:
            user = session.scalar(select(User).where(User.username == name))
            ok = verify_secret(password, user.password_hash if user else None)
            if not ok or user is None or not user.is_active:
                self.failures += 1
                audit.record(
                    session,
                    None,
                    "auth.login",
                    resource_type="user",
                    outcome="failure",
                    actor=name[:64] or "anonymous",
                    details={"reason": "invalid credentials or inactive account"},
                )
                failed = True
            else:
                failed = False
                pair = self._issue_pair(session, user, uuid4())
                audit.record(
                    session,
                    None,
                    "auth.login",
                    resource_type="user",
                    resource_id=user.id,
                    actor=user.username,
                )
        if failed:
            raise NotAuthenticated("invalid username or password", code="invalid_credentials")
        return pair

    def refresh(self, token: str) -> TokenPair:
        claims = self.tokens.verify(token, HUMAN_AUDIENCE, "refresh")
        reused = False
        with self.db.transaction() as session:
            stored = session.get(RefreshToken, claims.token_id)
            now = datetime.now(UTC)
            if stored is None or stored.token_hash != fingerprint(token):
                raise NotAuthenticated("invalid refresh token", code="invalid_token")
            if stored.revoked_at is not None:
                # Reuse of a rotated token: revoke the whole family (possible theft).
                session.execute(
                    update(RefreshToken)
                    .where(RefreshToken.family_id == stored.family_id)
                    .where(RefreshToken.revoked_at.is_(None))
                    .values(revoked_at=now)
                )
                audit.record(
                    session,
                    None,
                    "auth.refresh_reuse",
                    resource_type="user",
                    resource_id=stored.user_id,
                    outcome="denied",
                    actor=str(stored.user_id),
                )
                reused = True
            else:
                user = session.get(User, stored.user_id)
                if user is None or not user.is_active or stored.expires_at <= now:
                    raise NotAuthenticated("refresh token no longer valid", code="invalid_token")
                pair = self._issue_pair(session, user, stored.family_id)
                stored.revoked_at = now
                stored.replaced_by = self.tokens.verify(
                    pair.refresh_token, HUMAN_AUDIENCE, "refresh"
                ).token_id
        if reused:
            raise NotAuthenticated("refresh token reuse detected", code="token_reused")
        return pair

    def logout(self, token: str, principal: Principal) -> None:
        claims = self.tokens.verify(token, HUMAN_AUDIENCE, "refresh")
        with self.db.transaction() as session:
            stored = session.get(RefreshToken, claims.token_id)
            if stored is None or str(stored.user_id) != str(principal.user_id):
                raise NotAuthenticated("invalid refresh token", code="invalid_token")
            session.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == stored.family_id)
                .where(RefreshToken.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )
            audit.record(
                session, principal, "auth.logout", resource_type="user", resource_id=stored.user_id
            )

    # ----- machine credentials --------------------------------------------------------------
    def create_machine_credential(
        self, session: Session, kind: MachineKind, subject: str, mission_id: UUID | None
    ) -> tuple[MachineCredential, str]:
        secret = new_secret()
        credential = MachineCredential(
            kind=kind.value, subject=subject, mission_id=mission_id, secret_hash=hash_secret(secret)
        )
        session.add(credential)
        session.flush()
        return credential, secret

    def machine_token(self, credential_id: UUID, secret: str) -> tuple[str, datetime]:
        with self.db.transaction() as session:
            credential = session.get(MachineCredential, credential_id)
            ok = verify_secret(secret, credential.secret_hash if credential else None)
            if not ok or credential is None or not credential.is_active:
                self.failures += 1
                audit.record(
                    session,
                    None,
                    "auth.machine_token",
                    resource_type="machine_credential",
                    resource_id=credential_id,
                    outcome="failure",
                )
                failed = True
            else:
                failed = False
                credential.last_used_at = datetime.now(UTC)
                token, claims = self.tokens.issue(
                    str(credential.id),
                    MACHINE_AUDIENCE,
                    "access",
                    timedelta(minutes=self.settings.machine_token_minutes),
                )
        if failed:
            raise NotAuthenticated("invalid machine credential", code="invalid_credentials")
        return token, claims.expires_at

    # ----- request principal ----------------------------------------------------------------
    def principal_for_human(self, session: Session, token: str) -> Principal:
        claims = self.tokens.verify(token, HUMAN_AUDIENCE, "access")
        try:
            user_id = UUID(claims.subject)
        except ValueError as exc:
            raise NotAuthenticated("invalid token", code="invalid_token") from exc
        user = session.get(User, user_id)
        if user is None or not user.is_active:
            raise NotAuthenticated("account disabled or missing", code="account_inactive")
        memberships = session.execute(
            select(MissionMembership.mission_id, MissionMembership.role).where(
                MissionMembership.user_id == user.id
            )
        ).all()
        return Principal(
            subject=user.username,
            kind="human",
            user_id=user.id,
            global_role=GlobalRole(user.global_role),
            memberships=tuple((m, MissionRole(r)) for m, r in memberships),
        )

    def principal_for_machine(self, session: Session, token: str) -> Principal:
        claims = self.tokens.verify(token, MACHINE_AUDIENCE, "access")
        try:
            credential_id = UUID(claims.subject)
        except ValueError as exc:
            raise NotAuthenticated("invalid token", code="invalid_token") from exc
        credential = session.get(MachineCredential, credential_id)
        if credential is None or not credential.is_active:
            raise NotAuthenticated("credential revoked or missing", code="credential_revoked")
        return Principal(
            subject=credential.subject,
            kind=credential.kind,
            machine_mission=credential.mission_id,
            credential_id=credential.id,
        )

    def resolve(self, session: Session, token: str) -> Principal:
        """Try the human audience first, then the machine audience."""
        try:
            return self.principal_for_human(session, token)
        except NotAuthenticated as human_error:
            if human_error.code == "token_expired":
                raise
            try:
                return self.principal_for_machine(session, token)
            except NotAuthenticated as machine_error:
                if machine_error.code in ("credential_revoked", "token_expired"):
                    raise
                raise human_error from None
