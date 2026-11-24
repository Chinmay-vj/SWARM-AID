"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-24 15:31:07.791576
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from backend.database.session import APPEND_ONLY_POSTGRES, APPEND_ONLY_SQLITE

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SPATIAL_TABLES = ("observations", "incidents", "hazards", "agents")


def _postgres_extras() -> None:
    """PostGIS geometry for local grid coordinates (SRID 0, Cartesian) plus GiST indexes.

    The geometry is generated from x/y so the ORM stays portable. Genuine WGS84 coordinates
    would use a separate geography(Point, 4326) column; the simulator never produces them.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    for table in SPATIAL_TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN geom geometry(Point, 0) "
            "GENERATED ALWAYS AS (CASE WHEN x IS NULL OR y IS NULL THEN NULL "
            "ELSE ST_SetSRID(ST_MakePoint(x, y), 0) END) STORED"
        )
        op.execute(f"CREATE INDEX ix_{table}_geom ON {table} USING gist (geom)")


def _append_only_audit(dialect: str) -> None:
    if dialect == "postgresql":
        statements = APPEND_ONLY_POSTGRES
    elif dialect == "sqlite":
        statements = APPEND_ONLY_SQLITE
    else:
        raise RuntimeError(f"unsupported database dialect: {dialect}")
    for statement in statements:
        op.execute(statement)


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.String(length=100), nullable=True),
        sa.Column("mission_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column(
            "details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('success', 'failure', 'denied')", name=op.f("ck_audit_logs_outcome")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_logs_action"), ["action"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_audit_logs_mission_id_occurred_at"),
            ["mission_id", "occurred_at"],
            unique=False,
        )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("global_role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "global_role IN ('administrator', 'coordinator', 'operator', 'researcher', 'observer')",
            name=op.f("ck_users_global_role"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_table(
        "missions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("scenario_id", sa.String(length=100), nullable=False),
        sa.Column("sim_mission_id", sa.Uuid(), nullable=False),
        sa.Column(
            "config",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'running', 'paused', 'completed', 'stopped', 'failed')",
            name=op.f("ck_missions_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_missions_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_missions")),
    )
    with op.batch_alter_table("missions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_missions_status"), ["status"], unique=False)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_refresh_tokens_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    with op.batch_alter_table("refresh_tokens", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_refresh_tokens_family_id"), ["family_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_refresh_tokens_user_id"), ["user_id"], unique=False)

    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("agent_key", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("availability", sa.String(length=16), nullable=False),
        sa.Column("reported_state", sa.String(length=32), nullable=True),
        sa.Column("communication", sa.String(length=16), nullable=False),
        sa.Column("battery_fraction", sa.Double(), nullable=True),
        sa.Column(
            "degraded_sensors",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("last_report_ms", sa.Integer(), nullable=True),
        sa.Column("last_location_ms", sa.Integer(), nullable=True),
        sa.Column("x", sa.Double(), nullable=True),
        sa.Column("y", sa.Double(), nullable=True),
        sa.Column("crs", sa.String(length=64), nullable=True),
        sa.Column("uncertainty", sa.Double(), nullable=True),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["missions.id"], name=op.f("fk_agents_mission_id_missions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agents")),
        sa.UniqueConstraint("mission_id", "agent_key", name=op.f("uq_agents_mission_id_agent_key")),
        sa.UniqueConstraint("mission_id", "id", name=op.f("uq_agents_mission_id_id")),
    )
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_agents_mission_id"), ["mission_id"], unique=False)

    op.create_table(
        "domain_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("schema_version", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sim_time_ms", sa.Integer(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.String(length=100), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["missions.id"], name=op.f("fk_domain_events_mission_id_missions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_domain_events")),
        sa.UniqueConstraint(
            "mission_id", "sequence", name=op.f("uq_domain_events_mission_id_sequence")
        ),
    )
    with op.batch_alter_table("domain_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_domain_events_dispatched_at"), ["dispatched_at"], unique=False
        )

    op.create_table(
        "evidence_objects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("source_subject", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["missions.id"], name=op.f("fk_evidence_objects_mission_id_missions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_objects")),
        sa.UniqueConstraint("mission_id", "id", name=op.f("uq_evidence_objects_mission_id_id")),
        sa.UniqueConstraint(
            "mission_id", "sha256", name=op.f("uq_evidence_objects_mission_id_sha256")
        ),
    )
    with op.batch_alter_table("evidence_objects", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_evidence_objects_mission_id"), ["mission_id"], unique=False
        )

    op.create_table(
        "hazards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("first_reported_ms", sa.Integer(), nullable=False),
        sa.Column("last_reported_ms", sa.Integer(), nullable=False),
        sa.Column("report_count", sa.Integer(), nullable=False),
        sa.Column(
            "reporters",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("x", sa.Double(), nullable=True),
        sa.Column("y", sa.Double(), nullable=True),
        sa.Column("crs", sa.String(length=64), nullable=True),
        sa.Column("uncertainty", sa.Double(), nullable=True),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["missions.id"], name=op.f("fk_hazards_mission_id_missions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hazards")),
        sa.UniqueConstraint(
            "mission_id", "x", "y", "label", name=op.f("uq_hazards_mission_id_x_y_label")
        ),
    )
    with op.batch_alter_table("hazards", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_hazards_mission_id"), ["mission_id"], unique=False)

    op.create_table(
        "human_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=True),
        sa.Column("recommendation_id", sa.Uuid(), nullable=True),
        sa.Column("expected_revision", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("outcome_reason", sa.String(length=100), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("sim_time_ms", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('approval', 'incident_review', 'override', 'alert_acknowledgement')",
            name=op.f("ck_human_decisions_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('submitted', 'accepted', 'rejected', 'recorded', 'undeliverable')",
            name=op.f("ck_human_decisions_status"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name=op.f("fk_human_decisions_actor_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["missions.id"], name=op.f("fk_human_decisions_mission_id_missions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_human_decisions")),
        sa.UniqueConstraint(
            "mission_id",
            "actor_user_id",
            "idempotency_key",
            name=op.f("uq_human_decisions_mission_id_actor_user_id_idempotency_key"),
        ),
    )
    with op.batch_alter_table("human_decisions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_human_decisions_message_id"), ["message_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_human_decisions_mission_id_submitted_at"),
            ["mission_id", "submitted_at"],
            unique=False,
        )

    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("model2_id", sa.Uuid(), nullable=False),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("disposition", sa.String(length=32), nullable=False),
        sa.Column("priority_level", sa.String(length=32), nullable=True),
        sa.Column("priority_reason", sa.String(length=200), nullable=True),
        sa.Column("operator_priority", sa.String(length=200), nullable=True),
        sa.Column("opened_sim_ms", sa.Integer(), nullable=False),
        sa.Column("updated_sim_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("x", sa.Double(), nullable=True),
        sa.Column("y", sa.Double(), nullable=True),
        sa.Column("crs", sa.String(length=64), nullable=True),
        sa.Column("uncertainty", sa.Double(), nullable=True),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["missions.id"], name=op.f("fk_incidents_mission_id_missions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
        sa.UniqueConstraint("mission_id", "id", name=op.f("uq_incidents_mission_id_id")),
        sa.UniqueConstraint(
            "mission_id", "model2_id", name=op.f("uq_incidents_mission_id_model2_id")
        ),
    )
    with op.batch_alter_table("incidents", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_incidents_mission_id"), ["mission_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_incidents_mission_id_disposition"),
            ["mission_id", "disposition"],
            unique=False,
        )

    op.create_table(
        "machine_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("subject", sa.String(length=100), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=True),
        sa.Column("secret_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind = 'service' OR mission_id IS NOT NULL",
            name=op.f("ck_machine_credentials_agent_mission"),
        ),
        sa.CheckConstraint(
            "kind IN ('agent', 'service')", name=op.f("ck_machine_credentials_kind")
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["missions.id"], name=op.f("fk_machine_credentials_mission_id_missions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_machine_credentials")),
    )
    with op.batch_alter_table("machine_credentials", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_machine_credentials_mission_id"), ["mission_id"], unique=False
        )

    op.create_table(
        "mission_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("granted_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('coordinator', 'operator', 'researcher', 'observer')",
            name=op.f("ck_mission_memberships_role"),
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["missions.id"], name=op.f("fk_mission_memberships_mission_id_missions")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_mission_memberships_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mission_memberships")),
        sa.UniqueConstraint(
            "mission_id", "user_id", name=op.f("uq_mission_memberships_mission_id_user_id")
        ),
    )
    with op.batch_alter_table("mission_memberships", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_mission_memberships_mission_id"), ["mission_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_mission_memberships_user_id"), ["user_id"], unique=False
        )

    op.create_table(
        "mission_runtime",
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("last_event_sequence", sa.Integer(), nullable=False),
        sa.Column("current_run_id", sa.Uuid(), nullable=True),
        sa.Column("last_sim_ms", sa.Integer(), nullable=False),
        sa.Column("model2_state", sa.String(length=16), nullable=False),
        sa.Column("communication_state", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["missions.id"], name=op.f("fk_mission_runtime_mission_id_missions")
        ),
        sa.PrimaryKeyConstraint("mission_id", name=op.f("pk_mission_runtime")),
    )
    op.create_table(
        "mission_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("previous", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("sim_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["missions.id"],
            name=op.f("fk_mission_status_history_mission_id_missions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mission_status_history")),
    )
    with op.batch_alter_table("mission_status_history", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_mission_status_history_mission_id"), ["mission_id"], unique=False
        )

    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.String(length=100), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("agents", sa.Integer(), nullable=False),
        sa.Column(
            "config",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("software_version", sa.String(length=32), nullable=False),
        sa.Column("git_commit", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(length=64), nullable=True),
        sa.Column("final_sim_ms", sa.Integer(), nullable=False),
        sa.Column(
            "operational_metrics",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "research_metrics",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["missions.id"], name=op.f("fk_simulation_runs_mission_id_missions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_simulation_runs")),
    )
    with op.batch_alter_table("simulation_runs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_simulation_runs_mission_id"), ["mission_id"], unique=False
        )

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("model2_id", sa.Uuid(), nullable=False),
        sa.Column("member", sa.String(length=100), nullable=False),
        sa.Column("target_x", sa.Integer(), nullable=False),
        sa.Column("target_y", sa.Integer(), nullable=False),
        sa.Column("crs", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("coordinator_state", sa.String(length=32), nullable=False),
        sa.Column("reported_status", sa.String(length=32), nullable=True),
        sa.Column("reported_ms", sa.Integer(), nullable=True),
        sa.Column("created_ms", sa.Integer(), nullable=False),
        sa.Column("expires_ms", sa.Integer(), nullable=False),
        sa.Column("updated_ms", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["missions.id"], name=op.f("fk_tasks_mission_id_missions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
        sa.UniqueConstraint("mission_id", "id", name=op.f("uq_tasks_mission_id_id")),
        sa.UniqueConstraint("mission_id", "model2_id", name=op.f("uq_tasks_mission_id_model2_id")),
    )
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tasks_mission_id"), ["mission_id"], unique=False)

    op.create_table(
        "agent_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("report_type", sa.String(length=16), nullable=False),
        sa.Column("sim_time_ms", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=True),
        sa.Column("battery_fraction", sa.Double(), nullable=True),
        sa.Column(
            "details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("x", sa.Double(), nullable=True),
        sa.Column("y", sa.Double(), nullable=True),
        sa.Column("crs", sa.String(length=64), nullable=True),
        sa.Column("uncertainty", sa.Double(), nullable=True),
        sa.CheckConstraint(
            "report_type IN ('status', 'health', 'communication')",
            name=op.f("ck_agent_reports_type"),
        ),
        sa.ForeignKeyConstraint(
            ["mission_id", "agent_id"],
            ["agents.mission_id", "agents.id"],
            name=op.f("fk_agent_reports_mission_id_agent_id_agents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_reports")),
    )
    with op.batch_alter_table("agent_reports", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_agent_reports_agent_id_sim_time_ms"),
            ["agent_id", "sim_time_ms"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_agent_reports_mission_id"), ["mission_id"], unique=False
        )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("incident_revision", sa.Integer(), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("priority_reason", sa.String(length=200), nullable=False),
        sa.Column("review_state", sa.String(length=32), nullable=False),
        sa.Column(
            "supporting_evidence",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("sent_sim_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"], ["users.id"], name=op.f("fk_alerts_acknowledged_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["mission_id", "incident_id"],
            ["incidents.mission_id", "incidents.id"],
            name=op.f("fk_alerts_mission_id_incident_id_incidents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
        sa.UniqueConstraint("mission_id", "id", name=op.f("uq_alerts_mission_id_id")),
    )
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_alerts_mission_id_sent_sim_ms"),
            ["mission_id", "sent_sim_ms"],
            unique=False,
        )

    op.create_table(
        "incident_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column(
            "report_message_ids",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "uncertainties",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("confirmation_id", sa.Uuid(), nullable=True),
        sa.Column("priority_level", sa.String(length=32), nullable=True),
        sa.Column("priority_reason", sa.String(length=200), nullable=True),
        sa.Column("sim_time_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["mission_id", "incident_id"],
            ["incidents.mission_id", "incidents.id"],
            name=op.f("fk_incident_revisions_mission_id_incident_id_incidents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_revisions")),
        sa.UniqueConstraint(
            "incident_id", "revision", name=op.f("uq_incident_revisions_incident_id_revision")
        ),
    )
    with op.batch_alter_table("incident_revisions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_incident_revisions_mission_id"), ["mission_id"], unique=False
        )

    op.create_table(
        "incident_transitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("previous", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("reference", sa.Uuid(), nullable=False),
        sa.Column("sim_time_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["mission_id", "incident_id"],
            ["incidents.mission_id", "incidents.id"],
            name=op.f("fk_incident_transitions_mission_id_incident_id_incidents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_transitions")),
        sa.UniqueConstraint(
            "incident_id",
            "revision",
            "state",
            "reference",
            name=op.f("uq_incident_transitions_incident_id_revision_state_reference"),
        ),
    )
    with op.batch_alter_table("incident_transitions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_incident_transitions_mission_id"), ["mission_id"], unique=False
        )

    op.create_table(
        "mission_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("sim_time_ms", sa.Integer(), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('model2_checkpoint', 'model2_read_model', 'coordination')",
            name=op.f("ck_mission_snapshots_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["missions.id"], name=op.f("fk_mission_snapshots_mission_id_missions")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.id"],
            name=op.f("fk_mission_snapshots_run_id_simulation_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mission_snapshots")),
    )
    with op.batch_alter_table("mission_snapshots", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_mission_snapshots_mission_id_kind_sim_time_ms"),
            ["mission_id", "kind", "sim_time_ms"],
            unique=False,
        )

    op.create_table(
        "observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("reporter", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.Double(), nullable=False),
        sa.Column("observed_ms", sa.Integer(), nullable=False),
        sa.Column("received_ms", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("map_ref", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("x", sa.Double(), nullable=True),
        sa.Column("y", sa.Double(), nullable=True),
        sa.Column("crs", sa.String(length=64), nullable=True),
        sa.Column("uncertainty", sa.Double(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('environment', 'hazard', 'possible_human')", name=op.f("ck_observations_kind")
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name=op.f("ck_observations_confidence")
        ),
        sa.ForeignKeyConstraint(
            ["mission_id", "agent_id"],
            ["agents.mission_id", "agents.id"],
            name=op.f("fk_observations_mission_id_agent_id_agents"),
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["missions.id"], name=op.f("fk_observations_mission_id_missions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_observations")),
        sa.UniqueConstraint("mission_id", "id", name=op.f("uq_observations_mission_id_id")),
        sa.UniqueConstraint(
            "mission_id", "observation_id", name=op.f("uq_observations_mission_id_observation_id")
        ),
    )
    with op.batch_alter_table("observations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_observations_mission_id_kind"), ["mission_id", "kind"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_observations_mission_id_observed_ms"),
            ["mission_id", "observed_ms"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_observations_mission_id_x_y"), ["mission_id", "x", "y"], unique=False
        )

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("model2_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("incident_revision", sa.Integer(), nullable=False),
        sa.Column("request", sa.String(length=32), nullable=False),
        sa.Column(
            "evidence_ids",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "unknowns",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("expires_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_sim_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'confirmed', 'rejected', 'expired', 'superseded', 'revision_requested')",
            name=op.f("ck_recommendations_status"),
        ),
        sa.ForeignKeyConstraint(
            ["mission_id", "incident_id"],
            ["incidents.mission_id", "incidents.id"],
            name=op.f("fk_recommendations_mission_id_incident_id_incidents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendations")),
        sa.UniqueConstraint(
            "incident_id",
            "incident_revision",
            name=op.f("uq_recommendations_incident_id_incident_revision"),
        ),
        sa.UniqueConstraint("mission_id", "id", name=op.f("uq_recommendations_mission_id_id")),
        sa.UniqueConstraint(
            "mission_id", "model2_id", name=op.f("uq_recommendations_mission_id_model2_id")
        ),
    )
    with op.batch_alter_table("recommendations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_recommendations_mission_id_status"),
            ["mission_id", "status"],
            unique=False,
        )

    op.create_table(
        "task_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("sim_time_ms", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["mission_id", "task_id"],
            ["tasks.mission_id", "tasks.id"],
            name=op.f("fk_task_events_mission_id_task_id_tasks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_events")),
        sa.UniqueConstraint("task_id", "ordinal", name=op.f("uq_task_events_task_id_ordinal")),
    )
    with op.batch_alter_table("task_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_task_events_mission_id"), ["mission_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_task_events_task_id"), ["task_id"], unique=False)

    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("observation_pk", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("origin", sa.String(length=100), nullable=False),
        sa.Column("captured_ms", sa.Integer(), nullable=False),
        sa.Column("modality", sa.String(length=16), nullable=False),
        sa.Column("artifact_key", sa.String(length=100), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["mission_id", "object_id"],
            ["evidence_objects.mission_id", "evidence_objects.id"],
            name=op.f("fk_evidence_mission_id_object_id_evidence_objects"),
        ),
        sa.ForeignKeyConstraint(
            ["mission_id", "observation_pk"],
            ["observations.mission_id", "observations.id"],
            name=op.f("fk_evidence_mission_id_observation_pk_observations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence")),
        sa.UniqueConstraint(
            "observation_pk", "evidence_id", name=op.f("uq_evidence_observation_pk_evidence_id")
        ),
    )
    with op.batch_alter_table("evidence", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_evidence_mission_id_evidence_id"),
            ["mission_id", "evidence_id"],
            unique=False,
        )

    op.create_table(
        "incident_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("observation_pk", sa.Uuid(), nullable=False),
        sa.Column("first_revision", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "role IN ('supporting', 'conflicting')", name=op.f("ck_incident_evidence_role")
        ),
        sa.ForeignKeyConstraint(
            ["mission_id", "incident_id"],
            ["incidents.mission_id", "incidents.id"],
            name=op.f("fk_incident_evidence_mission_id_incident_id_incidents"),
        ),
        sa.ForeignKeyConstraint(
            ["mission_id", "observation_pk"],
            ["observations.mission_id", "observations.id"],
            name=op.f("fk_incident_evidence_mission_id_observation_pk_observations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_evidence")),
        sa.UniqueConstraint(
            "incident_id",
            "observation_pk",
            name=op.f("uq_incident_evidence_incident_id_observation_pk"),
        ),
    )
    with op.batch_alter_table("incident_evidence", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_incident_evidence_mission_id"), ["mission_id"], unique=False
        )

    op.create_table(
        "recommendation_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("recommendation_id", sa.Uuid(), nullable=False),
        sa.Column("previous", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("sim_time_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["mission_id", "recommendation_id"],
            ["recommendations.mission_id", "recommendations.id"],
            name=op.f(
                "fk_recommendation_status_history_mission_id_recommendation_id_recommendations"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendation_status_history")),
    )
    with op.batch_alter_table("recommendation_status_history", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_recommendation_status_history_mission_id"), ["mission_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_recommendation_status_history_recommendation_id"),
            ["recommendation_id"],
            unique=False,
        )

    dialect = op.get_bind().dialect.name
    _append_only_audit(dialect)
    if dialect == "postgresql":
        _postgres_extras()


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs")
        op.execute("DROP FUNCTION IF EXISTS swarm_audit_append_only()")
        for table in SPATIAL_TABLES:
            op.execute(f"DROP INDEX IF EXISTS ix_{table}_geom")
    else:
        op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update")
        op.execute("DROP TRIGGER IF EXISTS audit_logs_no_delete")
    with op.batch_alter_table("recommendation_status_history", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recommendation_status_history_recommendation_id"))
        batch_op.drop_index(batch_op.f("ix_recommendation_status_history_mission_id"))

    op.drop_table("recommendation_status_history")
    with op.batch_alter_table("incident_evidence", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_incident_evidence_mission_id"))

    op.drop_table("incident_evidence")
    with op.batch_alter_table("evidence", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_evidence_mission_id_evidence_id"))

    op.drop_table("evidence")
    with op.batch_alter_table("task_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_task_events_task_id"))
        batch_op.drop_index(batch_op.f("ix_task_events_mission_id"))

    op.drop_table("task_events")
    with op.batch_alter_table("recommendations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recommendations_mission_id_status"))

    op.drop_table("recommendations")
    with op.batch_alter_table("observations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_observations_mission_id_x_y"))
        batch_op.drop_index(batch_op.f("ix_observations_mission_id_observed_ms"))
        batch_op.drop_index(batch_op.f("ix_observations_mission_id_kind"))

    op.drop_table("observations")
    with op.batch_alter_table("mission_snapshots", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mission_snapshots_mission_id_kind_sim_time_ms"))

    op.drop_table("mission_snapshots")
    with op.batch_alter_table("incident_transitions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_incident_transitions_mission_id"))

    op.drop_table("incident_transitions")
    with op.batch_alter_table("incident_revisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_incident_revisions_mission_id"))

    op.drop_table("incident_revisions")
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_alerts_mission_id_sent_sim_ms"))

    op.drop_table("alerts")
    with op.batch_alter_table("agent_reports", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_agent_reports_mission_id"))
        batch_op.drop_index(batch_op.f("ix_agent_reports_agent_id_sim_time_ms"))

    op.drop_table("agent_reports")
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tasks_mission_id"))

    op.drop_table("tasks")
    with op.batch_alter_table("simulation_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_simulation_runs_mission_id"))

    op.drop_table("simulation_runs")
    with op.batch_alter_table("mission_status_history", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mission_status_history_mission_id"))

    op.drop_table("mission_status_history")
    op.drop_table("mission_runtime")
    with op.batch_alter_table("mission_memberships", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mission_memberships_user_id"))
        batch_op.drop_index(batch_op.f("ix_mission_memberships_mission_id"))

    op.drop_table("mission_memberships")
    with op.batch_alter_table("machine_credentials", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_machine_credentials_mission_id"))

    op.drop_table("machine_credentials")
    with op.batch_alter_table("incidents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_incidents_mission_id_disposition"))
        batch_op.drop_index(batch_op.f("ix_incidents_mission_id"))

    op.drop_table("incidents")
    with op.batch_alter_table("human_decisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_human_decisions_mission_id_submitted_at"))
        batch_op.drop_index(batch_op.f("ix_human_decisions_message_id"))

    op.drop_table("human_decisions")
    with op.batch_alter_table("hazards", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_hazards_mission_id"))

    op.drop_table("hazards")
    with op.batch_alter_table("evidence_objects", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_evidence_objects_mission_id"))

    op.drop_table("evidence_objects")
    with op.batch_alter_table("domain_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_domain_events_dispatched_at"))

    op.drop_table("domain_events")
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_agents_mission_id"))

    op.drop_table("agents")
    with op.batch_alter_table("refresh_tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_refresh_tokens_user_id"))
        batch_op.drop_index(batch_op.f("ix_refresh_tokens_family_id"))

    op.drop_table("refresh_tokens")
    with op.batch_alter_table("missions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_missions_status"))

    op.drop_table("missions")
    op.drop_table("users")
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_logs_mission_id_occurred_at"))
        batch_op.drop_index(batch_op.f("ix_audit_logs_action"))

    op.drop_table("audit_logs")
