"""Reproducibility manifest: what code, configuration and environment produced a result."""

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = (
    "pydantic",
    "numpy",
    "gymnasium",
    "pettingzoo",
    "fastapi",
    "sqlalchemy",
    "alembic",
    "uvicorn",
)


def git_commit(root: Path = ROOT) -> str | None:
    """HEAD commit, suffixed "-dirty" when tracked files have uncommitted changes, so a result
    never claims a commit that does not contain the code that produced it."""

    def git(*args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", *args], capture_output=True, text=True, timeout=5, cwd=root, check=False
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    head = git("rev-parse", "HEAD")
    if not head:
        return None
    status = git("status", "--porcelain", "--untracked-files=no")
    return f"{head}-dirty" if status else head


def config_digest(payload: Any) -> str:
    """Stable SHA-256 of a JSON-serialisable configuration."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def packages() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def environment() -> dict[str, Any]:
    """Host description for benchmark context. No user, path or secret information."""
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "os": f"{platform.system()} {platform.release()}",
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "logical_cpus": os.cpu_count(),
        "packages": packages(),
    }


def manifest(kind: str, configuration: Any) -> dict[str, Any]:
    from backend import __version__ as backend_version

    return {
        "manifest_version": "1",
        "kind": kind,
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "software_version": backend_version,
        "configuration": configuration,
        "configuration_sha256": config_digest(configuration),
        "environment": environment(),
        "argv": [Path(sys.argv[0]).name, *sys.argv[1:]],
    }
