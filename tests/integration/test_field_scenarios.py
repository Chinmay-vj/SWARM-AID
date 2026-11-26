import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluation.data.field_matrix import Matrix, guard
from evaluation.data.field_replay import replay
from evaluation.data.model2 import generate, read_rows, validate_release
from evaluation.data.model2_collect import Episode, LocalReport
from evaluation.data.model2_records import Features, Target
from simulation.core.configuration import ObservationWindow, load
from simulation.core.engine import Engine

MATRIX = Path("configs/datasets/field_matrix.json")


def test_families_and_replay() -> None:
    matrix = Matrix.model_validate_json(MATRIX.read_bytes())
    traces = set()
    for name in matrix.plans():
        config = load(name)
        first, replay = Engine(config), Engine(config)
        profile = config.field_profile
        assert profile is not None
        assert set(first.people) <= {(p.x, p.y) for p in profile.search_region}
        if name == "missing_person_field":
            assert len(first.people) == 1
        captured = []
        while first.reason == "running":
            assert first.views == replay.views
            captured.append(len(first.views["d0"].readings))
            first.step({})
            replay.step({})
        assert first.events == replay.events
        traces.add((tuple(first.events), tuple(captured)))
    assert len(traces) == 6


def test_sensor_window_and_uncertainty() -> None:
    config = load("wildfire_field")
    assert config.field_profile
    window = config.field_profile.windows[0]
    config = config.model_copy(
        update={
            "dropout": 0,
            "field_profile": config.field_profile.model_copy(update={"difficulty": "easy"}),
        }
    )
    engine = Engine(config)
    initial = {r.evidence.modality for r in engine.views["d0"].readings}
    assert "image" in initial
    assert "thermal" not in {r.evidence.modality for r in engine.views["d1"].readings}
    for _ in range(window.start):
        engine.step({})
    assert not set(window.disabled) & {r.evidence.modality for r in engine.views["d0"].readings}
    difficult = Engine(
        config.model_copy(
            update={
                "field_profile": config.field_profile.model_copy(update={"difficulty": "difficult"})
                if config.field_profile
                else None
            }
        )
    )
    assert difficult.mission_id != engine.mission_id
    with pytest.raises(ValidationError):
        ObservationWindow(start=2, stop=1, radius=1, condition="fog")


def test_expansion_protection_and_storage(tmp_path: Path) -> None:
    matrix = Matrix.model_validate_json(MATRIX.read_bytes())
    with pytest.raises(ValueError, match="reserved"):
        matrix.model_copy(update={"first_seed": 40}).plans()
    with pytest.raises(ValueError, match="budget"):
        guard(tmp_path, matrix, matrix.budget_bytes, 1)
    from evaluation.data.model2_collect import collect

    with pytest.raises(ValueError, match="reserved"):
        collect(Episode(scenario="flood_field", seed=43, agents=2, split="test"), 3)


def test_integrated_field_export(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "per_episode": 8,
                "episodes": [
                    {
                        "scenario": "missing_person_field",
                        "seed": 1901,
                        "agents": 2,
                        "difficulty": "easy",
                        "split": "train",
                    }
                ],
            }
        )
    )
    release = generate(plan, tmp_path, "test-field")
    assert validate_release(release)["train"] >= 8
    meta = json.loads((release / "release.json").read_bytes())["episodes"][0]
    source = read_rows(release / meta["model1_file"], LocalReport)
    assert source and all(row.readings for row in source)
    features = read_rows(release / "features.jsonl", Features)
    assert features and set(features[0].model_dump()) == {
        "sample_id",
        "age_ms",
        "receipt",
        "context",
    }
    assert all(
        key not in (release / "features.jsonl").read_text()
        for key in (
            "search_region",
            "people",
            "field_profile",
            "controlled_false_sighting",
            "event_trace",
        )
    )
    assert all(t.status == "pending" for t in read_rows(release / "targets.jsonl", Target))
    assert meta["event_trace"] and meta["providers"]["perception"] == "MockPerception"
    observed, references = replay(release, meta)
    assert len(observed) == len(source)
    assert all("visible_person_at_reported_cell" not in item for item in observed)
    assert all(item["source"] == "simulator_reference_at_observation" for item in references)
