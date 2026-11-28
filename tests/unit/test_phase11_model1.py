import hashlib
import importlib.util
import io
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

if importlib.util.find_spec("torch") is None or importlib.util.find_spec("torchvision") is None:
    pytest.skip("optional ML dependencies are not installed", allow_module_level=True)

import torch
from PIL import Image
from torch import Tensor, nn
from torch.utils.data import DataLoader, TensorDataset

from agents.shared.domain import Cell, Evidence, SensorFrame
from evaluation.data.contracts import Manifest, Registry, Sample
from evaluation.data.model1_prep import CandidateManifest
from evaluation.data.release_authorization import AuthorizationRecord, manifest_sha256
from evaluation.model1.checkpoints import restore_checkpoint, save_checkpoint
from evaluation.model1.data import (
    AuthorizedTaskDataset,
    TaskDataConfig,
    _cached_sensor_source_index,
    _sensor_window,
    build_task_dataloader,
    fit_training_channel_stats,
)
from evaluation.model1.metrics import (
    classification_metrics,
    detection_metrics,
    expected_calibration_error,
    missing_modality_accuracy,
    regression_metrics,
    segmentation_metrics,
)
from evaluation.model1.models import (
    AudioClassifier,
    MissingAwareFusion,
    ModelConfig,
    MultimodalFusionClassifier,
    SensorSequenceModel,
    build_model,
)
from evaluation.model1.provider import (
    Classifier,
    PerceptionPrediction,
    TrainedPerceptionProvider,
)
from evaluation.model1.training import (
    ClassificationTask,
    PredictionBatch,
    RegressionTask,
    SyntheticTaskDataset,
    TrainingConfig,
    TrainingContext,
    fit,
    make_gradient_scaler,
    synthetic_training_context,
)


def _image_bytes(color: tuple[int, int, int] = (120, 10, 4)) -> bytes:
    image = Image.new("RGB", (32, 32), color)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _authorized_release(
    root: Path,
) -> tuple[Registry, Manifest, Manifest, Path, AuthorizationRecord]:
    dataset_root = root / "data"
    image = _image_bytes()
    image_path = dataset_root / "raw" / "sample.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(image)
    target_path = dataset_root / "labels" / "sample.json"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text('{"label":"person"}', encoding="utf-8")
    image_asset = {
        "path": "raw/sample.png",
        "sha256": hashlib.sha256(image).hexdigest(),
        "availability": "available",
    }
    annotation = {
        "format": "json",
        "asset": {
            "path": "labels/sample.json",
            "sha256": hashlib.sha256(target_path.read_bytes()).hexdigest(),
            "availability": "available",
        },
        "labels": ["person"],
        "label_schema_version": "fixture-v1",
        "label_source": "synthetic-test",
        "review_status": "source",
    }
    base_sample = {
        "sample_id": "sample-1",
        "source_ref": "group-1",
        "source_id": "camera-1",
        "licence_ref": "fixture-terms",
        "modality": "image",
        "representation": "physical",
        "split": "train",
        "sequence_id": "group-1",
        "dimensions": [32, 32],
        "asset": image_asset,
    }
    input_manifest = Manifest.model_validate(
        {
            "schema_version": "1.0",
            "manifest_version": "fixture-release-v1",
            "dataset_id": "fixture",
            "dataset_version": "1",
            "origin": "real",
            "role": "operational",
            "samples": [base_sample],
        }
    )
    target_manifest = Manifest.model_validate(
        {
            "schema_version": "1.0",
            "manifest_version": "fixture-target-v1",
            "dataset_id": "fixture",
            "dataset_version": "1",
            "origin": "real",
            "role": "training_targets",
            "samples": [{**base_sample, "annotation": annotation}],
        }
    )
    registry = Registry.model_validate(
        {
            "schema_version": "1.0",
            "datasets": [
                {
                    "dataset_id": "fixture",
                    "name": "Fixture",
                    "origin": "real",
                    "version": "1",
                    "licence": "fixture-terms",
                    "licence_status": "verified",
                    "privacy_status": "approved",
                    "verification": "verified",
                    "privacy_considerations": "Synthetic test fixture.",
                    "modalities": ["image"],
                    "annotation_types": ["json"],
                    "tasks": ["fixture-classification"],
                    "label_definitions": {"person": "fixture class"},
                    "limitations": "Synthetic unit test only.",
                }
            ],
        }
    )
    candidate_dir = dataset_root / "candidate"
    candidate_dir.mkdir(parents=True)
    records_path = candidate_dir / "records.jsonl"
    records_path.write_text('{"record_id":"sample-1"}\n', encoding="utf-8")
    candidate_path = candidate_dir / "candidate.json"
    candidate = CandidateManifest(
        schema_version="phase10i-candidate-1.0",
        artifact_kind="candidate_only_not_approved_training_release",
        dataset_id="fixture",
        dataset_version="1",
        task="fixture-classification",
        records_file=records_path.name,
        records_sha256=hashlib.sha256(records_path.read_bytes()).hexdigest(),
        candidate_records=1,
        partition_counts={"train": 1},
        target_distribution={"person": 1},
        partition_integrity="CANDIDATE_ONLY",
        source_index_sha256="b" * 64,
        raw_inventory_sha256="c" * 64,
    )
    candidate_path.write_text(candidate.model_dump_json(), encoding="utf-8")
    candidate_sha256 = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    authorization = AuthorizationRecord(
        schema_version="phase10i-authorization-1.1",
        authorization_id="synthetic-pair-approval",
        dataset_id="fixture",
        dataset_version="1",
        task_id="fixture-classification",
        candidate_manifest_sha256=candidate_sha256,
        training_manifest_sha256=manifest_sha256(input_manifest),
        training_targets_manifest_sha256=manifest_sha256(target_manifest),
        approved_usage_scopes=("local_training", "local_evaluation"),
        governance_decision="approved",
        governance_evidence_refs=("synthetic-governance-fixture",),
        privacy_decision="approved",
        cloud_processing_decision="not_authorized",
        redistribution_decision="not_authorized",
        human_review_evidence_refs=("synthetic-review-fixture",),
        authorizing_owner_identity="synthetic-test-owner",
        owner_authorization_ref="synthetic-test-authorization",
        reviewer_identity="synthetic-test-reviewer",
        authorized_at=datetime.now(UTC),
        decision="APPROVE",
        decision_rationale="Synthetic test only; no real data or training approval.",
        restrictions=("Synthetic fixture only.",),
    )
    return registry, input_manifest, target_manifest, candidate_path, authorization


