import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Give concurrent Windows test runs separate writable scratch directories."""
    if sys.platform != "win32" or config.getoption("basetemp") is not None:
        return
    root = config.rootpath / "runs" / "pytest"
    root.mkdir(parents=True, exist_ok=True)
    scratch = TemporaryDirectory(dir=root)
    config.add_cleanup(scratch.cleanup)
    config.option.basetemp = str(Path(scratch.name) / "tmp")
