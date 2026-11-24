"""Authentication, account and machine-credential endpoints."""

from typing import Annotated

from fastapi import APIRouter, Body, Request, status
from sqlalchemy import select

from backend.api.dependencies import ContainerDep, PageDep, PrincipalDep
from backend.core.errors import Forbidden
from backend.core.permissions import GlobalRole
from backend.database import models as m
from backend.schemas import (
    LoginRequest,
    MachineTokenRequest,
    MachineTokenResponse,
    MembershipOut,
    MeResponse,
    Page,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserOut,
)
from backend.services import audit

router = APIRouter(tags=["auth"])


def _pair(pair: object) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,  # type: ignore[attr-defined]
        refresh_token=pair.refresh_token,  # type: ignore[attr-defined]
        access_expires_at=pair.access_expires_at,  # type: ignore[attr-defined]
        refresh_expires_at=pair.refresh_expires_at,  # type: ignore[attr-defined]
    )


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, services: ContainerDep) -> TokenResponse:
    client = request.client.host if request.client else "unknown"
    return _pair(services.auth.login(body.username, body.password, client))


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, services: ContainerDep) -> TokenResponse:
    return _pair(services.auth.refresh(body.refresh_token))


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshRequest, principal: PrincipalDep, services: ContainerDep) -> None:
    principal.require_human()
    services.auth.logout(body.refresh_token, principal)


@router.get("/auth/me", response_model=MeResponse)
def me(principal: PrincipalDep) -> MeResponse:
    return MeResponse(
        subject=principal.subject,
        kind=principal.kind,
        user_id=principal.user_id,
        global_role=principal.global_role,
        memberships=[MembershipOut(mission_id=mid, role=r) for mid, r in principal.memberships],
        machine_mission=principal.machine_mission,
    )


@router.post("/auth/machine-token", response_model=MachineTokenResponse)
def machine_token(body: MachineTokenRequest, services: ContainerDep) -> MachineTokenResponse:
    token, expires = services.auth.machine_token(body.credential_id, body.secret)
    return MachineTokenResponse(access_token=token, expires_at=expires)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED, tags=["users"])
def create_user(body: UserCreate, principal: PrincipalDep, services: ContainerDep) -> UserOut:
    if not principal.is_admin:
        raise Forbidden("administrator role required")
    with services.db.transaction() as session:
        user = services.auth.create_user(
            session, body.username, body.password, body.global_role, body.display_name
        )
        audit.record(
            session,
            principal,
            "user.create",
            resource_type="user",
            resource_id=user.id,
            details={"username": user.username, "global_role": user.global_role},
        )
        return UserOut.model_validate(user)


@router.get("/users", response_model=Page[UserOut], tags=["users"])
def list_users(principal: PrincipalDep, services: ContainerDep, page: PageDep) -> Page[UserOut]:
    if not principal.is_admin:
        raise Forbidden("administrator role required")
    from backend.services.access import paginate

    with services.db.read() as session:
        rows, total = paginate(
            session, select(m.User).order_by(m.User.username), page.limit, page.offset
        )
        return Page(
            items=[UserOut.model_validate(u) for u in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )


@router.post("/users/{user_id}/deactivate", response_model=UserOut, tags=["users"])
def deactivate_user(
    user_id: str,
    principal: PrincipalDep,
    services: ContainerDep,
    reason: Annotated[
        str, Body(embed=True, min_length=1, max_length=100)
    ] = "administrative action",
) -> UserOut:
    from uuid import UUID

    from backend.core.errors import NotFound

    if not principal.is_admin:
        raise Forbidden("administrator role required")
    with services.db.transaction() as session:
        user = session.get(m.User, UUID(user_id))
        if user is None:
            raise NotFound("user not found")
        if user.global_role == GlobalRole.ADMINISTRATOR and user.id == principal.user_id:
            raise Forbidden("administrators cannot deactivate themselves")
        user.is_active = False
        session.flush()
        audit.record(
            session,
            principal,
            "user.deactivate",
            resource_type="user",
            resource_id=user.id,
            details={"reason": reason},
        )
        return UserOut.model_validate(user)