def test_uci_regression_huber_forward_backward_is_finite() -> None:
    model = SensorSequenceModel(8, 1, hidden_dim=32)
    values = torch.randn(4, 24, 8)
    available = torch.ones(4, 24, 8, dtype=torch.bool)
    targets = torch.randn(4, 1)
    loss = RegressionTask(loss="huber", huber_delta=1.0).loss(
        model,
        {"values": values, "available": available},
        targets,
    )
    assert torch.isfinite(loss)
    torch.autograd.backward(loss)
    assert all(
        parameter.grad is None or torch.isfinite(parameter.grad).all()
        for parameter in model.parameters()
    )


def test_uci_sensor_rows_skip_blank_timestamps_and_reject_malformed_rows(
    tmp_path: Path,
) -> None:
    from evaluation.data.preprocessing import sensor_rows

    csv_path = tmp_path / "AirQualityUCI.csv"
    csv_path.write_text(
        "Date;Time;CO(GT)\n01/01/2004;00.00.00;1,0\n ; ; \n;;\n",
        encoding="utf-8",
    )
    parsed_rows = list(sensor_rows(csv_path))
    assert len(parsed_rows) == 1
    assert parsed_rows[0]["timestamp"] == "2004-01-01T00:00:00"

    csv_path.write_text(
        "Date;Time;CO(GT)\nnot-a-date;00.00.00;1,0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid UCI timestamp at source row 2"):
        list(sensor_rows(csv_path))


def test_uci_baselines_use_only_the_model_valid_validation_rows() -> None:
    from runs.phase11g3.launch_uci import baseline_metrics

    class ValidationDataset:
        targets = (1.0, 100.0, 3.0)
        previous = (1.0, 999.0, None)

        def __len__(self) -> int:
            return len(self.targets)

        def __getitem__(self, index: int) -> tuple[None, Tensor]:
            return None, torch.tensor([self.targets[index]])

        def previous_sensor_measurement(self, index: int, measurement: str) -> float | None:
            assert measurement == "CO(GT)"
            return self.previous[index]

    metrics = baseline_metrics(
        cast(AuthorizedTaskDataset, ValidationDataset()),
        torch.tensor([True, False, True]),
        train_mean=2.0,
    )
    assert metrics["sample_count"] == 2
    assert metrics["mean_mae"] == pytest.approx(1.0)
    assert metrics["persistence_mae"] == pytest.approx(0.5)
    assert metrics["persistence_fallback_samples"] == 1


