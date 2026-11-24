"""Password hashing and signed token handling.

Human and machine tokens use different audiences so neither can be replayed as the other.
Roles are never read from tokens; they are loaded from the database on every request.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from backend.core.config import BackendSettings
from backend.core.errors import NotAuthenticated

HUMAN_AUDIENCE = "swarm-aid:human"
MACHINE_AUDIENCE = "swarm-aid:machine"
Purpose = Literal["access", "refresh"]

_hasher = PasswordHash((Argon2Hasher(),))
# Verifying against a fixed hash keeps the failure path's timing close to the success path.
_DUMMY_HASH = _hasher.hash("swarm-aid-dummy-password")


def hash_secret(secret: str) -> str:
    """Argon2id hash for human passwords and machine credential secrets."""
    return _hasher.hash(secret)


def verify_secret(secret: str, encoded: str | None) -> bool:
    if encoded is None:
        _hasher.verify(secret, _DUMMY_HASH)
        return False
    try:
        return _hasher.verify(secret, encoded)
    except Exception:  # noqa: BLE001 - malformed stored hash must not authenticate
        return False


def fingerprint(token: str) -> str:
    """Non-reversible digest used to store refresh-token references."""
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def new_secret() -> str:
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class TokenClaims:
    subject: str
    audience: str
    purpose: Purpose
    token_id: UUID
    expires_at: datetime
    extra: dict[str, Any]


class TokenService:
    def __init__(self, settings: BackendSettings) -> None:
        self.settings = settings
        self._key = settings.jwt_secret.get_secret_value()

    def issue(
        self,
        subject: str,
        audience: str,
        purpose: Purpose,
        lifetime: timedelta,
        *,
        token_id: UUID | None = None,
        extra: dict[str, Any] | None = None,
    ) -> tuple[str, TokenClaims]:
        now = datetime.now(UTC)
        jti = token_id or uuid4()
        claims = TokenClaims(subject, audience, purpose, jti, now + lifetime, dict(extra or {}))
        payload = {
            **claims.extra,
            "iss": self.settings.jwt_issuer,
            "aud": audience,
            "sub": subject,
            "pur": purpose,
            "jti": str(jti),
            "iat": now,
            "nbf": now,
            "exp": claims.expires_at,
        }
        return jwt.encode(payload, self._key, algorithm=self.settings.jwt_algorithm), claims

    def verify(self, token: str, audience: str, purpose: Purpose) -> TokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._key,
                algorithms=[self.settings.jwt_algorithm],
                audience=audience,
                issuer=self.settings.jwt_issuer,
                options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "jti", "pur"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise NotAuthenticated("token expired", code="token_expired") from exc
        except jwt.PyJWTError as exc:
            raise NotAuthenticated("invalid token", code="invalid_token") from exc
        if payload.get("pur") != purpose:
            raise NotAuthenticated("token purpose mismatch", code="invalid_token")
        try:
            jti = UUID(str(payload["jti"]))
        except ValueError as exc:
            raise NotAuthenticated("invalid token", code="invalid_token") from exc
        reserved = {"iss", "aud", "sub", "pur", "jti", "iat", "nbf", "exp"}
        return TokenClaims(
            subject=str(payload["sub"]),
            audience=audience,
            purpose=purpose,
            token_id=jti,
            expires_at=datetime.fromtimestamp(int(payload["exp"]), UTC),
            extra={k: v for k, v in payload.items() if k not in reserved},
        )
