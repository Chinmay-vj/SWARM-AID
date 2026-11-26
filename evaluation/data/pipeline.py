"""Extension points for approved source-specific processing in later phases."""

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from evaluation.data.contracts import Dataset, Sample

# Relative to a single release directory. Consumer/modality indexes refer to assets in raw/.
LAYOUT = (
    "raw",
    "interim",
    "processed",
    "annotations",
    "manifests",
    "metadata",
    "splits",
    "licenses",
    "simulation/operational",
    "simulation/evaluator",
    "indexes/model1",
    "indexes/model2",
    "indexes/rgb",
    "indexes/thermal",
    "indexes/audio",
    "indexes/sensors",
    "indexes/paired",
    "artifacts",
)


class SourceAdapter(Protocol):
    def ingest(self, dataset: Dataset, raw: Path) -> Iterable[Sample]: ...


class SampleTransform(Protocol):
    """Conversion or preprocessing must retain source_ref and write derived assets separately."""

    def transform(self, sample: Sample, destination: Path) -> Sample: ...


def initialize_layout(release: Path) -> None:
    for directory in LAYOUT:
        (release / directory).mkdir(parents=True, exist_ok=True)
