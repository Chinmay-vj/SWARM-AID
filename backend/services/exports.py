"""Authorized JSON/CSV research exports with reproducibility metadata.

Operational exports contain only reported and decided information. The research export adds
evaluator-only ground-truth metrics and requires the EXPORT_RESEARCH permission. Exported
evaluator labels are never fed back to agents.
"""

import csv
import io
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import func, select

from backend import __version__
from backend.core.permissions import Permission, Principal
from backend.database import models as m
from backend.database.session import Database
from backend.services import audit
from backend.services.access import mission_for

Kind = Literal["operational", "research"]


class ExportService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def build(self, principal: Principal, mission_id: UUID, kind: Kind) -> dict[str, Any]:
        permission = (
            Permission.EXPORT_RESEARCH if kind == "research" else Permission.EXPORT_OPERATIONAL
        )
        with self.db.transaction() as session:
            mission = mission_for(session, principal, mission_id, permission)
            runs = list(
                session.scalars(
                    select(m.SimulationRun)
                    .where(m.SimulationRun.mission_id == mission_id)
                    .order_by(m.SimulationRun.started_at)
                )
            )

            def grouped(column: Any, model: Any, *where: Any) -> dict[str, int]:
                rows = session.execute(
                    select(column, func.count())
                    .where(model.mission_id == mission_id, *where)
                    .group_by(column)
                )
                return {str(k): int(cast(int, v)) for k, v in rows}

            agents = []
            for agent in session.scalars(select(m.Agent).where(m.Agent.mission_id == mission_id)):
                count = session.scalar(
                    select(func.count())
                    .select_from(m.Observation)
                    .where(m.Observation.agent_id == agent.id)
                )
                agents.append(
                    {
                        "agent_key": agent.agent_key,
                        "observations_reported": int(count or 0),
                        "last_report_ms": agent.last_report_ms,
                        "battery_fraction": agent.battery_fraction,
                        "availability": agent.availability,
                    }
                )
            decision_latency = [
                (d.resolved_at - d.submitted_at).total_seconds() * 1000
                for d in session.scalars(
                    select(m.HumanDecision).where(
                        m.HumanDecision.mission_id == mission_id,
                        m.HumanDecision.resolved_at.is_not(None),
                        m.HumanDecision.kind != "alert_acknowledgement",
                    )
                )
                if d.resolved_at is not None
            ]
            record: dict[str, Any] = {
                "export_kind": kind,
                "exported_at": datetime.now(UTC).isoformat(),
                "reproducibility": {
                    "mission_id": str(mission.id),
                    "scenario_id": mission.scenario_id,
                    "configuration": mission.config,
                    "seed": mission.config.get("seed"),
                    "agents": mission.config.get("agents"),
                    "coordination_policy": mission.config.get("coordination"),
                    "model2_mode": mission.config.get("command_mode"),
                    "backend_version": __version__,
                    "runs": [
                        {
                            "run_id": str(r.id),
                            "software_version": r.software_version,
                            "git_commit": r.git_commit,
                            "started_at": r.started_at.isoformat(),
                            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                            "model2_settings": r.config.get("model2"),
                        }
                        for r in runs
                    ],
                },
                "mission_summary": {"status": mission.status, "name": mission.name},
                "agent_performance": agents,
                "observation_statistics": {
                    "by_kind": grouped(m.Observation.kind, m.Observation),
                    "by_outcome": grouped(m.Observation.outcome, m.Observation),
                },
                "incident_metrics": {
                    "by_category": grouped(m.Incident.category, m.Incident),
                    "by_disposition": grouped(m.Incident.disposition, m.Incident),
                    "revisions": int(
                        session.scalar(
                            select(func.count())
                            .select_from(m.IncidentRevision)
                            .where(m.IncidentRevision.mission_id == mission_id)
                        )
                        or 0
                    ),
                },
                "recommendation_metrics": {
                    "by_status": grouped(m.Recommendation.status, m.Recommendation)
                },
                "human_decision_metrics": {
                    "by_status": grouped(m.HumanDecision.status, m.HumanDecision),
                    "resolution_latency_ms": decision_latency,
                },
                "communication_metrics": [
                    r.operational_metrics.get("communication_full") for r in runs
                ],
                "coordination_metrics": {
                    "tasks_by_state": grouped(m.Task.coordinator_state, m.Task),
                },
                "model2_counts": [r.operational_metrics.get("model2_counts") for r in runs],
            }
            if kind == "research":
                record["evaluator_ground_truth"] = {
                    "warning": "Simulator ground truth for evaluation only; never shown to agents.",
                    "runs": [r.research_metrics for r in runs],
                }
            audit.record(
                session,
                principal,
                f"export.{kind}",
                resource_type="mission",
                resource_id=mission_id,
                mission_id=mission_id,
            )
            return record

    @staticmethod
    def to_csv(record: dict[str, Any]) -> str:
        """Flatten the export into metric,key,value rows."""
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(("section", "key", "value"))

        def walk(prefix: str, value: Any) -> None:
            if isinstance(value, dict):
                for k, v in value.items():
                    walk(f"{prefix}.{k}" if prefix else str(k), v)
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    walk(f"{prefix}[{i}]", v)
            else:
                section, _, key = prefix.partition(".")
                writer.writerow((section, key, value))

        walk("", record)
        return out.getvalue()
