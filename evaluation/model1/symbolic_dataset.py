"""Authorization-bound offline symbolic environmental dataset."""

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch
from torch import Tensor
from torch.utils.data import Dataset

from evaluation.model1.environment_fusion import verify

ROOT = Path("D:/SWARM-AID-DATA")
PREP = ROOT / "runs/phase11h/training-preparation"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AuthorizedSymbolicDataset(Dataset[tuple[dict[str, Tensor], Tensor]]):

    def __init__(
        self,
        split: Literal["train", "validation"],
    ) -> None:

        if split not in {"train", "validation"}:
            raise ValueError("Reserved partition prohibited")

        config_path = PREP / "training_config.json"
        approval_path = PREP / "training_approval.json"

        config = json.loads(config_path.read_bytes())
        approval = json.loads(approval_path.read_bytes())

        if approval.get("approved") is not True:
            raise ValueError("Training approval missing")

        if approval["config_sha256"] != digest(config_path):
            raise ValueError("Configuration checksum mismatch")

        if config["scope"] != "offline symbolic simulation only":
            raise ValueError("Unauthorized scope")

        if approval["scope"] != config["scope"]:
            raise ValueError("Approval scope mismatch")

        if config["test_access"] is not False:
            raise ValueError("Reserved test access prohibited")

        if config["perception_checkpoint_modification"] is not False:
            raise ValueError("Existing checkpoints must be preserved")

        release = Path(config["release"]).resolve()

        if not release.is_relative_to(ROOT.resolve()):
            raise ValueError("Release outside permitted data root")

        verify(release)

        release_hash = digest(release / "release.json")

        if (
            release_hash != approval["release_sha256"]
            or release_hash != config["release_sha256"]
        ):
            raise ValueError("Release authorization mismatch")

        metadata = json.loads(
            (release / "release.json").read_bytes()
        )

        readiness = json.loads(
            (release / "readiness.json").read_bytes()
        )

        if readiness["status"] != "READY" or readiness["blockers"]:
            raise ValueError("Dataset readiness gate failed")

        binding = metadata["binding"]

        if binding["origin"] != "synthetic_simulator_only":
            raise ValueError("Unexpected dataset origin")

        for plan in binding["plans"]:
            if plan["seed"] in range(42, 47):
                raise ValueError("Reserved seed prohibited")
            if plan["split"] not in {"train", "validation"}:
                raise ValueError("Unauthorized partition")

        with np.load(
            release / "inputs.npz", allow_pickle=False
        ) as data:

            selected = (
                (data["split"] == split)
                & data["classification_eligible"]
            )

            self.values = torch.from_numpy(
                data["values"][selected].copy()
            )

            self.available = torch.from_numpy(
                data["available"][selected].copy()
            )

        targets = np.load(
            release / "targets.npy", allow_pickle=False
        )

        self.targets = torch.from_numpy(
            targets[selected].copy()
        )

        if not len(self.targets):
            raise ValueError("Empty authorized partition")

        self.split = split
        self.release = release
        self.config: dict[str, Any] = config
        self.manifest_sha256 = release_hash
        self.approval_sha256 = digest(approval_path)

    def __len__(self) -> int:
        return len(self.targets)

    def __getitem__(
        self, index: int
    ) -> tuple[dict[str, Tensor], Tensor]:

        return {
            "values": self.values[index],
            "available": self.available[index],
        }, self.targets[index]

    def class_weights(self) -> Tensor:

        if self.split != "train":
            raise ValueError("Weights require training partition")

        counts = torch.bincount(
            self.targets, minlength=4
        ).float()

        if (counts == 0).any():
            raise ValueError("Missing training class")

        return counts.sum() / (4 * counts)
