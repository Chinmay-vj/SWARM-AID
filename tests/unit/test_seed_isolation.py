"""Routine tests cannot exercise protected seeds. Uses a fake engine; no protected scenario runs."""

import re
import subprocess
import sys
from pathlib import Path

import pytest
import seed_guard

from simulation.core.configuration import load
from simulation.core.engine import Engine


class Fake:
    def __init__(self) -> None:
        self.seeds: list[int] = []

    def reset(self, seed: int) -> None:
        self.seeds.append(seed)


@pytest.mark.parametrize("seed", [900000, 900099, 43, 46])
def test_protected_and_retired_seeds_never_reach_the_engine(
    seed: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SWARM_ALLOW_LEGACY_RESERVED_SEEDS", raising=False)
    fake = Fake()
    with pytest.raises(RuntimeError, match="refused"):
        seed_guard.wrap(Fake.reset)(fake, seed)
    assert fake.seeds == []


def test_final_seeds_stay_refused_when_legacy_reproduction_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SWARM_ALLOW_LEGACY_RESERVED_SEEDS", "1")
    with pytest.raises(RuntimeError):
        seed_guard.isolate(900000)


def test_default_seed_is_assigned_a_development_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SWARM_ALLOW_LEGACY_RESERVED_SEEDS", raising=False)
    assert getattr(Engine.reset, "seed_guard", False)
    assert Engine(load("flood_basic")).seed == 12800


def test_child_processes_are_guarded() -> None:
    code = ("from simulation.core.engine import Engine; "
            "from simulation.core.configuration import load; "
            "print(Engine(load('flood_basic')).seed)")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert done.stdout.strip().splitlines()[-1] == "12800"


def test_connected_dashboard_specs_name_no_retired_or_protected_seed() -> None:
    """These specs drive the real engine outside pytest, where the seed guard does not reach."""
    specs = sorted((Path(__file__).resolve().parents[2] / "frontend/tests/e2e/connected").glob(
        "*.spec.ts"))
    found = [
        int(match)
        for spec in specs
        for match in re.findall(r'(?:seed:\s*|getByLabel\("Seed"\)\.fill\(")(\d+)',
                                spec.read_text(encoding="utf8"))
    ]
    assert specs and len(found) >= 5
    assert all(seed in range(12000, 13000) for seed in found), found
