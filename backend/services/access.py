"""Resource-level authorization helpers shared by every service."""

from typing import TypeVar
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from backend.core.errors import NotFound
from backend.core.permissions import Permission, Principal
from backend.database import models as m

Row = TypeVar("Row")


def mission_for(
    session: Session, principal: Principal, mission_id: UUID, permission: Permission
) -> m.Mission:
    """Load a mission the principal may access. Invisible missions report 404, not 403."""
    mission = session.get(m.Mission, mission_id)
    if (
        mission is None
        or not principal.can(Permission.MISSION_READ, mission_id)
        and not (principal.kind != "human" and principal.can(permission, mission_id))
    ):
        raise NotFound("mission not found")
    principal.require(permission, mission_id)
    return mission


def owned(
    session: Session,
    principal: Principal,
    model: type[Row],
    resource_id: UUID,
    permission: Permission = Permission.MISSION_READ,
) -> Row:
    """Load a mission-owned row and authorize against its mission (prevents BOLA)."""
    row = session.get(model, resource_id)
    mission_id = getattr(row, "mission_id", None)
    if row is None or mission_id is None or not principal.can(Permission.MISSION_READ, mission_id):
        raise NotFound(f"{getattr(model, '__tablename__', 'resource')} not found")
    principal.require(permission, mission_id)
    return row


def paginate(
    session: Session, query: Select[Row], limit: int, offset: int
) -> tuple[list[Row], int]:
    total = session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = list(session.scalars(query.limit(limit).offset(offset)))
    return rows, int(total)
