"""Separate simulator-only environmental fusion preparation. No training or real pairing."""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch
from pydantic import Field, model_validator
from torch import Tensor, nn
from torch.utils.data import Dataset

from agents.shared.domain import Record
from evaluation.model1.models import MissingAwareFusion
from simulation.core.configuration import load
from simulation.core.engine import Engine
from simulation.sensors.mock import Reading, sense

MODES = ("image", "thermal", "environment")
LABELS = ("routine", "water", "fire", "damage")
VARIANTS = ("native", "partial_missing", "missing", "noisy", "conflict")
SCENARIOS = ("flood_basic", "flood_field", "wildfire_basic", "wildfire_field",
             "earthquake_basic", "earthquake_field", "landslide_field", "cyclone_field")
TERRAIN = {**dict.fromkeys(("base", "dry", "forest", "road", "trail", "building",
                           "obstacle", "restricted", "weak_radio", "burned", "silt", "slope"), 0),
           "water": 1, "fire": 2, "smoke": 2, "thermal_anomaly": 2,
           "damaged": 3, "debris": 3, "blocked": 3}
DATA_ROOT = Path("D:/SWARM-AID-DATA")


def category(value: str) -> int | None:
    # Routine means other KNOWN reference terrain, never a declaration of safety.
    return TERRAIN.get(value)


def eligibility(values: Tensor, available: Tensor) -> Tensor:
    """Contradiction requires disagreeing, confident, nearly pure same-cell reports.

    Mixed categories or low-confidence observations are not automatically conflicts.
    The generator projects only one cell/time into each row.
    """
    if available.dtype != torch.bool or not torch.isfinite(values[available]).all():
        raise ValueError("available evidence must be finite with boolean masks")
    votes = torch.where(available[:, :, None], values[:, :, :4], 0)
    mass = votes.sum(dim=-1)
    strongest, winner = votes.max(dim=-1)
    strong = available & (mass > 0) & (strongest >= .8 * mass) & (values[:, :, 4] >= .5)
    disagreement = (winner[:, :, None] != winner[:, None, :])
    conflict = (disagreement & strong[:, :, None] & strong[:, None, :]).any(dim=(1, 2))
    return (available & (mass > 0)).any(dim=1) & ~conflict


class EpisodePlan(Record):
    scenario: str
    seed: int = Field(ge=0)
    split: Literal["train", "validation"]
    ticks: int = Field(default=8, ge=1, le=1000)

    @model_validator(mode="after")
    def development(self) -> "EpisodePlan":
        if self.seed in range(42, 47):
            raise ValueError("reserved seed")
        return self


def project(readings: tuple[Reading, ...]) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """Only observable content; no reference state, episode ID or seed enters features."""
    values = np.zeros((3, 6), dtype=np.float32)
    for reading in readings:
        mode = reading.evidence.modality
        label = category(reading.value)
        if mode not in MODES or label is None:
            continue
        i = MODES.index(mode)
        values[i, label] += reading.confidence
        values[i, 4] += reading.confidence
        values[i, 5] += 1
    available = values[:, 5] > 0
    values[:, :5] /= np.maximum(values[:, 5:6], 1)
    return values, available


class EnvironmentalFusion(nn.Module):
    """Untrained symbolic model; absent or conflicting evidence must abstain."""
    def __init__(self) -> None:
        super().__init__()
        self.fusion = MissingAwareFusion(dict.fromkeys(MODES, 6), 128)
        self.head = nn.Linear(128, 4)

    def forward(self, values: Tensor, available: Tensor) -> tuple[Tensor, Tensor]:
        if values.ndim != 3 or values.shape[1:] != (3, 6) or available.shape != values.shape[:2]:
            raise ValueError("expected [batch,3,6] features and [batch,3] availability")
        fused, valid = self.fusion({m: values[:, i] for i, m in enumerate(MODES)},
                                  {m: available[:, i] for i, m in enumerate(MODES)})
        valid = valid & eligibility(values, available)
        logits = self.head(fused)
        return torch.where(valid[:, None], logits, torch.zeros_like(logits)), valid