def test_finalizer_accepts_early_stopped_checkpoint_without_training() -> None:
    from runs.phase11g3.launch_uci import completed_training_result

    state = {
        "stale_epochs": 10,
        "best_epoch": 16,
        "best_score": 0.972842,
        "best_global_step": 1264,
        "history": [
            {
                "epoch": 26,
                "train_loss": 0.133783,
                "validation_score": 1.058111,
                "validation_metrics": {"mae": 0.752566, "rmse": 1.058111},
                "global_step": 2054,
                "best_epoch": 16,
            }
        ],
    }
    result = completed_training_result(
        state, 26, TrainingConfig(epochs=50, early_stopping_patience=10)
    )
    assert result.best_epoch == 16
    assert result.best_score == pytest.approx(0.972842)
    assert result.history[0].epoch == 26

    incomplete_state = {**state, "stale_epochs": 0}
    with pytest.raises(ValueError, match="completed or early-stopped"):
        completed_training_result(
            incomplete_state,
            16,
            TrainingConfig(epochs=50, early_stopping_patience=10),
        )


def test_uci_sensor_windows_parse_source_once_and_preserve_missing_values(tmp_path: Path) -> None:
    source = tmp_path / "AirQualityUCI.csv"
    source.write_text(
        "Date;Time;T;RH\n01/01/2004;00.00.00;10;50\n01/01/2004;01.00.00;-200;60\n",
        encoding="utf-8",
    )
    sample = cast(
        Sample, SimpleNamespace(source_rows=(2, 3), sensor_feature_names=("T", "RH"))
    )
    _cached_sensor_source_index.cache_clear()
    try:
        values, available = _sensor_window(source, sample)
        _sensor_window(source, sample)
        assert values.tolist() == [[10.0, 50.0], [0.0, 60.0]]
        assert available.tolist() == [[True, True], [False, True]]
        cache = _cached_sensor_source_index.cache_info()
        assert cache.misses == 1 and cache.hits == 1
    finally:
        _cached_sensor_source_index.cache_clear()


def test_cached_sensor_normalization_is_applied_once() -> None:
    dataset = object.__new__(AuthorizedTaskDataset)
    dataset._config = TaskDataConfig("sensor_regression")
    row = SimpleNamespace(sample_id="window-1", sensor_feature_names=("T", "RH"))
    target = SimpleNamespace(annotation=SimpleNamespace(numeric_targets=(4.0,)))
    dataset.rows = (cast(Sample, row),)
    dataset._targets = {"window-1": cast(Sample, target)}
    dataset._sensor_values = torch.tensor([[[12.0, 40.0], [8.0, 60.0]]])
    dataset._sensor_available = torch.tensor([[[True, True], [False, True]]])
    dataset._normalized_sensor_values = None
    dataset._sensor_targets = torch.tensor([[4.0]])
    dataset.normalization = None
    dataset.augmentation_enabled = False
    dataset.set_normalization(torch.tensor([10.0, 50.0]), torch.tensor([2.0, 10.0]))
    features, targets = dataset[0]
    assert features["values"].tolist() == [[1.0, -1.0], [0.0, 1.0]]
    assert features["available"].tolist() == [[True, True], [False, True]]
    assert targets.tolist() == [4.0]


