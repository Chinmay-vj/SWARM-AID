import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.append(str(Path(__file__).resolve().parent))
import seed_guard

seed_guard.install()
os.environ["PYTHONPATH"] = os.pathsep.join(
    filter(None, [str(Path(__file__).resolve().parent / "child_guard"),
                  os.environ.get("PYTHONPATH")]))


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    terminalreporter.write_line(
        f"seed isolation: {seed_guard.substitutions} in-process default-seed substitutions")


def pytest_configure(config: pytest.Config) -> None:
    """Give concurrent Windows test runs separate writable scratch directories."""
    if sys.platform != "win32" or config.getoption("basetemp") is not None:
        return
    root = config.rootpath / "runs" / "pytest"
    root.mkdir(parents=True, exist_ok=True)
    scratch = TemporaryDirectory(dir=root)
    config.add_cleanup(scratch.cleanup)
    config.option.basetemp = str(Path(scratch.name) / "tmp")


# These tests execute retired reserved seeds 43-45. They are kept, but never run by accident.
RESERVED_SEED_TESTS = ("test_field_scenarios.py::test_expansion_protection_and_storage",
                       "test_system_integration.py::test_identical_configuration_reproduces_identically")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.environ.get("SWARM_ALLOW_LEGACY_RESERVED_SEEDS") == "1":
        return
    for item in items:
        if item.nodeid.endswith(RESERVED_SEED_TESTS):
            item.add_marker(pytest.mark.skip(reason="executes retired reserved evaluation seeds"))


try:  # Backend fixtures need the optional backend extra; Phases 1-6 run without it.
    import fastapi  # noqa: F401
except ImportError:
    collect_ignore_glob = ["backend_api/*"]
else:
    from backend_support import (  # noqa: F401 - fixtures registered by import
        api,
        app,
        client,
        coordinator,
        db_path,
        settings,
        slow_settings,
        sqlite_dir,
        template_db,
    )
