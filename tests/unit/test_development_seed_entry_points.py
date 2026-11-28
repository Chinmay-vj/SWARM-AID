"""Development entry points ask for a seed instead of falling back to the historical default."""

import sys
from pathlib import Path

import pytest

from simulation.core.configuration import load

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("argv", [["simulation", "--headless"]])
def test_simulator_cli_refuses_the_implicit_default(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from simulation.__main__ import main

    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        main()
    assert "pass --seed" in capsys.readouterr().err


def test_headless_run_requires_a_seed(capsys: pytest.CaptureFixture[str]) -> None:
    from orchestration.__main__ import main

    with pytest.raises(SystemExit):
        main(["run"])
    assert "--seed" in capsys.readouterr().err


def test_historical_defaults_are_preserved() -> None:
    assert load("flood_basic").seed == 42
    assert "seed" not in load("flood_basic").model_fields_set


def test_demo_scripts_and_form_name_no_retired_seed() -> None:
    for name in ("scripts/backend_demo.py", "scripts/system_demo.py"):
        text = (REPO / name).read_text(encoding="utf8")
        assert not any(f"seed={n}" in text or f'"seed": {n}' in text for n in range(42, 47)), name
    form = (REPO / "frontend/src/features/missions/MissionsPage.tsx").read_text(encoding="utf8")
    assert 'useState("42")' not in form and "default_seed" not in form