def test_regression_fit_uses_one_validation_forward_and_records_stage_timings() -> None:
    class CountingRegressor(nn.Linear):
        def __init__(self) -> None:
            super().__init__(2, 1)
            self.forward_count = 0

        def forward(self, features: Tensor) -> Tensor:
            self.forward_count += 1
            return super().forward(features)

    fixture_sha256 = hashlib.sha256(b"synthetic regression fixture").hexdigest()
    examples = tuple(
        (torch.tensor([float(index), 1.0]), torch.tensor([float(index)])) for index in range(4)
    )
    train_data = SyntheticTaskDataset(
        examples, fixture_id="tiny-regressor", fixture_sha256=fixture_sha256
    )
    validation_data = SyntheticTaskDataset(
        examples[:2], fixture_id="tiny-regressor", fixture_sha256=fixture_sha256
    )
    model = CountingRegressor()
    result = fit(
        model,
        DataLoader(train_data, batch_size=4),
        DataLoader(validation_data, batch_size=2),
        RegressionTask(loss="huber"),
        config=TrainingConfig(epochs=1, progress=False),
        context=synthetic_training_context("tiny-regression", train_data),
    )
    assert model.forward_count == 2
    assert result.history[0].stage_timings["loader_wait_seconds"] >= 0
    assert result.history[0].stage_timings["forward_and_loss_seconds"] >= 0


def test_task_models_handle_modalities_and_missingness() -> None:
    visual = build_model(ModelConfig(task="image_classification", num_classes=3, image_size=32))
    assert visual(torch.rand(2, 3, 32, 32)).shape == (2, 3)
    thermal = build_model(ModelConfig(task="thermal_classification", num_classes=2, image_size=32))
    assert thermal(torch.rand(2, 1, 32, 32)).shape == (2, 2)
    audio = AudioClassifier(4)
    assert audio(torch.rand(2, 1, 32, 40)).shape == (2, 4)
    sensor = SensorSequenceModel(3, 2, hidden_dim=8)
    logits, valid = sensor(
        torch.rand(2, 5, 3), torch.tensor([[[True, False, True]] * 5, [[False, False, False]] * 5])
    )
    assert logits.shape == (2, 2) and valid.tolist() == [True, False]

    fusion = MissingAwareFusion({"image": 4, "thermal": 2}, hidden_dim=8)
    fused, available = fusion(
        {"image": torch.rand(2, 4), "thermal": torch.rand(2, 2)},
        {"image": torch.tensor([True, False]), "thermal": torch.tensor([False, False])},
    )
    assert fused.shape == (2, 8) and available.tolist() == [True, False]
    assert torch.equal(fused[1], torch.zeros(8))
    multimodal = MultimodalFusionClassifier(
        {
            "image": nn.Sequential(nn.Flatten(), nn.Linear(12, 4)),
            "thermal": nn.Sequential(nn.Flatten(), nn.Linear(4, 2)),
        },
        {"image": 4, "thermal": 2},
        3,
        hidden_dim=8,
    )
    outputs, _ = multimodal(
        {"image": torch.rand(2, 3, 2, 2), "thermal": torch.rand(2, 1, 2, 2)},
        {"image": torch.tensor([True, True]), "thermal": torch.tensor([True, False])},
    )
    assert outputs.shape == (2, 3)


def test_torchvision_detection_and_segmentation_builders() -> None:
    detection = build_model(ModelConfig(task="object_detection", num_classes=3, image_size=64))
    detection.eval()
    with torch.inference_mode():
        detected = detection([torch.rand(3, 64, 64)])
    assert isinstance(detected, list) and set(detected[0]) >= {"boxes", "labels", "scores"}
    segmentation = build_model(
        ModelConfig(task="semantic_segmentation", num_classes=3, image_size=64)
    )
    segmentation.eval()
    with torch.inference_mode():
        segmented = segmentation(torch.rand(1, 3, 64, 64))
    assert segmented["out"].shape == (1, 3, 64, 64)


def test_authorized_task_loader_binds_input_targets_and_train_only_stats(tmp_path: Path) -> None:
    registry, input_manifest, target_manifest, candidate_path, authorization = _authorized_release(
        tmp_path
    )
    data_root = tmp_path / "data"
    dataset = AuthorizedTaskDataset(
        registry,
        input_manifest,
        target_manifest,
        data_root,
        TaskDataConfig("image_classification", image_size=32, batch_size=1),
        task_id="fixture-classification",
        candidate_manifest_path=candidate_path,
        authorization_records=(authorization,),
    )
    batch = next(iter(build_task_dataloader(dataset, seed=7, device=torch.device("cpu"))))
    assert batch[0].shape == (1, 3, 32, 32)
    assert batch[1].tolist() == [0]
    mean, scale = fit_training_channel_stats(dataset)
    assert mean.shape == scale.shape == (3,)
    assert torch.all(scale > 0)


