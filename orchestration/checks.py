"""Validate every configuration source before anything starts.

Each check reports ok, warning, error or skipped with a short detail. Configured values that
could be sensitive (secrets, database URLs) are never echoed; only field names, dialects and
lengths are reported.
"""

import importlib.util
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parents[1]
Status = Literal["ok", "warning", "error", "skipped"]
Profile = Literal["headless", "research", "connected", "development", "testing"]
BACKEND_PROFILES = {"connected", "development"}
SECRET_NAME = re.compile(r"SECRET|TOKEN|PASSWORD|PASSWD|PRIVATE|CREDENTIAL|API_?KEY", re.IGNORECASE)


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str


def _errors(exc: ValidationError) -> str:
    """Field locations and messages only, never input values."""
    return "; ".join(
        f"{'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}"
        for e in exc.errors(include_input=False, include_url=False)
    )[:400]


def _guard(name: str, fn: Callable[[], Check | list[Check]]) -> list[Check]:
    try:
        result = fn()
    except ValidationError as exc:
        return [Check(name, "error", _errors(exc))]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [Check(name, "error", f"{type(exc).__name__}: {exc}"[:400])]
    return result if isinstance(result, list) else [result]


def check_python() -> Check:
    version = sys.version_info[:2]
    if version in ((3, 11), (3, 12)):
        return Check("python", "ok", f"Python {version[0]}.{version[1]}")
    return Check("python", "error", f"Python {version[0]}.{version[1]}; 3.11 or 3.12 required")


def check_dependencies(profile: Profile) -> list[Check]:
    groups = {
        "core": ("pydantic",),
        "simulation extra": ("numpy", "gymnasium", "pettingzoo"),
        "backend extra": ("fastapi", "uvicorn", "sqlalchemy", "alembic", "jwt", "pwdlib"),
    }
    results = []
    for group, modules in groups.items():
        missing = [mod for mod in modules if importlib.util.find_spec(mod) is None]
        needed = group == "core" or (group == "backend extra" and profile in BACKEND_PROFILES)
        if not missing:
            results.append(Check(f"dependencies: {group}", "ok", "installed"))
        else:
            results.append(
                Check(
                    f"dependencies: {group}",
                    "error" if needed else "warning",
                    f'missing {", ".join(missing)}; pip install -e ".[dev,simulation,backend]"',
                )
            )
    return results


def check_research_settings() -> list[Check]:
    from configs.settings import load_settings
    from simulation.environments.base import REGISTRY

    settings = load_settings(ROOT / "configs" / "default.toml")
    checks = [
        Check("configs/default.toml", "ok", f"seed {settings.seed}, tick {settings.tick_ms} ms")
    ]
    if settings.scenario not in REGISTRY:
        checks.append(
            Check(
                "configs/default.toml scenario",
                "warning",
                f"'{settings.scenario}' is not a simulator disaster profile "
                f"({', '.join(sorted(REGISTRY))}); the file is a Phase 1 contract example and "
                "is not read by the simulator, backend or experiment runners",
            )
        )
    return checks


def check_agent_settings() -> list[Check]:
    from agents.command_agent.agent import Settings as CommandSettings
    from agents.drone_agent.components import Settings as Model1Settings

    model1 = Model1Settings.model_validate_json((ROOT / "configs" / "model1.json").read_bytes())
    model2 = CommandSettings.model_validate_json((ROOT / "configs" / "model2.json").read_bytes())
    checks = [
        Check(
            "configs/model1.json",
            "ok",
            f"perception={model1.perception}, reasoning={model1.reasoning}, "
            f"movement={model1.movement} (coordination runs enable movement)",
        ),
        Check("configs/model2.json", "ok", f"mode={model2.mode}"),
    ]
    if model2 != CommandSettings():
        checks.append(
            Check(
                "configs/model2.json defaults",
                "warning",
                "differs from Model 2 defaults; the backend and Phase 9 runner use defaults with "
                "only command_mode overridden, so this file applies to --command-config only",
            )
        )
    return checks


def check_scenarios() -> list[Check]:
    from backend.integrations.simulation_adapter import MissionConfig, available_scenarios

    results = []
    names = sorted(available_scenarios())
    for name in names:
        try:
            scenario = MissionConfig(scenario_id=name).validated()
        except (ValueError, ValidationError) as exc:
            results.append(Check(f"scenario {name}", "error", str(exc)[:300]))
            continue
        results.append(
            Check(
                f"scenario {name}",
                "ok",
                f"{scenario.disaster}, {scenario.width}x{scenario.height}, "
                f"{scenario.agents} agents, horizon {scenario.horizon}",
            )
        )
    if not names:
        results.append(Check("scenarios", "error", "no scenario fixtures found"))
    return results


