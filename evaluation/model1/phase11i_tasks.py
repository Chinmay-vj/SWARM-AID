"""Phase 11I experiment bodies. Run only through evaluation.model1.phase11i.

Every real dataset is built by AuthorizedTaskDataset on the unchanged approved
train/validation partitions (development_only excludes the reserved test split).
"""

import functools
import hashlib
import json
import math
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch
from torch import Tensor, nn

from evaluation.data.contracts import Manifest, Registry
from evaluation.data.release_authorization import AuthorizationBundle
from evaluation.model1 import environment_fusion
from evaluation.model1.data import (
    AuthorizedTaskDataset,
    DatasetSplit,
    TaskDataConfig,
    TaskValidationSession,
    build_task_dataloader,
    fit_sensor_normalization,
)
from evaluation.model1.metrics import classification_metrics
from evaluation.model1.models import ModelConfig, build_model
from evaluation.model1.segmentation import segmentation_terms
from evaluation.model1.segmentation_cache import prepare_segmentation_cache
from evaluation.model1.training import (
    ClassificationTask,
    DetectionTask,
    RegressionTask,
    SegmentationTask,
    TrainingConfig,
    authorized_training_context,
    fit,
    seed_everything,
)

DATA = Path("D:/SWARM-AID-DATA")
RUNS = DATA / "runs/phase11i"


def say(message: str) -> None:
    print(message, flush=True)


