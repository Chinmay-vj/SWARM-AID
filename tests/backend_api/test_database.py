"""Migrations, constraints, isolation, append-only audit, transactions and concurrency."""

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from backend_support import ROOT, make_settings
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError

from backend.core.config import BackendSettings
from backend.core.errors import Conflict
from backend.database import models as m
from backend.database.base import utcnow
from backend.database.session import Database, build_engine


def alembic_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["url"] = url
    return config


def test_migration_upgrade_downgrade_and_reupgrade(sqlite_dir: Path) -> None:
    url = f"sqlite:///{(sqlite_dir / f'{uuid4().hex}.db').as_posix()}"
    engine = create_engine(url)
    config = alembic_config(url)
    for step in ("upgrade", "downgrade", "upgrade"):
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            if step == "upgrade":
                command.upgrade(config, "head")
            else:
                command.downgrade(config, "base")
        tables = set(inspect(engine).get_table_names())
        if step == "downgrade":
            assert tables <= {"alembic_version"}
        else:
            assert {"missions", "incidents", "audit_logs", "domain_events"} <= tables
            assert len(tables) == 28  # 27 application tables + alembic_version
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0001"
        )
        triggers = {
            r[0]
            for r in connection.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'"))
        }
        assert triggers == {"audit_logs_no_update", "audit_logs_no_delete"}
    engine.dispose()


def test_migration_preserves_existing_rows_on_reupgrade(settings: BackendSettings) -> None:
    db = Database(build_engine(settings))
    with db.transaction() as session:
        session.add(
            m.User(username="keep", display_name="k", password_hash="x", global_role="observer")
        )
    config = alembic_config(settings.database_url)
    with db.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")  # already at head: no-op, no data loss
    with db.read() as session:
        assert session.query(m.User).filter_by(username="keep").count() == 1
    db.dispose()


@pytest.fixture
def db(settings: BackendSettings) -> Iterator[Database]:
    database = Database(build_engine(settings))
    yield database
    database.dispose()


def seed_mission(db: Database) -> tuple[m.User, m.Mission]:
    with db.transaction() as session:
        user = m.User(
            username=f"u{uuid4().hex[:8]}",
            display_name="u",
            password_hash="x",
            global_role="coordinator",
        )
        session.add(user)
        session.flush()
        mission = m.Mission(
            name="m",
            scenario_id="flood_basic",
            sim_mission_id=uuid4(),
            config={},
            created_by=user.id,
        )
        session.add(mission)
        session.flush()
        session.add(m.MissionRuntime(mission_id=mission.id))
    return user, mission


def test_foreign_keys_and_unique_constraints(db: Database) -> None:
    with pytest.raises(IntegrityError), db.transaction() as session:
        session.add(
            m.MissionMembership(
                mission_id=uuid4(), user_id=uuid4(), role="observer", granted_by="t"
            )
        )
    user, _mission = seed_mission(db)
    with pytest.raises(IntegrityError), db.transaction() as session:
        session.add(
            m.User(
                username=user.username,
                display_name="dup",
                password_hash="x",
                global_role="observer",
            )
        )
    with pytest.raises(IntegrityError), db.transaction() as session:
        session.add(
            m.Mission(
                name="bad",
                scenario_id="x",
                sim_mission_id=uuid4(),
                config={},
                created_by=user.id,
                status="exploded",
            )
        )


def test_composite_keys_block_cross_mission_evidence(db: Database) -> None:
    _, mission_a = seed_mission(db)
    _, mission_b = seed_mission(db)
    with db.transaction() as session:
        incident = m.Incident(
            id=uuid4(),
            mission_id=mission_a.id,
            model2_id=uuid4(),
            current_revision=1,
            category="possible_human",
            disposition="human_review_pending",
            opened_sim_ms=0,
            updated_sim_ms=0,
        )
        observation = m.Observation(
            mission_id=mission_b.id,
            observation_id=uuid4(),
            message_id=uuid4(),
            reporter="d0",
            kind="possible_human",
            confidence=0.5,
            observed_ms=0,
            received_ms=0,
            map_ref="x",
            outcome="admitted",
            source="simulation",
        )
        session.add_all([incident, observation])
    with pytest.raises(IntegrityError), db.transaction() as session:
        session.add(
            m.IncidentEvidence(
                mission_id=mission_a.id,
                incident_id=incident.id,
                observation_pk=observation.id,
                first_revision=1,
            )
        )


