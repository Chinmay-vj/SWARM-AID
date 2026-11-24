"""Engine creation, explicit transaction boundaries and schema readiness checks."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.config import BackendSettings
from backend.core.errors import Conflict, ServiceUnavailable


def build_engine(settings: BackendSettings) -> Engine:
    url = settings.database_url
    kwargs: dict[str, Any] = {"future": True}
    memory = ":memory:" in url or url in ("sqlite://", "sqlite+pysqlite://")
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if memory:
            kwargs["poolclass"] = StaticPool
        else:
            path = url.split("///", 1)[-1]
            if path:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
    else:
        kwargs |= {
            "pool_size": settings.database_pool_size,
            "max_overflow": settings.database_max_overflow,
            "pool_pre_ping": True,
        }
    engine = create_engine(url, **kwargs)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            if not memory:
                # WAL lets readers proceed during tick writes. synchronous=NORMAL survives a
                # process crash; the latest transactions can be lost on OS crash or power loss.
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    return engine


class Database:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.sessions = sessionmaker(engine, expire_on_commit=False, autoflush=False)
        self.transaction_failures = 0

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """One atomic unit of work. Commits on success, rolls back on any error."""
        session = self.sessions()
        try:
            yield session
            session.commit()
        except OperationalError as exc:
            session.rollback()
            self.transaction_failures += 1
            raise ServiceUnavailable("database unavailable", code="database_unavailable") from exc
        except SQLAlchemyError as exc:
            session.rollback()
            self.transaction_failures += 1
            from sqlalchemy.orm.exc import StaleDataError

            if isinstance(exc, StaleDataError):
                raise Conflict("record was modified concurrently", code="stale_version") from exc
            raise
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    @contextmanager
    def read(self) -> Iterator[Session]:
        session = self.sessions()
        try:
            yield session
        except OperationalError as exc:
            raise ServiceUnavailable("database unavailable", code="database_unavailable") from exc
        finally:
            # close() ends the read transaction without expiring loaded attributes, so
            # detached rows stay readable while response models are built.
            session.close()

    def ping(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False

    def migration_revision(self) -> str | None:
        try:
            with self.engine.connect() as connection:
                if not inspect(connection).has_table("alembic_version"):
                    return None
                row = connection.execute(text("SELECT version_num FROM alembic_version")).first()
                return str(row[0]) if row else None
        except SQLAlchemyError:
            return None

    def dispose(self) -> None:
        self.engine.dispose()


APPEND_ONLY_SQLITE = (
    """CREATE TRIGGER IF NOT EXISTS audit_logs_no_update BEFORE UPDATE ON audit_logs
    BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS audit_logs_no_delete BEFORE DELETE ON audit_logs
    BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END""",
)
APPEND_ONLY_POSTGRES = (
    """CREATE OR REPLACE FUNCTION swarm_audit_append_only() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'audit_logs is append-only'; END; $$ LANGUAGE plpgsql""",
    """CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION swarm_audit_append_only()""",
)