def development_plans() -> tuple[EpisodePlan, ...]:
    return tuple(EpisodePlan(scenario=SCENARIOS[i % len(SCENARIOS)], seed=3000 + i,
                             split="train" if i < 60 else "validation") for i in range(80))


def readiness(targets: np.ndarray[Any, Any], splits: np.ndarray[Any, Any],
              eligible: np.ndarray[Any, Any], rows: list[dict[str, Any]],
              plans: tuple[EpisodePlan, ...]) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    coverage: dict[str, Any] = {}
    blockers = []
    if len(targets) != len(rows) or len(eligible) != len(rows) or len(splits) != len(rows):
        raise ValueError("row alignment mismatch")
    if len({r['sample_id'] for r in rows}) != len(rows):
        raise ValueError("duplicate sample ID")
    native = [i for i, r in enumerate(rows) if r['variant'] == 'native']
    if len({rows[i]['parent_id'] for i in native}) != len(native):
        raise ValueError("duplicate native parent")
    episode_splits: dict[str, str] = {}
    parents: dict[str, tuple[int, str]] = {}
    observation_parents: dict[tuple[str, str], str] = {}
    plan_splits = {f'{p.scenario}/{p.seed}': p.split for p in plans}
    for i, row in enumerate(rows):
        split = str(splits[i])
        if row['seed'] in range(42, 47) or plan_splits.get(row['episode']) != split:
            raise ValueError("reserved seed or episode split mismatch")
        if episode_splits.setdefault(row['episode'], split) != split:
            raise ValueError("episode overlap")
        identity = (int(targets[i]), split)
        if parents.setdefault(row['parent_id'], identity) != identity:
            raise ValueError("parent target or split mismatch")
        if row['variant'] == 'native':
            for oid in row['observation_ids']:
                key = (row['episode'], oid)
                if observation_parents.setdefault(key, row['parent_id']) != row['parent_id']:
                    raise ValueError("duplicate native observation")
    for split, minimum, episodes_minimum, expected in (
        ('train', 20, 8, 60), ('validation', 8, 3, 20)
    ):
        episodes = {p.seed for p in plans if p.split == split}
        scenarios = {p.scenario for p in plans if p.split == split}
        if len(episodes) != expected or scenarios != set(SCENARIOS):
            blockers.append(f'{split}: expected {expected} independent episodes across all 8 scenarios')
        counts[split] = {}
        for variant in VARIANTS:
            chosen = np.asarray([r['variant'] == variant for r in rows]) & (splits == split)
            counts[split][variant] = {
                status: np.bincount(targets[chosen & (eligible == flag)], minlength=4).tolist()
                for status, flag in (('classification', True), ('abstention', False))}
        coverage[split] = {}
        for label, name in enumerate(LABELS):
            indices = [i for i in native if splits[i] == split and targets[i] == label]
            admitted = [i for i in indices if eligible[i]]
            independent = len({rows[i]['episode'] for i in admitted})
            coverage[split][name] = {'native_parents': len(indices),
                                    'eligible_native': len(admitted), 'eligible_episodes': independent}
            if len(admitted) < minimum or independent < episodes_minimum:
                blockers.append(f'{split}/{name}: insufficient eligible native/episode coverage')
    return {'status': 'READY' if not blockers else 'BLOCKED', 'samples': len(rows),
            'label_order': list(LABELS), 'counts_by_split_variant_eligibility': counts,
            'native_coverage': coverage, 'blockers': blockers,
            'scope': 'offline synthetic development readiness only; no accuracy or deployment claim',
            'thresholds': {'train': {'native_per_class': 20, 'episodes_per_class': 8},
                           'validation': {'native_per_class': 8, 'episodes_per_class': 3}}}