def sha(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def baseline(model_name: str) -> dict[str, Any]:
    """Baseline checkpoint, its recorded configuration and its saved validation metrics."""
    inventory = json.loads((RUNS / "baseline_inventory.json").read_bytes())["models"]
    path = Path(next(m["checkpoint"] for m in inventory if m["model"] == model_name))
    sidecar = json.loads(path.with_suffix(".json").read_bytes())
    if sidecar["sha256"] != sha(path):
        raise ValueError(f"baseline checkpoint checksum mismatch: {path}")
    payload = torch.load(path, map_location="cpu", weights_only=True)
    return {
        "path": path,
        "sha256": sidecar["sha256"],
        "metrics": sidecar["result"]["validation_metrics"],
        "payload": payload,
        "model_config": payload["model_config"],
    }


def datasets(
    release: Path,
    kind: Any,
    splits: tuple[DatasetSplit, ...] = ("train", "validation"),
    *,
    image_size: int = 224,
    batch_size: int = 8,
    flip: float = 0.0,
    mask: Mapping[int, str] | None = None,
) -> list[AuthorizedTaskDataset]:
    registry = Registry.model_validate_json((release / "registry.json").read_bytes())
    inputs = Manifest.model_validate_json((release / "operational.json").read_bytes())
    targets = Manifest.model_validate_json((release / "targets.json").read_bytes())
    bundle = AuthorizationBundle.model_validate_json(
        (release / "authorization_bundle.json").read_bytes()
    )
    task = json.loads((release / "candidate.json").read_bytes())["task"]
    config = TaskDataConfig(
        kind,
        image_size=image_size,
        batch_size=batch_size,
        horizontal_flip_probability=flip,
        mask_value_to_label=mask,
        development_only=True,
    )
    session = TaskValidationSession()
    built = []
    for split in splits:
        started = time.perf_counter()
        say(f"[init] authorization and integrity split={split}")
        built.append(
            AuthorizedTaskDataset(
                registry, inputs, targets, DATA, config, task_id=task,
                candidate_manifest_path=release / "candidate.json",
                authorization_records=bundle.records, split=split,
                validation_session=session,
            )
        )
        say(f"[init] split={split} samples={len(built[-1])} "
            f"seconds={time.perf_counter() - started:.1f}")
    return built


class WeightedSegmentation(SegmentationTask):
    """Class-weighted CE plus Dice. Validation metrics stay the unweighted baseline ones."""

    def __init__(self, weights: Tensor) -> None:
        super().__init__(dice_weight=1.0)
        self.weights = weights

    def loss(self, model: nn.Module, features: Tensor, targets: Tensor) -> Tensor:
        logits = model(features)
        logits = logits["out"] if isinstance(logits, Mapping) else logits
        cross_entropy = nn.functional.cross_entropy(
            logits.float(), targets, weight=self.weights.to(logits.device), ignore_index=255
        )
        _, predicted, expected, intersection = segmentation_terms(logits, targets, 255)
        present = expected > 0
        dice = (2 * intersection[present] + 1e-6) / (predicted[present] + expected[present] + 1e-6)
        return cross_entropy + 1 - dice.mean()


class SelectByMAE(RegressionTask):
    def selection_score(self, metrics: Mapping[str, float]) -> tuple[float, Literal["min", "max"]]:
        return metrics["mae"], "min"


class PhotometricJitter(nn.Module):
    """Training-only brightness/contrast jitter on normalized images. Geometry is unchanged."""

    def __init__(self, inner: nn.Module, strength: float) -> None:
        super().__init__()
        self.inner, self.strength = inner, strength

    def forward(self, images: Tensor) -> Any:
        if self.training:
            shape = (len(images), 1, 1, 1)
            gain = 1 + self.strength * (2 * torch.rand(shape, device=images.device) - 1)
            shift = self.strength * (2 * torch.rand(shape, device=images.device) - 1)
            images = images * gain + shift
        return self.inner(images)


class AudioMobileNet(nn.Module):
    """One-channel MobileNetV3-small on per-clip standardized log-mel with SpecAugment."""

    def __init__(self, classes: int) -> None:
        super().__init__()
        self.inner = build_model(
            ModelConfig(task="thermal_classification", num_classes=classes)
        )

    def forward(self, log_mel: Tensor) -> Any:
        mean = log_mel.mean((2, 3), keepdim=True)
        x = (log_mel - mean) / log_mel.std((2, 3), keepdim=True).clamp_min(1e-5)
        if self.training:
            x = x.clone()
            time_steps, bins = x.shape[2], x.shape[3]
            for i in range(len(x)):
                x[i] = x[i].roll(int(torch.randint(time_steps, ())), dims=1)
                for _ in range(2):
                    width = int(torch.randint(max(time_steps // 10, 1), ()))
                    start = int(torch.randint(time_steps - width, ()))
                    x[i, :, start : start + width] = 0
                    width = int(torch.randint(max(bins // 8, 1), ()))
                    start = int(torch.randint(bins - width, ()))
                    x[i, :, :, start : start + width] = 0
        return self.inner(x)


def class_weights(data: AuthorizedTaskDataset, classes: int) -> Tensor:
    """Square-root inverse training pixel frequency, bounded to [0.5, 4]."""
    cache = data._segmentation_cache
    counts = np.zeros(256, dtype=np.int64)
    for start in range(0, len(cache.masks), 64):
        counts += np.bincount(np.asarray(cache.masks[start : start + 64]).ravel(), minlength=256)
    frequency = torch.from_numpy(counts[:classes]).double()
    frequency /= frequency.sum()
    weights = (1 / frequency.clamp_min(1e-6)).sqrt()
    weights /= (weights * frequency).sum()
    return weights.clamp(0.5, 4.0).float()


def flame_cache(data: AuthorizedTaskDataset, root: Path) -> None:
    """Attach the existing decoded FLAME cache after verifying binding and checksum."""
    directory = root / data.split
    metadata = json.loads((directory / "metadata.json").read_bytes())
    descriptor = metadata["descriptor"]
    expected = {
        "authorization_id": data.authorization_id,
        "candidate": data.candidate_manifest_sha256,
        "inputs": data.manifest_sha256,
        "targets": data.target_manifest_sha256,
    }
    if descriptor["binding"] != expected or descriptor["partition"] != data.split:
        raise ValueError("FLAME cache is not bound to the authorized release")
    if sha(directory / "images.npy") != metadata["cache_sha256"]:
        raise ValueError("corrupted FLAME cache")
    images = np.load(directory / "images.npy", mmap_mode="r", allow_pickle=False)
    position = {row["sha256"]: i for i, row in enumerate(descriptor["inventory"])}
    order = {}
    for row in data.rows:
        assert row.asset is not None
        order[row.sample_id] = position[row.asset.sha256]

    def load(sample: Any, target: Any) -> tuple[Tensor, int]:
        image = torch.from_numpy(images[order[sample.sample_id]].copy())
        label = data._class_index(target.annotation.labels[0])
        return image.permute(2, 0, 1).float().div_(255), label

    data._load_sample = load  # type: ignore[method-assign]
    say(f"[cache] flame split={data.split} verified samples={len(order)}")


def memoize_samples(data: AuthorizedTaskDataset) -> None:
    """Decode each already-verified clip once per process (log-mel is the loader bottleneck)."""
    original = data._load_sample

    @functools.cache
    def by_id(sample_id: str) -> tuple[Any, Any]:
        return original(data._inputs[sample_id], data._targets[sample_id])

    data._load_sample = lambda sample, target: by_id(sample.sample_id)  # type: ignore[method-assign]


def feasible_batch(
    model: nn.Module, adapter: Any, sample: tuple[Any, Any], candidates: list[int]
) -> int:
    """Largest candidate whose BF16 forward/backward fits under 24 GiB."""
    features, target = sample
    original = {k: v.detach().clone() for k, v in model.state_dict().items()}
    for batch in candidates:
        try:
            model.load_state_dict(original)  # the probe must not alter weights or BatchNorm
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            x = features.unsqueeze(0).repeat(batch, 1, 1, 1).cuda()
            y = torch.as_tensor(target).unsqueeze(0).repeat(batch, *([1] * target.ndim)).cuda()
            model.cuda().train()
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = adapter.loss(model, x, y)
            torch.autograd.backward(loss)
            peak = torch.cuda.max_memory_allocated() / 2**30
            model.zero_grad(set_to_none=True)
            say(f"[batch-probe] batch={batch} peak_GiB={peak:.2f}")
            if peak < 20:
                model.load_state_dict(original)
                return batch
        except torch.cuda.OutOfMemoryError:
            say(f"[batch-probe] batch={batch} out_of_memory")
    raise RuntimeError("no candidate batch size is feasible")


def latest_checkpoint(folder: Path) -> tuple[Path, str] | None:
    """Newest epoch with a sidecar; an orphan from a crash between writes is set aside."""
    for path in sorted(folder.glob("epoch-*.pt"), reverse=True):
        sidecar = path.with_suffix(".json")
        if sidecar.is_file():
            return path, json.loads(sidecar.read_bytes())["sha256"]
        path.replace(path.with_suffix(".orphan"))
    return None


def train(name: str, spec: dict[str, Any], deadline: float) -> dict[str, Any]:
    """One authorized training experiment. The orchestrator has verified owner approval."""
    release = Path(spec["release"])
    out = RUNS / "experiments" / name
    checkpoints = DATA / "checkpoints/phase11i" / name
    settings = dict(spec["training"])
    candidates = spec["batch_candidates"]
    state_path = out / "state.json"
    state = json.loads(state_path.read_bytes()) if state_path.is_file() else {}
    batch = state.get("batch_size", candidates[0])
    kind = spec["kind"]
    base = baseline(spec["baseline"])
    seed_everything(settings["seed"])
    model_config = dict(base["model_config"])
    adapter: Any
    model: nn.Module
    if kind == "semantic_segmentation":
        taxonomy = model_config["taxonomy"]
        mask = {int(k): v for k, v in taxonomy["raw_to_label"].items()}
        data = datasets(release, kind, image_size=512, batch_size=batch, flip=0.5, mask=mask)
        for item in data:
            prepare_segmentation_cache(item, Path(spec["cache"]))
        classes = len(data[0].labels)
        weights = class_weights(data[0], classes)
        say(f"[class-weights] {[round(float(v), 2) for v in weights]}")
        mean = torch.tensor(model_config["normalization_mean"])
        scale = torch.tensor(model_config["normalization_scale"])
        for item in data:
            item.set_normalization(mean, scale)
        inner = build_model(ModelConfig(task=kind, num_classes=classes, image_size=512))
        inner.load_state_dict(base["payload"]["model_state"])
        model = PhotometricJitter(inner, spec["jitter"])
        adapter = WeightedSegmentation(weights)
        model_config["phase11i"] = {"wrapper": "photometric", "class_weights": weights.tolist()}
    elif kind == "audio_classification":
        data = datasets(release, kind, batch_size=batch)
        for item in data:
            memoize_samples(item)
        model = AudioMobileNet(len(data[0].labels))
        adapter = ClassificationTask()
        adapter.criterion = nn.CrossEntropyLoss(label_smoothing=spec["label_smoothing"])
        model_config = {"architecture": "mobilenet_v3_small_logmel", "num_classes": 50}
    elif kind == "image_classification":
        data = datasets(release, kind, batch_size=batch, flip=0.5)
        for item in data:
            flame_cache(item, Path(spec["cache"]))
            item.set_normalization(
                torch.tensor(model_config["normalization_mean"]),
                torch.tensor(model_config["normalization_scale"]),
            )
        model = PhotometricJitter(build_model(ModelConfig(task=kind, num_classes=2)), spec["jitter"])
        adapter = ClassificationTask()
        adapter.criterion = nn.CrossEntropyLoss(label_smoothing=spec["label_smoothing"])
    else:
        data = datasets(release, "sensor_regression", batch_size=batch)
        mean, scale = fit_sensor_normalization(data[0])
        for item in data:
            item.set_normalization(mean, scale)
        model = build_model(
            ModelConfig(task="sensor_regression", num_classes=1, sensor_features=8,
                        hidden_dim=spec["hidden_dim"], dropout=spec["dropout"])
        )
        adapter = SelectByMAE(loss="huber", huber_delta=spec["huber_delta"])
        model_config.update(hidden_dim=spec["hidden_dim"], dropout=spec["dropout"],
                            huber_delta=spec["huber_delta"])
    if "batch_size" not in state and len(candidates) > 1:
        batch = feasible_batch(model, adapter, data[0][0], candidates)
        for item in data:
            item._config.batch_size = batch
    state_path.write_text(json.dumps({"batch_size": batch}), encoding="utf8")
    config = TrainingConfig.model_validate(
        {**settings, "batch_size": batch, "device": "cuda:0", "mixed_precision": True,
         "amp_dtype": "bfloat16", "workers": 0, "checkpoint_every": 1, "progress": True,
         "max_gpu_memory_gb": 24.0, "checkpoint_root": checkpoints,
         "profile_output_root": out}
    )
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda e: 0.05 + 0.475 * (1 + math.cos(math.pi * min(e / config.epochs, 1)))
    )
    resume = latest_checkpoint(checkpoints / "authorized-training")
    say(f"[start] experiment={name} batch={batch} resume={resume[0] if resume else None} "
        f"deadline_remaining_s={deadline - time.time():.0f}")
    device = torch.device(config.device)
    loaders = [build_task_dataloader(d, seed=config.seed, device=device) for d in data]
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    finished = resume is not None and _is_finished(resume[0], config)
    if not finished:
        fit(model, loaders[0], loaders[1], adapter, config=config,
            context=authorized_training_context(data[0]), model_config=model_config,
            optimizer=optimizer, scheduler=scheduler, deadline=deadline,
            resume_path=resume[0] if resume else None,
            resume_sha256=resume[1] if resume else None)
    last = latest_checkpoint(checkpoints / "authorized-training")
    if last is None:
        raise RuntimeError("no checkpoint was written")
    loop = torch.load(last[0], map_location="cpu", weights_only=True)["loop_state"]
    best_epoch = loop["best_epoch"]
    best = last[0].with_name(f"epoch-{best_epoch:04d}.pt")
    metrics = loop["history"][best_epoch - 1]["validation_metrics"]
    return {
        "status": "completed" if _is_finished(last[0], config) else "interrupted",
        "metric": spec["metric"],
        "value": metrics[spec["metric"]],
        "baseline_value": base["metrics"][spec["metric"]],
        "best_checkpoint": str(best),
        "latest_checkpoint": str(last[0]),
        "best_epoch": best_epoch,
        "epochs_completed": len(loop["history"]),
        "batch_size": batch,
        "this_session_seconds": time.perf_counter() - started,
        "peak_gpu_MiB": torch.cuda.max_memory_allocated() / 2**20,
        "validation_metrics": {
            k: v for k, v in metrics.items() if not k.startswith("confusion_")
        },
    }


def _is_finished(checkpoint: Path, config: TrainingConfig) -> bool:
    payload = torch.load(checkpoint, map_location="cpu", weights_only=True)
    return bool(
        payload["epoch"] >= config.epochs
        or payload["loop_state"]["stale_epochs"] >= config.early_stopping_patience
    )


def wisard_rgb_eval(spec: dict[str, Any], deadline: float) -> dict[str, Any]:
    """Validation-only inference-resolution experiment on a fixed subset. No training."""
    release = Path(spec["release"])
    base = baseline("WiSARD RGB")
    results: dict[str, Any] = {}
    for size in spec["image_sizes"]:
        if results and time.time() > deadline - 240:
            break
        data = datasets(release, "object_detection", ("validation",),
                        image_size=size, batch_size=8)[0]
        indices = np.linspace(0, len(data) - 1, min(spec["samples"], len(data))).astype(int)
        model: Any = build_model(
            ModelConfig(task="object_detection", num_classes=2, image_size=size)
        )
        model.load_state_dict(base["payload"]["model_state"])
        model.cuda().eval()
        predictions: list[Any] = []
        targets: list[Any] = []
        started = time.perf_counter()
        torch.cuda.reset_peak_memory_stats()
        with torch.inference_mode():
            for start in range(0, len(indices), 8):
                batch = [data[int(i)] for i in indices[start : start + 8]]
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    output = model([x.cuda() for x, _ in batch])
                predictions += [{k: v.float().cpu() if v.is_floating_point() else v.cpu()
                                 for k, v in item.items()} for item in output]
                targets += [y for _, y in batch]
                say(f"[wisard-eval] size={size} images={len(targets)}/{len(indices)} "
                    f"elapsed_s={time.perf_counter() - started:.0f} "
                    f"deadline_remaining_s={deadline - time.time():.0f}")
        metrics = DetectionTask().metrics(predictions, targets)
        results[str(size)] = {
            **metrics,
            "images": len(targets),
            "seconds": time.perf_counter() - started,
            "peak_gpu_MiB": torch.cuda.max_memory_allocated() / 2**20,
        }
        say(f"[wisard-eval] size={size} map50={metrics['map50']:.6f} "
            f"precision={metrics['precision']:.4f} recall={metrics['recall']:.4f}")
    return {
        "status": "completed" if len(results) == len(spec["image_sizes"]) else "interrupted",
        "subset_results_by_inference_size": results,
        "full_validation_baseline_map50": base["metrics"]["map50"],
        "selection": "retain_baseline",
        "limitations": [
            "Fixed evenly spaced validation subset; not comparable with full-validation mAP50",
            "Validation already used for checkpoint selection; reserved test untouched",
            "Low mAP50: unreliable for person finding; never evidence that an area is clear",
        ],
    }


def uci_persistence(spec: dict[str, Any], deadline: float) -> dict[str, Any]:
    """Baseline model and persistence MAE on one identical eligible validation sample set."""
    base = baseline("UCI Air Quality")
    train_data, validation = datasets(Path(spec["release"]), "sensor_regression", batch_size=64)
    mean, scale = fit_sensor_normalization(train_data)
    validation.set_normalization(mean, scale)
    model = build_model(ModelConfig.model_validate(
        {k: v for k, v in base["model_config"].items() if k not in {"loss", "huber_delta"}}
    ))
    model.load_state_dict(base["payload"]["model_state"])
    model.eval()
    with torch.inference_mode():
        x = [validation[i] for i in range(len(validation))]
        output, valid = model(torch.stack([a["values"] for a, _ in x]),
                              torch.stack([a["available"] for a, _ in x]))
    target = torch.stack([y for _, y in x])[:, 0]
    previous = [validation.previous_sensor_measurement(i, "CO(GT)") for i in range(len(x))]
    eligible = torch.tensor(
        [p is not None and math.isfinite(p) and p != -200 for p in previous]
    ) & valid
    past = torch.tensor([p if p is not None else 0.0 for p in previous])
    model_error = (output[:, 0] - target).abs()
    return {
        "status": "completed",
        "validation_samples": len(x),
        "eligible_samples": int(eligible.sum()),
        "baseline_model_mae_all": float(model_error[valid].mean()),
        "baseline_model_mae_eligible": float(model_error[eligible].mean()),
        "persistence_mae_eligible": float((past - target).abs()[eligible].mean()),
        "input_features": list(validation.rows[0].sensor_feature_names),
        "fairness": "Persistence reads the last past CO(GT) value; the model inputs do not "
                    "include CO(GT) history, so the comparison favours persistence in "
                    "information access. No future values are used by either method.",
    }


def fusion_eval(spec: dict[str, Any], deadline: float) -> dict[str, Any]:
    """Symbolic stress test. Targets are the simulator labels, never the eligibility rule."""
    prepared = json.loads(
        (DATA / "runs/phase11h/training-preparation/training_config.json").read_bytes()
    )
    release = Path(prepared["release"])
    environment_fusion.verify(release)
    with np.load(release / "inputs.npz", allow_pickle=False) as arrays:
        chosen = (arrays["split"] == "validation") & arrays["classification_eligible"]
        values = torch.from_numpy(arrays["values"][chosen].copy())
        available = torch.from_numpy(arrays["available"][chosen].copy())
    targets = torch.from_numpy(np.load(release / "targets.npy", allow_pickle=False)[chosen].copy())
    checkpoint = DATA / "saved-models/EnvironmentalFusion-v1/environmental_fusion_best.pt"
    model = environment_fusion.EnvironmentalFusion()
    model.load_state_dict(torch.load(checkpoint, map_location="cpu",
                                     weights_only=True)["model_state"])
    model.eval()
    report: dict[str, Any] = {}
    for seed, condition in enumerate(
        ("clean", "noise_0.2", "noise_0.5", "drop_half", "one_wrong_weak", "one_wrong_strong")
    ):
        generator = torch.Generator().manual_seed(7000 + seed)
        v, a = values.clone(), available.clone()
        if condition.startswith("noise"):
            level = float(condition.split("_")[1])
            v[..., :5] = (v[..., :5] + level * torch.randn(v[..., :5].shape, generator=generator)
                          ).clamp(0, 1)
        elif condition == "drop_half":
            a &= torch.rand(a.shape, generator=generator) > 0.5
        elif condition.startswith("one_wrong"):
            confidence = 0.3 if condition.endswith("weak") else 0.9
            for i in range(len(v)):
                modes = a[i].nonzero().flatten()
                mode = int(modes[torch.randint(len(modes), (), generator=generator)])
                wrong = (int(targets[i]) + 1 + int(torch.randint(3, (), generator=generator))) % 4
                v[i, mode] = 0
                v[i, mode, wrong] = confidence
                v[i, mode, 4] = confidence
                v[i, mode, 5] = 1
        v = torch.where(a[..., None], v, torch.zeros_like(v))
        with torch.inference_mode():
            logits, valid = model(v, a)
        votes = torch.where(a[..., None], v[..., :4], torch.zeros(()))
        methods = {
            "neural": logits,
            "category_voting": nn.functional.one_hot(votes.argmax(-1), 4).float()
            .mul((a & (votes.sum(-1) > 0))[..., None]).sum(1),
            "confidence_weighted": (votes * v[..., 4:5]).sum(1),
        }
        rows: dict[str, Any] = {"samples": len(v), "coverage": float(valid.float().mean())}
        for method, scores in methods.items():
            # Every method abstains on the same rule, so only the classifiers differ.
            if valid.any():
                m = classification_metrics(scores[valid], targets[valid])
                rows[method] = {"accuracy": m["accuracy"], "macro_f1": m["macro_f1"]}
        report[condition] = rows
        say(f"[fusion] {condition} {rows}")
    return {
        "status": "completed",
        "conditions": report,
        "limitations": [
            "Perturbations of correlated symbolic validation rows; not real multimodal evidence",
            "Macro F1 is over accepted rows; read together with coverage",
        ],
    }