def test_task_loader_rejects_unbound_target_manifest(tmp_path: Path) -> None:
    registry, input_manifest, target_manifest, candidate_path, authorization = _authorized_release(
        tmp_path
    )
    changed = target_manifest.model_copy(update={"manifest_version": "changed"})
    with pytest.raises(ValueError, match="training targets manifest"):
        AuthorizedTaskDataset(
            registry,
            input_manifest,
            changed,
            tmp_path / "data",
            TaskDataConfig("image_classification", image_size=32),
            task_id="fixture-classification",
            candidate_manifest_path=candidate_path,
            authorization_records=(authorization,),
        )


def test_model1_provider_preserves_evidence_and_presence_uncertainty() -> None:
    class FixedModel(nn.Module):
        def forward(self, image: Tensor) -> Tensor:
            return torch.tensor([[0.0, 4.0]], device=image.device)

    class Resolver:
        def resolve(self, agent_id: str, evidence: Evidence) -> bytes:
            assert agent_id == evidence.origin == "d0"
            return _image_bytes()

    evidence_id = uuid4()
    evidence = Evidence(
        evidence_id=evidence_id,
        origin="d0",
        captured_ms=10,
        modality="image",
        artifact_key="fixture-image",
    )
    frame = SensorFrame(
        agent_id="d0",
        tick_ms=20,
        samples=(evidence,),
        cell=Cell(x=1, y=2),
        battery_fraction=0.8,
    )
    classifier = Classifier(
        FixedModel(),
        {
            0: PerceptionPrediction(kind="environment", label="clear", confidence=0.5),
            1: PerceptionPrediction(kind="possible_human", confidence=0.5),
        },
        image_size=32,
    )
    provider = TrainedPerceptionProvider(
        "d0", Resolver(), classifier, provider_id="test-model", task_id="presence-detection"
    )
    findings = provider.perceive(frame)
    assert len(findings) == 1
    assert findings[0].kind == "possible_human" and findings[0].label is None
    assert findings[0].observation.evidence == (evidence,)
    assert findings[0].observation.observed_ms == frame.tick_ms
    assert provider.perceive(frame)[0].observation.observation_id == (
        findings[0].observation.observation_id
    )


def test_metrics_cover_classification_detection_segmentation_and_missingness() -> None:
    logits = torch.tensor([[4.0, 0.0], [0.0, 4.0]])
    labels = torch.tensor([0, 1])
    assert classification_metrics(logits, labels)["accuracy"] == 1.0
    assert expected_calibration_error(logits, labels) >= 0
    assert (
        missing_modality_accuracy(logits, labels, {"image": torch.tensor([True, False])})[
            "missing_image_accuracy"
        ]
        == 1.0
    )
    assert (
        segmentation_metrics(
            torch.tensor([[[[4.0, 0.0]], [[0.0, 4.0]]]]),
            torch.tensor([[[0, 1]]]),
            classes=2,
        )["macro_iou"]
        == 1.0
    )
    assert regression_metrics(torch.tensor([1.0, 3.0]), torch.tensor([1.0, 2.0]))["mae"] == 0.5
    assert (
        detection_metrics(
            [
                {
                    "boxes": torch.tensor([[0.0, 0.0, 10.0, 10.0]]),
                    "labels": torch.tensor([1]),
                    "scores": torch.tensor([0.9]),
                }
            ],
            [{"boxes": torch.tensor([[0.0, 0.0, 10.0, 10.0]]), "labels": torch.tensor([1])}],
        )["map50"]
        == 1.0
    )


def test_regression_metrics_exclude_invalid_sensor_windows() -> None:
    metrics = RegressionTask().metrics(
        PredictionBatch(
            torch.tensor([[1.0], [100.0], [3.0]]),
            torch.tensor([True, False, True]),
        ),
        torch.tensor([[0.0], [99.0], [1.0]]),
    )

    assert metrics["mae"] == 1.5
    assert metrics["rmse"] == pytest.approx(2.5**0.5)


