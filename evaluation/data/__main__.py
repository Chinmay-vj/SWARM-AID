"""Read-only validation CLI; schema emits JSON Schema to stdout."""

import argparse
import csv
import json
import os
import sys
import wave
from pathlib import Path
from xml.etree.ElementTree import ParseError

from pydantic import BaseModel

from evaluation.data.contracts import Manifest, Registry, Storage
from evaluation.data.validation import validate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("configs/datasets/registry.json"))
    parser.add_argument("--config", type=Path, default=Path("configs/datasets/storage.json"))
    parser.add_argument("--schema", choices=["registry", "manifest", "storage"])
    parser.add_argument("--verify-files", action="store_true")
    parser.add_argument("manifest", type=Path, nargs="*")
    args = parser.parse_args()
    if args.schema:
        models: dict[str, type[BaseModel]] = {
            "registry": Registry,
            "manifest": Manifest,
            "storage": Storage,
        }
        model = models[args.schema]
        print(json.dumps(model.model_json_schema(), indent=2))
        return 0
    try:
        config = Storage.model_validate_json(args.config.read_bytes())
        storage = Storage(
            root=os.environ.get("SWARM_DATASET_ROOT", config.root), schema_version="1.0"
        )
        registry = Registry.model_validate_json(args.registry.read_bytes())
        manifests = [Manifest.model_validate_json(path.read_bytes()) for path in args.manifest]
        if args.verify_files and not manifests:
            raise ValueError("file verification requires at least one manifest")
        counts = validate(registry, manifests, Path(storage.root), verify_files=args.verify_files)
        print(json.dumps({"datasets": len(registry.datasets), "rows_by_split": counts}))
    except (ValueError, OSError, ParseError, wave.Error, csv.Error, EOFError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
