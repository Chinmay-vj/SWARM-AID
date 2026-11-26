import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from agents.shared.domain import Recommendation
from evaluation.data.contracts import Registry
from evaluation.data.crisismmd import inspect, map_observed
from evaluation.data.humaid import passages, text_key
from evaluation.data.model2 import generate, manifest, read_rows, save_review, validate_release
from evaluation.data.model2_addendum import summarize
from evaluation.data.model2_collect import Episode, challenge, collect
from evaluation.data.model2_records import Features, Input, Target, relation
from evaluation.data.validation import validate


@pytest.fixture(scope="module")
def example() -> Input:
    rows, _ = collect(Episode(scenario="command_routine", seed=100, agents=2, split="train"), 4)
    return rows[0][0]


def test_controlled_cases_and_identity(example: Input) -> None:
    original = example.model_dump_json()
    for variant in ("repeat", "relay", "conflict", "stale", "spurious"):
        s, t = challenge(example, variant)
        assert s.parent_id == example.sample_id and s.split == example.split
        t.check(s)
        assert s.receipt.report.finding.observation == example.receipt.report.finding.observation
        if variant in ("repeat", "relay"):
            assert relation(s.receipt, s.context) == "duplicate"
        if variant == "conflict":
            assert t.relationship == "conflicting"
        if variant == "stale":
            assert s.age_ms >= 1500
    assert example.model_dump_json() == original


def test_asof_and_reserved_seeds(example: Input) -> None:
    with pytest.raises(ValueError, match="reserved seed"):
        Input.model_validate({**example.model_dump(), "seed": 42})
    future = example.receipt.model_copy(update={"received_ms": example.receipt.received_ms + 1})
    with pytest.raises(ValueError, match="future context"):
        Input.model_validate({**example.model_dump(), "context": [future]})
    with pytest.raises(ValidationError):
        Features.model_validate(
            {**Features.from_input(example).model_dump(), "truth_person_id": "p"}
        )
    assert "variant" not in Features.from_input(example).model_dump()


def test_governance_and_citations(example: Input) -> None:
    with pytest.raises(ValueError, match="provenance"):
        Target(sample_id=example.sample_id, provenance="human_reviewed").check(example)
    with pytest.raises(ValueError, match="attribution"):
        Target(
            sample_id=example.sample_id, provenance="rule_derived", supporting=(UUID(int=0),)
        ).check(example)


def test_recommendation_expiry_and_actual_corroboration() -> None:
    rows, _ = collect(Episode(scenario="flood_basic", seed=101, agents=3, split="train"), 40)
    assert any(t.relationship == "corroborating" for _, t in rows)
    s, t = next((s, t) for s, t in rows if t.recommendation is not None)
    assert t.recommendation and t.baseline_incident
    rec = t.recommendation
    for modified in (
        rec.model_copy(update={"expires_ms": s.receipt.received_ms}),
        rec.model_copy(update={"incident_revision": rec.incident_revision + 1}),
        rec.model_copy(update={"evidence_ids": (UUID(int=0),)}),
    ):
        with pytest.raises(ValueError):
            t.model_copy(update={"recommendation": modified}).check(s)
    with pytest.raises(ValidationError):
        Recommendation.model_validate({**rec.model_dump(), "request": "dispatch_drone"})


def test_generation_validation_and_review(tmp_path: Path) -> None:
    cfg = tmp_path / "plan.json"
    cfg.write_text(
        json.dumps(
            {
                "per_episode": 4,
                "episodes": [
                    {"scenario": "command_routine", "seed": 100, "agents": 2, "split": "train"}
                ],
            }
        )
    )
    a = generate(cfg, tmp_path, "a")
    b = generate(cfg, tmp_path, "b")
    for name in ("features.jsonl", "inputs.jsonl", "targets.jsonl", "evaluator.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes()
    assert validate_release(a) == {"train": 9}
    with pytest.raises(FileExistsError):
        generate(cfg, tmp_path, "a")
    rows = read_rows(a / "inputs.jsonl", Input)
    addendum = tmp_path / "addendum"
    addendum.mkdir()
    stats = summarize(a, addendum)
    assert sum(stats["primary"].values()) == len(rows)
    assert stats["eligible"]["false_alarm"] == 1
    forms = read_rows(addendum / "review-queue.jsonl", Target)
    assert {form.sample_id for form in forms} == {row.sample_id for row in rows}
    assert all(form.status == "pending" and form.assessment is None for form in forms)
    for name in ("native", "controlled"):
        for line in (addendum / f"{name}-index.jsonl").read_bytes().splitlines():
            link = json.loads(line)
            source = rows[link["input_line"] - 1]
            assert (source.variant == "native") == (name == "native")
            assert str(source.sample_id) == link["sample_id"]
    changed = rows[0].model_copy(update={"split": "test", "sample_id": UUID(int=3)})
    with pytest.raises(ValueError, match="cross-split"):
        validate(
            Registry.model_validate_json((a / "registry.json").read_bytes()),
            [manifest([*rows, changed], "a")],
            a,
        )
    review = tmp_path / "example-review.json"
    review.write_text(
        Target(
            sample_id=rows[0].sample_id,
            provenance="human_reviewed",
            reviewer="fixture-only",
            revision=1,
            status="ambiguous",
            uncertainty=("fixture-only",),
        ).model_dump_json()
    )
    assert save_review(a, review).is_file()
    with pytest.raises(FileExistsError):
        save_review(a, review)
    (a / "features.jsonl").write_text("invalid")
    with pytest.raises(ValueError, match="checksum"):
        validate_release(a)


def test_public_annotation_scope(tmp_path: Path) -> None:
    (tmp_path / "train.tsv").write_text(
        "event_name\ttweet_id\timage_id\timage\tlabel_text\ttweet_text\n"
        'fixture\t1\ta\tabsent.jpg\taffected_individuals\t"literal" quote\n'
    )
    audit = inspect(tmp_path)
    table = audit["tables"][0]
    assert table["pairs"] == 1 and table["missing_image_paths"] == 1
    assert table["mapping"] == {"affected_individuals": "public_affected_people_context"}
    assert map_observed("unmapped", {"unmapped"}) is None
    with pytest.raises(ValueError, match="unobserved"):
        map_observed("informative", set())


def test_public_benchmark_overlap(tmp_path: Path) -> None:
    task = tmp_path / "informative"
    task.mkdir()
    for split in ("train", "test"):
        name = f"{split}.jpg"
        (tmp_path / name).write_bytes(b"same fixture bytes")
        row = {
            "event_name": "fixture",
            "tweet_id": "post",
            "image_id": name,
            "image_path": name,
            "tweet_text": "fixture",
            "label": "informative",
        }
        (task / f"{split}.json").write_text(json.dumps([row]))
    audit = inspect(tmp_path)["benchmark"]
    overlap = audit["across_splits"]
    assert overlap["event"] == overlap["post"] == overlap["media_sha256"] == 1
    assert overlap["image"] == 0
    assert all(s["missing_images"] == 0 for s in audit["splits"])


def test_public_shared_wording() -> None:
    phrase = "one two three four five six seven eight nine ten eleven twelve"
    assert text_key("  A&amp;B  ") == text_key("a&b")
    assert passages(phrase) & passages("@fixture " + phrase + " new ending")
    assert not passages("too few words")
