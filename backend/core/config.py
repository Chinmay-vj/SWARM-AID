"""Validated backend settings loaded from SWARM_* environment variables or a local .env."""

from functools import cached_property
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, PositiveInt, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend import __version__

Environment = Literal["development", "testing", "production"]


class BackendSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SWARM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_name: str = "SWARM-AID backend"
    version: str = __version__
    environment: Environment = "development"
    debug: bool = False
    host: str = "127.0.0.1"
    port: PositiveInt = 8000
    api_prefix: str = "/api/v1"

    database_url: str = "sqlite:///./runs/backend/swarm_aid.db"
    database_pool_size: PositiveInt = 5
    database_max_overflow: int = Field(default=5, ge=0)
    require_migrations: bool = True

    # Mandatory: there is deliberately no default signing secret.
    jwt_secret: SecretStr
    jwt_issuer: str = "swarm-aid-backend"
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_minutes: PositiveInt = 15
    refresh_token_minutes: PositiveInt = 60 * 12
    machine_token_minutes: PositiveInt = 60

    cors_origins: tuple[str, ...] = ()
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    page_size_default: PositiveInt = 50
    page_size_max: PositiveInt = 500
    max_request_bytes: PositiveInt = 1_000_000
    login_attempts_per_minute: PositiveInt = 10

    websocket_max_connections: PositiveInt = 100
    websocket_queue_size: PositiveInt = 256
    websocket_heartbeat_seconds: float = Field(default=15.0, gt=0)
    websocket_auth_timeout_seconds: float = Field(default=5.0, gt=0)

    max_concurrent_simulations: PositiveInt = 2
    simulation_tick_delay_ms: int = Field(default=100, ge=0)
    snapshot_every_ticks: PositiveInt = 10

    evidence_dir: Path = Path("runs/backend/evidence")
    evidence_max_bytes: PositiveInt = 5_000_000
    evidence_media_types: tuple[str, ...] = (
        "image/png",
        "image/jpeg",
        "application/json",
        "text/plain",
    )
    audit_retention_days: PositiveInt = 365
    # Read-only source of Phase 5/6 experiment comparison files for the research dashboard.
    experiments_dir: Path = Path("runs")

    @model_validator(mode="after")
    def check_security(self) -> Self:
        secret = self.jwt_secret.get_secret_value()
        if len(secret) < 32:
            raise ValueError("SWARM_JWT_SECRET must contain at least 32 characters")
        if self.environment == "production":
            if self.debug:
                raise ValueError("debug mode is not permitted in production")
            if self.database_url.startswith("sqlite"):
                raise ValueError("production requires PostgreSQL; SQLite is for development")
            if "*" in self.cors_origins:
                raise ValueError("wildcard CORS origins are not permitted in production")
        return self

    @cached_property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


def configured_database_url(env_file: Path = Path(".env")) -> str | None:
    """SWARM_DATABASE_URL with the same precedence as BackendSettings: the process environment
    first, then the local .env file. Used by Alembic so migrations target the database the
    server will open."""
    import os

    from dotenv import dotenv_values

    value = os.environ.get("SWARM_DATABASE_URL")
    if value:
        return value
    if env_file.is_file():
        return dotenv_values(env_file).get("SWARM_DATABASE_URL") or None
    return None


class ConfigurationError(RuntimeError):
    """Raised with field names and messages only; configured values are never echoed."""


def load_settings() -> BackendSettings:
    from pydantic import ValidationError

    try:
        return BackendSettings()  # values from SWARM_* environment variables and .env
    except ValidationError as exc:
        problems = "; ".join(
            (f"SWARM_{'_'.join(str(p) for p in e['loc']).upper()}: " if e["loc"] else "") + e["msg"]
            for e in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigurationError(f"invalid backend configuration: {problems}") from None