def test_synthetic_fit_and_atomic_checkpoint_recovery(tmp_path: Path) -> None:
    fixture_sha256 = hashlib.sha256(b"synthetic fixture only").hexdigest()
    train_examples = tuple(
        (torch.tensor([float(index), 1.0]), torch.tensor(index % 2, dtype=torch.int64))
        for index in range(8)
    )
    validation_examples = train_examples[:4]
    train_data = SyntheticTaskDataset(
        train_examples, fixture_id="tiny-classifier", fixture_sha256=fixture_sha256
    )
    validation_data = SyntheticTaskDataset(
        validation_examples, fixture_id="tiny-classifier", fixture_sha256=fixture_sha256
    )
    train_loader = DataLoader(train_data, batch_size=4, shuffle=False)
    validation_loader = DataLoader(validation_data, batch_size=4)
    context = synthetic_training_context("synthetic-classification", train_data)
    model = nn.Linear(2, 2)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.01)
    result = fit(
        model,
        train_loader,
        validation_loader,
        ClassificationTask(),
        config=TrainingConfig(epochs=2, early_stopping_patience=2),
        context=context,
        optimizer=optimizer,
    )
    assert result.global_step > 0 and result.history and result.best_epoch > 0
    model_config = {"task": "tiny-classification", "classes": 2}
    training_config = {"epochs": 2, "seed": 42}
    before = {name: value.clone() for name, value in model.state_dict().items()}
    scaler = make_gradient_scaler(enabled=False)
    info = save_checkpoint(
        tmp_path,
        "synthetic-test.pt",
        model,
        optimizer,
        None,
        scaler,
        epoch=result.best_epoch,
        global_step=result.global_step,
        best_validation_metric=result.best_score,
        model_config=model_config,
        training_config=training_config,
        context=context,
    )
    assert info.path.parent.name == "synthetic"
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.add_(10)
    restored = restore_checkpoint(
        info.path,
        info.sha256,
        tmp_path,
        model,
        optimizer,
        None,
        scaler,
        expected_model_config=model_config,
        expected_training_config=training_config,
        expected_context=context,
        device=torch.device("cpu"),
    )
    assert restored.epoch == info.epoch
    assert all(torch.equal(value, model.state_dict()[name]) for name, value in before.items())


def test_real_training_context_requires_bound_approval_and_loader() -> None:
    with pytest.raises(ValueError, match="explicit task authorization"):
        TrainingContext(
            artifact_kind="authorized_training",
            task_id="task",
            release_manifest_sha256="a" * 64,
        )
    context = TrainingContext(
        artifact_kind="authorized_training",
        task_id="task",
        release_manifest_sha256="a" * 64,
        authorization_id="approval",
        candidate_manifest_sha256="b" * 64,
        training_targets_manifest_sha256="c" * 64,
    )
    train = DataLoader(TensorDataset(torch.ones(1, 1), torch.zeros(1, 1)))
    validation = DataLoader(TensorDataset(torch.ones(1, 1), torch.zeros(1, 1)))
    with pytest.raises(ValueError, match="authorization-gated"):
        fit(
            nn.Linear(1, 1),
            train,
            validation,
            ClassificationTask(),
            config=TrainingConfig(epochs=1),
            context=context,
        )


@pytest.mark.parametrize("dataset_id", ["heridal", "sard"])
def test_task_loader_rejects_phase10j_exclusions_before_authorization(
    tmp_path: Path,
    dataset_id: str,
) -> None:
    registry, inputs, targets, candidate, authorization = _authorized_release(tmp_path)
    inputs = inputs.model_copy(update={"dataset_id": dataset_id})
    targets = targets.model_copy(update={"dataset_id": dataset_id})
    with pytest.raises(ValueError, match="excluded from active"):
        AuthorizedTaskDataset(
            registry,
            inputs,
            targets,
            tmp_path / "data",
            TaskDataConfig("image_classification"),
            task_id="fixture",
            candidate_manifest_path=candidate,
            authorization_records=(authorization,),
        )


def test_mask_loader_preserves_classes_and_rejects_unmapped_pixels(tmp_path: Path) -> None:
    from evaluation.model1.data import _mask_tensor

    path = tmp_path / "mask.png"
    mask = Image.new("L", (2, 2))
    mask.putdata([0, 1, 1, 0])
    mask.save(path)
    result = _mask_tensor(
        path, (4, 4), {0: "background", 1: "fixture"}, {"background": 0, "fixture": 1}
    )
    values = {int(value) for row in result.tolist() for value in row}
    assert result.shape == (4, 4) and values == {0, 1}
    with pytest.raises(ValueError, match="without source-verified"):
        _mask_tensor(path, (4, 4), {0: "background"}, {"background": 0})