def generate(plans: tuple[EpisodePlan, ...], destination: Path) -> Path:
    if not destination.resolve().is_relative_to(DATA_ROOT.resolve()):
        raise ValueError("generated artifacts must remain under D:/SWARM-AID-DATA")
    plans = tuple(EpisodePlan.model_validate(p.model_dump()) for p in plans)
    if not plans or len({p.seed for p in plans}) != len(plans):
        raise ValueError("episodes require unique seeds, including across splits")
    if len(plans) > 100 or sum(p.ticks for p in plans) > 2000:
        raise ValueError("bounded development generation only")
    configs = [load(p.scenario).model_copy(update={"seed": p.seed}) for p in plans]
    binding = {"schema": "symbolic-environment-fusion-2", "plans": [p.model_dump() for p in plans],
               "configs": [c.model_dump(mode="json") for c in configs], "labels": LABELS,
               "modes": MODES, "variants": VARIANTS, "terrain_mapping": TERRAIN,
               "sampling": "offline stratified probes; max 4 unique cells per class/episode", "origin": "synthetic_simulator_only",
               "code": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
                   Path(__file__), Path('simulation/core/engine.py'), Path('simulation/sensors/mock.py'))}}
    key = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    output = destination / ("v2-" + key)
    if output.exists():
        verify(output)
        return output
    destination.mkdir(parents=True, exist_ok=True)
    features, masks, labels, splits, provenance = [], [], [], [], []
    for plan, cfg in zip(plans, configs, strict=True):
        engine = Engine(cfg)
        selected_cells: set[tuple[int, int]] = set()
        selected_counts = [0] * 4
        for _ in range(plan.ticks):
            # Reference state selects OFFLINE probes only; never moves a drone.
            groups: dict[int, list[tuple[int, int]]] = {i: [] for i in range(4)}
            for cell, terrain in engine.world.tiles.items():
                label = category(terrain)
                if label is not None and cell not in selected_cells:
                    groups[label].append(cell)
            sampling = np.random.default_rng(plan.seed * 1000 + engine.t)
            for target, cells in groups.items():
                sampling.shuffle(cells)
                for cell in cells[:max(0, 4 - selected_counts[target])]:
                    selected_cells.add(cell)
                    selected_counts[target] += 1
                    # Distinct sensor principal gives stable unique source IDs without
                    # rewriting any observation ID emitted by the existing sensor.
                    probe = len(selected_cells)
                    agent = f"d{plan.seed * 100000 + engine.t * 1000 + probe}"
                    packet, *_ = sense(cfg, plan.seed, engine.t, agent, cell,
                                       1.0, "north", engine.world.tiles, {})
                    local = tuple(r for r in packet.readings if r.cell is not None
                                  and (r.cell.x, r.cell.y) == cell)
                    x, mask = project(local)
                    parent = f"{plan.scenario}/{plan.seed}/{cell[0]},{cell[1]}"
                    for variant in VARIANTS:
                        value, present = x.copy(), mask.copy()
                        rng = np.random.default_rng(int.from_bytes(hashlib.sha256(
                            f'{parent}/{variant}/corruption'.encode()).digest()[:8], 'little'))
                        if variant == "missing":
                            present[:] = False
                        elif variant == "partial_missing":
                            retained = np.flatnonzero(present)
                            present[:] = False
                            if len(retained):
                                present[int(rng.choice(retained))] = True
                        elif variant == "noisy":
                            value[:, :5] *= rng.uniform(.2, 1, (3, 1)).astype(np.float32)
                            present &= rng.random(3) > .3
                        elif variant == "conflict":
                            # Controlled synthetic contradiction, independent of target.
                            observed = int(value[:, :4].sum(axis=0).argmax())
                            value[:2] = 0
                            value[0, observed] = 1
                            value[1, (observed + 1) % 4] = 1
                            value[:2, 4:] = 1
                            present[:2] = True
                        value[~present] = 0
                        features.append(value)
                        masks.append(present)
                        labels.append(target)
                        splits.append(plan.split)
                        provenance.append({"sample_id": parent + '/' + variant, "parent_id": parent,
                            "episode": f'{plan.scenario}/{plan.seed}', "scenario": plan.scenario,
                            "seed": plan.seed, "tick": engine.t, "agent": agent, "variant": variant,
                            "sampling_cell": cell, "sampling_reference_category": target,
                            "observation_ids": [str(r.evidence.evidence_id) for r in local],
                            "origin": "synthetic", "target_provenance": "simulator_reference_tile"})
            engine.step({a: 0 for a in engine.drones}, report_hook=False)
    eligible = eligibility(torch.from_numpy(np.asarray(features)),
                           torch.from_numpy(np.asarray(masks))).numpy()
    with tempfile.TemporaryDirectory(dir=destination) as temp:
        staging = Path(temp) / 'release'
        staging.mkdir()
        np.savez_compressed(staging / 'inputs.npz', values=np.asarray(features), available=np.asarray(masks),
                            split=np.asarray(splits), classification_eligible=eligible)
        np.save(staging / 'targets.npy', np.asarray(labels, dtype=np.int64))
        (staging / 'provenance.json').write_text(json.dumps(provenance), encoding='utf8')
        report = readiness(np.asarray(labels), np.asarray(splits), eligible, provenance, plans)
        (staging / 'readiness.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        metadata = {"binding": binding, "samples": len(labels), "files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in staging.iterdir()}}
        (staging / 'release.json').write_text(json.dumps(metadata, sort_keys=True), encoding='utf8')
        os.replace(staging, output)
    verify(output)
    return output


def verify(path: Path) -> None:
    metadata = json.loads((path / 'release.json').read_bytes())
    binding = metadata['binding']
    key = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    if path.name != 'v2-' + key or binding['schema'] != 'symbolic-environment-fusion-2':
        raise ValueError("release identity mismatch")
    if set(metadata['files']) != {'inputs.npz', 'targets.npy', 'provenance.json', 'readiness.json'}:
        raise ValueError("incomplete release inventory")
    for name, expected in metadata['files'].items():
        source = (path / name).resolve()
        if not source.is_relative_to(path.resolve()) or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError("symbolic artifact integrity failure")
    plans = tuple(EpisodePlan.model_validate(p) for p in binding['plans'])
    if len({p.seed for p in plans}) != len(plans):
        raise ValueError("episode seed overlap")
    with np.load(path / 'inputs.npz', allow_pickle=False) as data:
        values, available = data['values'], data['available']
        n = metadata['samples']
        if values.shape != (n, 3, 6) or available.shape != (n, 3) or available.dtype != np.bool_:
            raise ValueError("feature schema mismatch")
        eligible = eligibility(torch.from_numpy(values), torch.from_numpy(available)).numpy()
        if not np.array_equal(eligible, data['classification_eligible']):
            raise ValueError("eligibility mismatch")
        targets = np.load(path / 'targets.npy', allow_pickle=False)
        if targets.shape != (n,) or targets.dtype != np.int64 or np.any((targets < 0) | (targets > 3)):
            raise ValueError("target schema mismatch")
        report = readiness(targets, data['split'], eligible,
                           json.loads((path / 'provenance.json').read_bytes()), plans)
    if report != json.loads((path / 'readiness.json').read_bytes()):
        raise ValueError("readiness report mismatch")


class EnvironmentalDataset(Dataset[tuple[Tensor, Tensor, Tensor]]):
    """Development-only tensor loader; IDs and reference state never become inputs."""
    def __init__(self, path: Path, split: Literal["train", "validation"],
                 *, subset: Literal["classification", "abstention"] = "classification") -> None:
        if split not in {"train", "validation"}:
            raise ValueError("reserved test access is prohibited")
        verify(path)
        with np.load(path / 'inputs.npz', allow_pickle=False) as arrays:
            if subset not in {'classification', 'abstention'}:
                raise ValueError('unknown eligibility subset')
            selected = (arrays['split'] == split) & (
                arrays['classification_eligible'] == (subset == 'classification'))
            self.values = torch.from_numpy(arrays['values'][selected].copy())
            self.available = torch.from_numpy(arrays['available'][selected].copy())
        self.targets = torch.from_numpy(np.load(path / 'targets.npy', allow_pickle=False)[selected].copy())

    def __len__(self) -> int:
        return len(self.targets)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor, Tensor]:
        return self.values[index], self.available[index], self.targets[index]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DATA_ROOT / 'runs/phase11h/environment-fusion')
    args = parser.parse_args()
    plans = development_plans()
    output = generate(plans, args.output)
    print(output, flush=True)
    print((output / 'readiness.json').read_text(), flush=True)



if __name__ == '__main__':
    main()
