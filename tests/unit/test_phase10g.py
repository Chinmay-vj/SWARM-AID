import csv
import json
import wave
import zipfile
from pathlib import Path
from uuid import UUID

import pytest

from evaluation.data.alert_audit import trace
from evaluation.data.crisis_decode import run as decode_crisis
from evaluation.data.field_review import agreement
from evaluation.data.model2 import digest
from evaluation.data.phase10g import process, records
from evaluation.data.phase10g_quality import near_pairs
from evaluation.data.preprocessing import (
    audio,
    batches,
    brightness,
    extract_zip,
    fit,
    group_split,
    image,
    letterbox,
    normalized_text,
    sensor_rows,
)
from evaluation.data.public_preprocessing import coco, esc
from evaluation.data.review_loaders import asset, native_batches, paired, public_batches
from evaluation.data.temporal_partitions import chronological
from evaluation.data.visual_quality import inspect_one
from simulation.core.configuration import load


def test_archive_and_storage(tmp_path: Path) -> None:
    path = tmp_path / "source.zip"
    for name in ("../file", "C:/elsewhere", "CON", "sub/file:stream", "ok."):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(name, "sample")
        with pytest.raises(ValueError):
            extract_zip(path, tmp_path / "out", 20, 0)
        assert not (tmp_path / "out").exists()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("sub/file", "abc")
    with pytest.raises(ValueError):
        extract_zip(path, tmp_path / "out", 2, 0)
    extract_zip(path, tmp_path / "out", 3, 0)
    assert (tmp_path / "out/sub/file").read_bytes() == b"abc"
    with pytest.raises(ValueError):
        asset(tmp_path, "../raw")


def test_images_and_masks(tmp_path: Path) -> None:
    pil = pytest.importorskip("PIL.Image")
    rgb = pil.new("RGB", (4, 2))
    mask = pil.new("L", (4, 2), 7)
    thermal = pil.new("I;16", (4, 2), 1025)
    thermal.save(tmp_path / "thermal.png")
    rgb.save(tmp_path / "rgb.png")
    assert image(tmp_path / "thermal.png").getpixel((0, 0)) == 1025
    pair = paired(tmp_path, "rgb.png", "thermal.png", "pair-1", "verified fixture")
    assert pair["thermal"].getpixel((1, 1)) == 1025
    with pytest.raises(ValueError):
        paired(tmp_path, "rgb.png", "thermal.png", "pair-1", "")
    out, boxes, labels = letterbox(rgb, (8, 8), [(1, 0, 2, 2)], mask, 255)
    assert out.size == (8, 8) and boxes == [(2, 2, 4, 4)]
    assert {v for _, v in labels.getcolors()} == {7, 255}
    with pytest.raises(ValueError):
        letterbox(rgb, (8, 8), [(3, 1, 2, 2)])
    with pytest.raises(ValueError):
        brightness(rgb, 1.1, "validation", True, 100)
    with pytest.raises(ValueError):
        brightness(thermal, 1.1, "train", True, 100)


def test_coco_orphan_and_box(tmp_path: Path) -> None:
    folder = tmp_path / "train"
    folder.mkdir()
    (folder / "sample.jpg").touch()
    (folder / "_annotations.coco.json").write_text(
        json.dumps(
            {
                "images": [{"file_name": "sample.jpg", "id": 1, "width": 5, "height": 5}],
                "categories": [{"id": 1, "name": "Person"}],
                "annotations": [
                    {"id": 1, "image_id": 1, "bbox": [4, 4, 2, 2], "category_id": 1},
                    {"id": 2, "image_id": 2, "bbox": [0, 0, 1, 1], "category_id": 1},
                ],
            }
        )
    )
    assert all(row["error"] for row in coco(tmp_path))


def test_audio(tmp_path: Path) -> None:
    pytest.importorskip("numpy")
    (tmp_path / "audio").mkdir()
    (tmp_path / "meta").mkdir()
    wav = tmp_path / "audio/sample.wav"
    with wave.open(str(wav), "wb") as out:
        out.setparams((2, 2, 8000, 0, "NONE", "not compressed"))
        out.writeframes(b"\0" * 3200)
    (tmp_path / "meta/esc50.csv").write_text(
        "filename,fold,target,category,src_file\nsample.wav,3,2,rain,123\n"
    )
    row = next(esc(tmp_path))
    assert row["fold"] == 3 and row["channels"] == 2
    features = audio(wav, 16000, 0.2)
    assert features["waveform"].shape == (3200,) and features["log_mel"].shape[1] == 40


