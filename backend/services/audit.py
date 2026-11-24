"""Append-only audit records. Metadata is redacted before storage."""

from typing import Any, Literal
from uuid import UUID

from sqlalchemy.orm import Session

from backend.core.logging import redact, request_id_var
from backend.core.permissions import Principal
from backend.database.models import AuditLog

Outcome = Literal["success", "failure", "denied"]


def record(
    session: Session,
    principal: Principal | None,
    action: str,
    *,
    resource_type: str,
    resource_id: object = None,
    mission_id: UUID | None = None,
    outcome: Outcome = "success",
    details: dict[str, Any] | None = None,
    actor: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor=actor or (principal.subject if principal else "anonymous"),
        actor_type=principal.kind if principal else "anonymous",
        action=action,
        resource_type=resource_type,
        resource_id=None if resource_id is None else str(resource_id),
        mission_id=mission_id,
        request_id=request_id_var.get(),
        outcome=outcome,
        details=redact(details or {}),
    )
    session.add(entry)
    return entry