def check_experiments() -> list[Check]:
    from evaluation.command_agent_experiments import Experiment as CommandExperiment
    from evaluation.experiment_runner import Experiment as CoordinationExperiment
    from orchestration.matrix import MatrixPlan

    results = []
    for path in sorted((ROOT / "configs" / "experiments").glob("*.json")):
        model = (
            MatrixPlan
            if path.stem.startswith("phase9")
            else CommandExperiment
            if path.stem.startswith("phase6")
            else CoordinationExperiment
        )

        def validate(path: Path = path, model: type[BaseModel] = model) -> Check:
            model.model_validate_json(path.read_bytes())
            return Check(f"experiment {path.name}", "ok", model.__module__)

        results += _guard(f"experiment {path.name}", validate)
    return results


def check_backend(profile: Profile) -> list[Check]:
    if importlib.util.find_spec("fastapi") is None:
        return [Check("backend settings", "skipped", "backend extra not installed")]
    from backend.core.config import ConfigurationError, load_settings

    required = profile in BACKEND_PROFILES
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        return [Check("backend settings", "error" if required else "skipped", str(exc)[:400])]
    dialect = settings.database_url.split(":", 1)[0]
    checks = [
        Check(
            "backend settings",
            "ok",
            f"environment={settings.environment}, database={dialect}, "
            f"bind={settings.host}:{settings.port}, secret length ok",
        )
    ]
    if settings.host not in ("127.0.0.1", "localhost", "::1"):
        checks.append(
            Check(
                "backend bind address",
                "warning",
                "not bound to localhost; development services should bind to 127.0.0.1",
            )
        )
    if settings.cors_origins:
        checks.append(
            Check(
                "backend CORS",
                "warning",
                "CORS origins configured; the dashboard proxy does not need CORS",
            )
        )
    checks.append(check_migration(settings))
    return checks


def check_migration(settings: object) -> Check:
    from backend.api.v1.system import HEAD_REVISION
    from backend.core.config import BackendSettings
    from backend.database.session import Database, build_engine

    assert isinstance(settings, BackendSettings)
    if settings.is_sqlite:
        path = settings.database_url.split("///", 1)[-1]
        if path and path != ":memory:" and not Path(path).exists():
            return Check(
                "database migration",
                "warning",
                "SQLite file not created yet; run: python -m alembic upgrade head",
            )
    db = Database(build_engine(settings))
    try:
        if not db.ping():
            return Check("database migration", "error", "database not reachable")
        revision = db.migration_revision()
    finally:
        db.dispose()
    if revision == HEAD_REVISION:
        return Check("database migration", "ok", f"at head {HEAD_REVISION}")
    return Check(
        "database migration",
        "error",
        f"revision {revision} != head {HEAD_REVISION}; run: python -m alembic upgrade head",
    )


def check_frontend(profile: Profile) -> list[Check]:
    frontend = ROOT / "frontend"
    if not (frontend / "package.json").is_file():
        return [Check("frontend", "error", "frontend/package.json missing")]
    package = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    checks = [Check("frontend package", "ok", f"{package.get('name')} {package.get('version')}")]
    if not (frontend / "node_modules").is_dir():
        checks.append(
            Check(
                "frontend dependencies",
                "error" if profile in BACKEND_PROFILES else "warning",
                "node_modules missing; run: npm ci (in frontend/)",
            )
        )
    for env_file in sorted(frontend.glob(".env*")):
        if env_file.name.endswith(".example"):
            continue
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            key = line.split("=", 1)[0].strip()
            if key.startswith("VITE_") and SECRET_NAME.search(key):
                checks.append(
                    Check(
                        f"frontend {env_file.name}",
                        "error",
                        f"{key} looks like a secret; VITE_* values are bundled into the browser",
                    )
                )
    return checks


def run_checks(profile: Profile = "development") -> list[Check]:
    results = [check_python(), *check_dependencies(profile)]
    for name, fn in (
        ("research settings", check_research_settings),
        ("agent settings", check_agent_settings),
        ("scenarios", check_scenarios),
        ("experiments", check_experiments),
    ):
        results += _guard(name, fn)
    if profile in BACKEND_PROFILES:
        results += _guard("backend", lambda: check_backend(profile))
    if profile in BACKEND_PROFILES:
        results += _guard("frontend", lambda: check_frontend(profile))
    return results
