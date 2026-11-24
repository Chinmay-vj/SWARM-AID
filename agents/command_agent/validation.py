"""Independent authorization for synthetic operator review."""

from agents.shared.domain import Category
from communication.messages import HumanApproval, IncidentUpdate


def validate_decision(
    principal: str,
    proposal: HumanApproval,
    current: IncidentUpdate | None,
    now: int,
    already_decided: bool,
) -> str:
    if principal != "operator":
        return "unauthorized"
    if not current or not current.recommendation:
        return "no_active_recommendation"
    rec = current.recommendation
    if (
        rec.recommendation_id != proposal.recommendation_id
        or current.incident.revision != proposal.revision
    ):
        return "revision_mismatch"
    if now >= rec.expires_ms:
        return "expired"
    if already_decided:
        return "already_decided"
    if proposal.decision == "confirm_rescue_need" and current.incident.category == Category.HAZARD:
        return "human_sighting_required"
    return "approved"
