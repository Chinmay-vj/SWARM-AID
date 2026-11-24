"""Human decisions, incident reviews, overrides and alert acknowledgements.

The backend checks identity, permission, version and deadline, records the decision durably,
then forwards it to Model 2 through the simulated operator channel. Model 2's independent
validator is authoritative: the decision stays "submitted" until Model 2 accepts or rejects it.
Approval never issues movement commands; Model 1 safety gates are unaffected.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import Conflict, NotFound
from backend.core.logging import request_id_var
from backend.core.permissions import Permission, Principal
from backend.database import models as m
from backend.database.session import Database
from backend.integrations.runtime import RuntimeManager
from backend.schemas import AlertOut, DecisionOut
from backend.services import audit
from backend.services.access import mission_for, owned
from communication.messages import HumanApproval, HumanIncidentReview, HumanOverride, Payload

DecisionKind = Literal["approval", "incident_review", "override"]


class OversightService:
    def __init__(self, db: Database, runtime: RuntimeManager) -> None:
        self.db = db
        self.runtime = runtime

    # ----- shared submission path ----------------------------------------------------------
    def _existing(
        self, session: Session, principal: Principal, mission_id: UUID, key: str | None, action: str
    ) -> m.HumanDecision | None:
        if key is None:
            return None
        found = session.scalar(
            select(m.HumanDecision).where(
                m.HumanDecision.mission_id == mission_id,
                m.HumanDecision.actor_user_id == principal.user_id,
                m.HumanDecision.idempotency_key == key,
            )
        )
        if found is not None and found.action != action:
            raise Conflict(
                "idempotency key reused for a different request", code="idempotency_conflict"
            )
        return found

    def _submit(
        self,
        principal: Principal,
        mission_id: UUID,
        *,
        kind: DecisionKind,
        action: str,
        reason: str,
        idempotency_key: str | None,
        validate: Callable[
            [Session, int], tuple[Payload, int, int | None, UUID | None, UUID | None, int | None]
        ],
    ) -> DecisionOut:
        """validate(session, sim_now) -> (payload, expires_ms, override_revision,
        incident_id, recommendation_id, expected_revision)."""
        principal.require_human()
        with self.db.read() as session:
            existing = self._existing(session, principal, mission_id, idempotency_key, action)
            if existing is not None:
                return DecisionOut.model_validate(existing)
        runtime = self.runtime.get(mission_id)
        ctx = runtime.ctx
        with ctx.lock:
            now = ctx.now_ms
            box = ctx.network.mail["operator"]
            message_id = uuid5(box.session, f"command/{box.sequence.get('command', 0)}")
            with self.db.transaction() as session:
                if self._existing(session, principal, mission_id, idempotency_key, action):
                    raise Conflict("duplicate request in progress", code="duplicate_request")
                payload, expires_ms, revision, incident_id, rec_id, expected = validate(
                    session, now
                )
                if expires_ms <= now:
                    raise Conflict("decision deadline has passed", code="expired")
                role = principal.mission_role(mission_id)
                decision = m.HumanDecision(
                    mission_id=mission_id,
                    kind=kind,
                    action=action,
                    incident_id=incident_id,
                    recommendation_id=rec_id,
                    expected_revision=expected,
                    actor_user_id=principal.user_id,
                    actor_role=role.value if role else "none",
                    reason=reason,
                    idempotency_key=idempotency_key,
                    message_id=message_id,
                    request_id=request_id_var.get(),
                    sim_time_ms=now,
                )
                session.add(decision)
                session.flush()
                audit.record(
                    session,
                    principal,
                    f"{kind}.{action}",
                    resource_type="recommendation"
                    if rec_id
                    else "incident"
                    if incident_id
                    else "mission",
                    resource_id=rec_id or incident_id or mission_id,
                    mission_id=mission_id,
                    details={
                        "decision_id": str(decision.id),
                        "expected_revision": expected,
                        "reason": reason,
                    },
                )
                out = DecisionOut.model_validate(decision)
            # Durable record committed; now hand the decision to Model 2.
            ctx.network.issue("operator", payload, "command", expires_ms, revision)
            sent = box.sent[-1].message_id
            if sent != message_id:  # pragma: no cover - guards the prediction invariant
                raise RuntimeError("operator channel message identity mismatch")
        return out

    # ----- recommendations -----------------------------------------------------------------
    def _pending_recommendation(
        self, session: Session, rec: m.Recommendation, version: int, now: int
    ) -> m.Incident:
        incident = session.get(m.Incident, rec.incident_id)
        assert incident is not None
        if rec.incident_revision != version or incident.current_revision != rec.incident_revision:
            raise Conflict(
                "recommendation version is outdated",
                code="stale_version",
                details={
                    "submitted_version": version,
                    "recommendation_version": rec.incident_revision,
                    "incident_revision": incident.current_revision,
                },
            )
        if rec.status != "pending":
            raise Conflict(f"recommendation is {rec.status}", code="recommendation_not_pending")
        if rec.expires_ms <= now:
            raise Conflict("recommendation has expired", code="expired")
        return incident

    def decide(
        self,
        principal: Principal,
        rec_id: UUID,
        decision: Literal["approve_review", "reject", "confirm_rescue_need"],
        version: int,
        reason: str,
        idempotency_key: str | None,
    ) -> DecisionOut:
        permission = (
            Permission.RECOMMENDATION_CONFIRM
            if decision == "confirm_rescue_need"
            else Permission.RECOMMENDATION_DECIDE
        )
        with self.db.read() as session:
            mission_id = owned(session, principal, m.Recommendation, rec_id, permission).mission_id

        def validate(session: Session, now: int) -> tuple[Payload, int, None, UUID, UUID, int]:
            rec = session.get(m.Recommendation, rec_id)
            assert rec is not None
            incident = self._pending_recommendation(session, rec, version, now)
            # Model 2 receives its own identifiers; backend IDs are mission-scoped.
            payload = HumanApproval(
                message_type="human_approval",
                recommendation_id=rec.model2_id,
                incident_id=incident.model2_id,
                revision=rec.incident_revision,
                decision=decision,
                reason=reason,
            )
            return payload, rec.expires_ms, None, rec.incident_id, rec.id, rec.incident_revision

        return self._submit(
            principal,
            mission_id,
            kind="approval",
            action=decision,
            reason=reason,
            idempotency_key=idempotency_key,
            validate=validate,
        )

    def request_revision(
        self, principal: Principal, rec_id: UUID, version: int, reason: str, key: str | None
    ) -> DecisionOut:
        with self.db.read() as session:
            rec = owned(
                session, principal, m.Recommendation, rec_id, Permission.RECOMMENDATION_DECIDE
            )
            mission_id, incident_id = rec.mission_id, rec.incident_id
        return self.incident_review(
            principal,
            incident_id,
            "correct",
            version,
            reason,
            key,
            mission_id=mission_id,
            rec_id=rec_id,
        )

    # ----- incidents -----------------------------------------------------------------------
    def acknowledge_incident(
        self, principal: Principal, incident_id: UUID, revision: int, reason: str, key: str | None
    ) -> DecisionOut:
        with self.db.read() as session:
            owned(session, principal, m.Incident, incident_id, Permission.INCIDENT_ACKNOWLEDGE)
            rec = session.scalar(
                select(m.Recommendation).where(
                    m.Recommendation.incident_id == incident_id,
                    m.Recommendation.status == "pending",
                )
            )
            if rec is None:
                raise Conflict(
                    "incident has no recommendation awaiting review", code="no_pending_review"
                )
            mission_id, rec_id = rec.mission_id, rec.id

        def validate(session: Session, now: int) -> tuple[Payload, int, None, UUID, UUID, int]:
            current = session.get(m.Recommendation, rec_id)
            assert current is not None
            incident = self._pending_recommendation(session, current, revision, now)
            payload = HumanApproval(
                message_type="human_approval",
                recommendation_id=current.model2_id,
                incident_id=incident.model2_id,
                revision=current.incident_revision,
                decision="approve_review",
                reason=reason,
            )
            return payload, current.expires_ms, None, incident_id, current.id, revision

        return self._submit(
            principal,
            mission_id,
            kind="approval",
            action="approve_review",
            reason=reason,
            idempotency_key=key,
            validate=validate,
        )

    def incident_review(
        self,
        principal: Principal,
        incident_id: UUID,
        action: Literal["correct", "prioritize", "resolve", "close"],
        revision: int,
        reason: str,
        key: str | None,
        *,
        mission_id: UUID | None = None,
        rec_id: UUID | None = None,
    ) -> DecisionOut:
        permission = {
            "correct": Permission.FEEDBACK_CORRECT,
            "prioritize": Permission.INCIDENT_REQUEST_REVIEW,
            "resolve": Permission.INCIDENT_RESOLUTION_REPORT,
            "close": Permission.INCIDENT_CLOSE,
        }[action]
        with self.db.read() as session:
            incident = owned(session, principal, m.Incident, incident_id, permission)
            if mission_id is not None and incident.mission_id != mission_id:
                raise NotFound("incident not found")
            mission_id = incident.mission_id
        runtime = self.runtime.get(mission_id)
        review_ms = runtime.ctx.command.settings.review_ms

        def validate(
            session: Session, now: int
        ) -> tuple[Payload, int, None, UUID, UUID | None, int]:
            current = session.get(m.Incident, incident_id)
            assert current is not None
            if current.current_revision != revision:
                raise Conflict(
                    "incident revision is outdated",
                    code="stale_version",
                    details={"submitted": revision, "current": current.current_revision},
                )
            if current.disposition == "closed":
                raise Conflict("incident is closed", code="incident_closed")
            if action == "close" and current.disposition != "resolution_reported":
                raise Conflict(
                    "closure requires a prior human resolution report", code="resolution_required"
                )
            payload = HumanIncidentReview(
                message_type="human_incident_review",
                incident_id=current.model2_id,
                revision=revision,
                action=action,
                reason=reason,
            )
            return payload, now + review_ms, None, incident_id, rec_id, revision

        return self._submit(
            principal,
            mission_id,
            kind="incident_review",
            action=action,
            reason=reason,
            idempotency_key=key,
            validate=validate,
        )

    # ----- mission override ----------------------------------------------------------------
    def override(
        self,
        principal: Principal,
        mission_id: UUID,
        action: Literal["pause", "resume", "end"],
        reason: str,
        key: str | None,
    ) -> DecisionOut:
        """Revision-bound HumanOverride to Model 2 coordination (assignment pause/resume/end).
        Simulation execution control is separate (mission lifecycle endpoints)."""
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_OVERRIDE)
        runtime = self.runtime.get(mission_id)
        review_ms = runtime.ctx.command.settings.review_ms

        def validate(session: Session, now: int) -> tuple[Payload, int, int, None, None, int]:
            revision = runtime.ctx.fleet.command_revision
            payload = HumanOverride(message_type="human_override", action=action, reason=reason)
            return payload, now + review_ms, revision, None, None, revision

        return self._submit(
            principal,
            mission_id,
            kind="override",
            action=action,
            reason=reason,
            idempotency_key=key,
            validate=validate,
        )

    # ----- alerts --------------------------------------------------------------------------
    def acknowledge_alert(self, principal: Principal, alert_id: UUID, reason: str) -> AlertOut:
        """Records that a human saw the alert. Does not change incident state."""
        principal.require_human()
        with self.db.transaction() as session:
            alert = owned(session, principal, m.Alert, alert_id, Permission.ALERT_ACKNOWLEDGE)
            if alert.acknowledged_at is None:
                alert.acknowledged_at = datetime.now(UTC)
                alert.acknowledged_by = principal.user_id
                role = principal.mission_role(alert.mission_id)
                session.add(
                    m.HumanDecision(
                        mission_id=alert.mission_id,
                        kind="alert_acknowledgement",
                        action="acknowledge",
                        incident_id=alert.incident_id,
                        expected_revision=alert.incident_revision,
                        actor_user_id=principal.user_id,
                        actor_role=role.value if role else "none",
                        reason=reason,
                        status="recorded",
                        request_id=request_id_var.get(),
                        resolved_at=alert.acknowledged_at,
                    )
                )
                audit.record(
                    session,
                    principal,
                    "alert.acknowledge",
                    resource_type="alert",
                    resource_id=alert_id,
                    mission_id=alert.mission_id,
                )
            session.flush()
            return AlertOut.model_validate(alert)
