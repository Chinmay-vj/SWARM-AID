"""Atomic, integrity-checked uint8 detection cache; never admits reserved test rows."""

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
from evaluation.model1.data import AuthorizedTaskDataset


class DetectionCache:
    def __init__(self, directory: Path, binding: dict[str, Any]) -> None:
        metadata = json.loads((directory / "complete.json").read_bytes())
        if metadata["binding"] != binding:
            raise ValueError("incompatible detection cache")
        self.paths = [directory / name for name in ("images.npy", "boxes.npy", "offsets.npy")]
        for path in self.paths:
            if digest(path) != metadata["sha256"][path.name]:
                raise ValueError("corrupted detection cache")
        self.stats = [(p.stat().st_size, p.stat().st_mtime_ns) for p in self.paths]
        self.images, self.boxes, self.offsets = (
            np.load(p, mmap_mode="r", allow_pickle=False) for p in self.paths
        )
        n, size = len(binding["assets"]), binding["image_size"]
        if (self.images.shape != (n, 3, size, size) or self.images.dtype != np.uint8
                or self.boxes.ndim != 2 or self.boxes.shape[1] != 5
                or self.boxes.dtype != np.float32 or self.offsets.dtype != np.int64
                or self.offsets.shape != (n + 1,) or self.offsets[0] != 0
                or self.offsets[-1] != len(self.boxes) or np.any(np.diff(self.offsets) <= 0)
                or not np.isfinite(self.boxes).all()
                or np.any(self.boxes[:, :4] < 0) or np.any(self.boxes[:, :4] > size)
                or np.any(self.boxes[:, 2:4] <= self.boxes[:, :2])
                or np.any(self.boxes[:, 4] != 1)):
            raise ValueError("invalid detection cache arrays")

    def __getitem__(self, index: int) -> tuple[Tensor, dict[str, Tensor]]:
        if [(p.stat().st_size, p.stat().st_mtime_ns) for p in self.paths] != self.stats:
            raise ValueError("detection cache changed after verification")
        boxes = torch.from_numpy(self.boxes[self.offsets[index]:self.offsets[index + 1]].copy())
        return torch.from_numpy(self.images[index].copy()).float().div_(255), {
            "boxes": boxes[:, :4], "labels": boxes[:, 4].long(),
        }


def prepare_detection_cache(dataset: AuthorizedTaskDataset, root: Path) -> dict[str, Any]:
    if (not isinstance(dataset, AuthorizedTaskDataset)
            or dataset.split not in {"train", "validation"}
            or dataset._config.task != "object_detection"
            or dataset.label_indices != {"human": 1}):
        raise ValueError("cache requires authorized development human detection data")
    if os.name == "nt" and root.resolve().drive.upper() != "D:":
        raise ValueError("cache must remain on D:")
    started = time.perf_counter()
    assets = []
    offsets = [0]
    for row in dataset.rows:
        ann = dataset._targets[row.sample_id].annotation
        assert row.asset is not None and ann is not None
        assets.append([row.sample_id, row.asset.sha256, ann.asset.sha256, row.dimensions,
                       ann.boxes, ann.box_labels])
        offsets.append(offsets[-1] + len(ann.boxes))
    binding = json.loads(json.dumps({
        "schema": "wisard-detection-cache-1", "image_size": dataset._config.image_size,
        "input_manifest": dataset.manifest_sha256, "target_manifest": dataset.target_manifest_sha256,
        "authorization": dataset.authorization_id, "split": dataset.split, "assets": assets,
        "transform": "RGB-display-bilinear-uint8-xyxy; source orientation must be 1",
    }))
    key = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / key
    hit = destination.exists()
    print(f"[cache] split={dataset.split} hit={hit} samples={len(assets)}", flush=True)
    if not hit:
        with tempfile.TemporaryDirectory(prefix="building-", dir=root) as tmp:
            staging = Path(tmp) / "payload"
            staging.mkdir()
            size = dataset._config.image_size
            images = np.lib.format.open_memmap(staging / "images.npy", mode="w+", dtype=np.uint8,
                                               shape=(len(assets), 3, size, size))
            boxes = np.lib.format.open_memmap(staging / "boxes.npy", mode="w+", dtype=np.float32,
                                              shape=(offsets[-1], 5))
            for i, row in enumerate(dataset.rows):
                x, y = dataset._load_sample(row, dataset._targets[row.sample_id])
                images[i] = x.mul(255).round().byte().numpy()
                boxes[offsets[i]:offsets[i + 1], :4] = y["boxes"].numpy()
                boxes[offsets[i]:offsets[i + 1], 4] = y["labels"].numpy()
                if (i + 1) % 50 == 0 or i + 1 == len(assets):
                    elapsed = time.perf_counter() - started
                    print(f"[cache-build] {i + 1}/{len(assets)} elapsed_s={elapsed:.2f} "
                          f"eta_s={elapsed / (i + 1) * (len(assets) - i - 1):.2f}", flush=True)
            images.flush()
            boxes.flush()
            del images, boxes
            np.save(staging / "offsets.npy", np.array(offsets, dtype=np.int64))
            names = ("images.npy", "boxes.npy", "offsets.npy")
            for name in names:
                with (staging / name).open("r+b") as stream:
                    os.fsync(stream.fileno())
            metadata = {"binding": binding, "sha256": {n: digest(staging / n) for n in names}}
            with (staging / "complete.json").open("w", encoding="utf8") as stream:
                json.dump(metadata, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staging, destination)
    dataset._detection_cache = DetectionCache(destination, binding)
    result = {"cache_hit": hit, "seconds": time.perf_counter() - started}
    print(f"[cache] verified split={dataset.split} seconds={result['seconds']:.2f}", flush=True)
    return result
