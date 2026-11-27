"""Lossless, atomic development-only preprocessing cache for authorized datasets."""

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import Tensor

from evaluation.data.model2 import digest
from evaluation.model1.data import AuthorizedTaskDataset, _image_tensor, _mask_tensor


class SegmentationCache:
    def __init__(self, directory: Path, binding: dict[str, Any]) -> None:
        metadata = json.loads((directory / "complete.json").read_bytes())
        if metadata["binding"] != binding:
            raise ValueError("incompatible segmentation cache")
        self.paths = [directory / "images.npy", directory / "masks.npy"]
        for path in self.paths:
            if digest(path) != metadata["sha256"][path.name]:
                raise ValueError("corrupted segmentation cache")
        self.stats = [(p.stat().st_size, p.stat().st_mtime_ns) for p in self.paths]
        self.images = np.load(self.paths[0], mmap_mode="r", allow_pickle=False)
        self.masks = np.load(self.paths[1], mmap_mode="r", allow_pickle=False)
        n, size = len(binding["assets"]), binding["image_size"]
        if (
            self.images.shape != (n, 3, size, size)
            or self.masks.shape != (n, size, size)
            or self.images.dtype != np.uint8
            or self.masks.dtype != np.uint8
        ):
            raise ValueError("invalid segmentation cache shape or dtype")

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor]:
        if [(p.stat().st_size, p.stat().st_mtime_ns) for p in self.paths] != self.stats:
            raise ValueError("segmentation cache changed after verification")
        return (
            torch.from_numpy(self.images[index].copy()).float().div_(255),
            torch.from_numpy(self.masks[index].copy()).long(),
        )


def prepare_segmentation_cache(dataset: AuthorizedTaskDataset, root: Path) -> dict[str, Any]:
    if (
        not isinstance(dataset, AuthorizedTaskDataset)
        or dataset.split not in {"train", "validation"}
        or dataset._config.task != "semantic_segmentation"
    ):
        raise ValueError("cache requires authorized training/validation segmentation data")
    if os.name == "nt" and root.resolve().drive.upper() != "D:":
        raise ValueError("cache must remain on D:")
    if dataset.normalization is not None:
        raise ValueError("prepare deterministic cache before normalization")
    started = time.perf_counter()
    assets = []
    for row in dataset.rows:
        target = dataset._targets[row.sample_id]
        assert row.asset is not None and target.annotation is not None
        assets.append(
            [
                row.sample_id,
                row.asset.path,
                row.asset.sha256,
                target.annotation.asset.path,
                target.annotation.asset.sha256,
            ]
        )
    binding = {
        "schema": "segmentation-cache-1",
        "input_manifest": dataset.manifest_sha256,
        "target_manifest": dataset.target_manifest_sha256,
        "authorization": dataset.authorization_id,
        "candidate": dataset.candidate_manifest_sha256,
        "split": dataset.split,
        "image_size": dataset._config.image_size,
        "rgb_exif": "transpose-before-resize",
        "mask_exif": "none",
        "mask_resize": "nearest",
        "rgb_resize": "bilinear",
        "taxonomy": {str(k): v for k, v in dataset._config.mask_value_to_label.items()},
        "indices": dataset.label_indices,
        "assets": assets,
        "implementation": digest(Path(__file__)) + digest(Path(__file__).with_name("data.py")),
    }
    key = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / key
    timings = {"rgb_decode_exif_resize_seconds": 0.0, "mask_decode_resize_remap_seconds": 0.0}
    hit = destination.exists()
    print(
        f"[cache] split={dataset.split} status={'hit' if hit else 'miss'} samples={len(assets)}",
        flush=True,
    )
    if not hit:
        with tempfile.TemporaryDirectory(prefix="building-", dir=root) as tmp:
            staging = Path(tmp)
            size = dataset._config.image_size
            images = np.lib.format.open_memmap(
                staging / "images.npy",
                mode="w+",
                dtype=np.uint8,
                shape=(len(assets), 3, size, size),
            )
            masks = np.lib.format.open_memmap(
                staging / "masks.npy", mode="w+", dtype=np.uint8, shape=(len(assets), size, size)
            )
            for i, (_, image_path, _, mask_path, _) in enumerate(assets):
                tick = time.perf_counter()
                x = _image_tensor(dataset._asset_path(image_path), "RGB", (size, size))
                timings["rgb_decode_exif_resize_seconds"] += time.perf_counter() - tick
                tick = time.perf_counter()
                y = _mask_tensor(
                    dataset._asset_path(mask_path),
                    (size, size),
                    dataset._config.mask_value_to_label,
                    dataset.label_indices,
                )
                timings["mask_decode_resize_remap_seconds"] += time.perf_counter() - tick
                if y.min() < 0 or y.max() >= min(len(dataset.labels), 256):
                    raise ValueError("cache mask outside taxonomy")
                images[i] = x.mul(255).round().byte().numpy()
                masks[i] = y.byte().numpy()
                if (i + 1) % 50 == 0 or i + 1 == len(assets):
                    elapsed = time.perf_counter() - started
                    print(
                        f"[preprocess] {i + 1}/{len(assets)} elapsed_s={elapsed:.2f} "
                        f"eta_s={elapsed / (i + 1) * (len(assets) - i - 1):.2f}",
                        flush=True,
                    )
            images.flush()
            masks.flush()
            del images, masks
            for path in (staging / "images.npy", staging / "masks.npy"):
                with path.open("r+b") as stream:
                    os.fsync(stream.fileno())
            metadata = {
                "binding": binding,
                "sha256": {name: digest(staging / name) for name in ("images.npy", "masks.npy")},
            }
            with (staging / "complete.json").open("w", encoding="utf8") as stream:
                json.dump(metadata, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staging, destination)
    dataset._segmentation_cache = SegmentationCache(destination, binding)
    result = {
        "cache_hit": hit,
        "directory": str(destination),
        "seconds": time.perf_counter() - started,
        **timings,
    }
    print(f"[cache] complete split={dataset.split} seconds={result['seconds']:.2f}", flush=True)
    return result