def test_sensors_resume_loader(tmp_path: Path) -> None:
    uci = tmp_path / "AirQualityUCI.csv"
    uci.write_text("Date;Time;T;RH;\n10/03/2004;18.00.00;-200;12,5;\n")
    rows = list(sensor_rows(uci))
    assert rows[0]["missing"] and rows[1]["standardized"] == 12.5
    water = tmp_path / "USGSWater.csv"
    keys = [
        "arithmetic_mean",
        "maximum",
        "minimum",
        "median",
        "p5",
        "p10",
        "p25",
        "p50",
        "p75",
        "p90",
        "p95",
    ]
    with water.open("w", newline="") as stream:
        w = csv.DictWriter(
            stream,
            fieldnames=[
                "start_date",
                "monitoring_location_id",
                "approval_status",
                "unit_of_measure",
                *keys,
            ],
        )
        w.writeheader()
        w.writerow(
            dict.fromkeys(keys, "2") | {"start_date": "2020-01-01", "unit_of_measure": "ft^3/s"}
        )
    assert next(sensor_rows(water))["standardized"] == pytest.approx(0.056633693184)
    out = tmp_path / "derived"
    out.mkdir()
    with pytest.raises(ValueError):
        process("UCI", uci, out, 1, 1, 1)
    assert not (out / "UCI").exists()
    process("UCI", uci, out, 1, 1 << 20, 1)
    before = digest(out / "UCI/index.jsonl")
    process("UCI", uci, out, 1, 1 << 20, 1)
    assert digest(out / "UCI/index.jsonl") == before
    assert next(public_batches(out / "UCI"))[0]["measurements"]["T"][-1]
    assert next(records("UCI", uci, 2))["line"] == 2


def test_training_boundary_and_agreement(tmp_path: Path) -> None:
    assert normalized_text(" No\t fire  at 2 https://a.b ", True) == "No fire at 2 [URL]"
    assert normalized_text("   ") is None
    assert group_split("episode1") == group_split("episode1")
    assert list(batches([1, 2, 3], 2)) == [[1, 2], [3]]
    assert fit([("train", True, 0, "one", 2.0), ("train", True, 1, "two", 4.0)])["mean"] == 3
    for split, approved, seed in [
        ("validation", True, 0),
        ("train", False, 0),
        ("train", True, 46),
    ]:
        with pytest.raises(ValueError):
            fit([(split, approved, seed, "x", 1.0)])
    ids = [UUID(int=i) for i in (1, 2)]
    a = dict(zip(ids, ["routine", "urgent"], strict=True))
    assert agreement(a, a)["kappa"] == 1
    assert agreement({}, a)["kappa"] is None
    (tmp_path / "release.json").write_text('{"episodes":[{"plan":{"seed":42}}]}')
    with pytest.raises(ValueError, match="protected"):
        next(native_batches(tmp_path, "model2"))
    with pytest.raises(ValueError, match="protected"):
        trace(load("flood_field").model_copy(update={"seed": 42}), "rules")


def test_temporal_groups_and_near_duplicates() -> None:
    spans = [(str(i), f"2020-01-0{i}", f"2020-01-0{i}") for i in range(1, 8)]
    spans.append(("overlap", "2020-01-05", "2020-01-06"))
    assigned = chronological(spans)
    assert assigned["overlap"] == assigned["5"] == assigned["6"]
    assert assigned["1"] == "train" and assigned["7"] == "test"
    assert chronological([spans[0]]) == {"1": "unassigned"}
    assert list(near_pairs([0, 7, (1 << 64) - 1])) == [(0, 1)]


def test_segmentation_unknown_class_is_flagged(tmp_path: Path) -> None:
    pil = pytest.importorskip("PIL.Image")
    pil.new("RGB", (4, 3)).save(tmp_path / "scene.png")
    pil.new("L", (4, 3), 10).save(tmp_path / "mask.png")
    row = {"path": "scene.png", "mask": "mask.png", "size": [4, 3]}
    assert "error" in inspect_one(tmp_path, "FloodNet", row)
    assert inspect_one(tmp_path, "RescueNet", row)["pixels"] == {"10": 12}


def test_crisis_decode_counts_shared_content_and_flags_bad_references(tmp_path: Path) -> None:
    pil = pytest.importorskip("PIL.Image")
    pil.new("RGB", (3, 2)).save(tmp_path / "ok.png")
    (tmp_path / "bad.png").write_bytes(b"invalid image")
    base = tmp_path / "processed/phase10g-v1"
    (tmp_path / "manifests").mkdir()
    names = ("CrisisMMD", "HERIDAL", "SARD", "FloodNet", "RescueNet", "FLAME", "WiSARD")
    for name in names:
        folder = base / name
        folder.mkdir(parents=True)
        entries = (
            [{"path": p} for p in ("ok.png", "ok.png", "bad.png")]
            if name == "CrisisMMD"
            else [{"sha256": digest(tmp_path / "ok.png")}]
        )
        index = folder / "index.jsonl"
        index.write_text("".join(json.dumps(row) + "\n" for row in entries))
        (folder / "summary.json").write_text(json.dumps({
            "configuration": {"source": str(tmp_path)}, "outputs": {"index.jsonl": digest(index)}
        }))
    decode_crisis(tmp_path)
    out = tmp_path / "manifests/phase10g-crisis-decode-v1"
    summary = json.loads((out / "summary.json").read_bytes())
    assert summary["counts"] == {"references": 3, "flagged": 1}
    assert summary["distinct_image_hashes"] == 2
    assert summary["exact_hash_overlap_by_visual_source"]["HERIDAL"] == 1
    assert json.loads((out / "flags.jsonl").read_bytes())["path"] == "bad.png"
    with pytest.raises(FileExistsError):
        decode_crisis(tmp_path)
