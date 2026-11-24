"""Alembic environment. Resolves the URL from -x url=..., SWARM_DATABASE_URL (process
environment, then .env, matching the backend settings) or a SQLite default."""

from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

from backend.core.config import configured_database_url
from backend.database import models  # noqa: F401 - registers tables on Base.metadata
from backend.database.base import Base

config = context.config
DEFAULT_URL = "sqlite:///./runs/backend/swarm_aid.db"


def database_url() -> str:
    url = context.get_x_argument(as_dictionary=True).get("url") or configured_database_url()
    if not url:
        url = config.get_main_option("sqlalchemy.url") or DEFAULT_URL
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return url


def run_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=Base.metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is not None:
        context.configure(
            connection=connectable, target_metadata=Base.metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=Base.metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