def test_audit_log_is_append_only(db: Database) -> None:
    with db.transaction() as session:
        entry = m.AuditLog(
            actor="t",
            actor_type="human",
            action="x",
            resource_type="r",
            request_id="r1",
            outcome="success",
        )
        session.add(entry)
    for statement in ("UPDATE audit_logs SET action = 'tampered'", "DELETE FROM audit_logs"):
        with pytest.raises(IntegrityError, match="append-only"), db.engine.begin() as connection:
            connection.execute(text(statement))
    with db.read() as session:
        assert session.get(m.AuditLog, entry.id) is not None


def test_transaction_rollback_and_optimistic_concurrency(db: Database) -> None:
    _, mission = seed_mission(db)
    with pytest.raises(RuntimeError), db.transaction() as session:
        row = session.get(m.Mission, mission.id)
        assert row is not None
        row.name = "half-written"
        raise RuntimeError("simulated failure mid-transaction")
    with db.read() as session:
        row = session.get(m.Mission, mission.id)
        assert row is not None and row.name == "m"
    first, second = db.sessions(), db.sessions()
    a, b = first.get(m.Mission, mission.id), second.get(m.Mission, mission.id)
    assert a is not None and b is not None
    a.name = "first writer"
    first.commit()
    b.name = "second writer"
    with pytest.raises(Exception) as excinfo:
        second.commit()
    assert type(excinfo.value).__name__ == "StaleDataError"
    second.rollback()
    with pytest.raises(Conflict), db.transaction() as session:
        stale = session.get(m.Mission, mission.id)
        assert stale is not None
        session.execute(
            text("UPDATE missions SET version = version + 1 WHERE id = :i"), {"i": mission.id.hex}
        )
        stale.name = "lost update"
    first.close()
    second.close()


def test_timestamps_are_utc_aware_and_naive_rejected(db: Database) -> None:
    _, mission = seed_mission(db)
    with db.read() as session:
        row = session.get(m.Mission, mission.id)
        assert row is not None and row.created_at.tzinfo is not None
        assert row.created_at.utcoffset().total_seconds() == 0  # type: ignore[union-attr]
    with pytest.raises(Exception, match="naive"), db.transaction() as session:
        session.add(
            m.AuditLog(
                actor="t",
                actor_type="human",
                action="x",
                resource_type="r",
                request_id="r",
                outcome="success",
                occurred_at=datetime(2026, 1, 1),
            )
        )
    assert utcnow().tzinfo is not None


def test_database_unavailable_maps_to_service_unavailable(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "missing" / "nope.db", tmp_path)
    db = Database(build_engine(settings))
    db.engine.dispose()
    broken = Database(create_engine("sqlite:///" + (tmp_path / "dir_as_db").as_posix()))
    (tmp_path / "dir_as_db").mkdir()
    from backend.core.errors import ServiceUnavailable

    with pytest.raises(ServiceUnavailable), broken.transaction() as session:
        session.execute(text("SELECT 1"))
    assert broken.ping() is False
    broken.dispose()
    _ = OperationalError


def test_migration_url_follows_backend_settings_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 8 regression: Alembic must migrate the database the server opens, including a
    SWARM_DATABASE_URL that is only set in .env."""
    from backend.core.config import configured_database_url

    env_file = tmp_path / ".env"
    monkeypatch.delenv("SWARM_DATABASE_URL", raising=False)
    assert configured_database_url(env_file) is None
    env_file.write_text("SWARM_DATABASE_URL=sqlite:///./from-dotenv.db\n", encoding="utf-8")
    assert configured_database_url(env_file) == "sqlite:///./from-dotenv.db"
    monkeypatch.setenv("SWARM_DATABASE_URL", "sqlite:///./from-environment.db")
    assert configured_database_url(env_file) == "sqlite:///./from-environment.db"
