"""Test-only evaluation seed isolation for the symbolic engine. Production code is unchanged.

Under pytest, and in Python child processes it starts:
- seed 42, the scenario default, is assigned the development seed 12800 and counted;
- retired seeds 43-46 are refused;
- proposed protected final seeds 900000-900099 are always refused.
SWARM_ALLOW_LEGACY_RESERVED_SEEDS=1 permits 42-46 for deliberate historical reproduction only.
Code that uses these numbers without constructing an Engine is outside this guard.
"""

import importlib.abc
import importlib.machinery
import os
import sys
from collections.abc import Callable
from types import ModuleType
from typing import Any

TARGET = "simulation.core.engine"
DEFAULT_SEED, DEVELOPMENT_SEED = 42, 12800
RETIRED = range(43, 47)
PROTECTED = range(900000, 900100)
substitutions = 0


def isolate(seed: int) -> int:
    """The seed the engine may use for a requested seed."""
    global substitutions
    if seed in PROTECTED:
        raise RuntimeError(f"protected final evaluation seed {seed} refused in tests")
    if os.environ.get("SWARM_ALLOW_LEGACY_RESERVED_SEEDS") == "1":
        return seed
    if seed in RETIRED:
        raise RuntimeError(f"retired reserved seed {seed} refused in tests")
    if seed == DEFAULT_SEED:
        substitutions += 1
        return DEVELOPMENT_SEED
    return seed


def wrap(reset: Callable[[Any, int], None]) -> Callable[[Any, int], None]:
    def guarded(self: Any, seed: int) -> None:
        reset(self, isolate(seed))

    guarded.seed_guard = True  # type: ignore[attr-defined]
    return guarded


def patch(module: ModuleType) -> None:
    if not getattr(module.Engine.reset, "seed_guard", False):
        module.Engine.reset = wrap(module.Engine.reset)


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name: str, path: Any, target: Any = None) -> Any:
        if name != TARGET:
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is None or spec.loader is None:
            return spec
        loader: Any = spec.loader
        run = loader.exec_module

        def exec_module(module: ModuleType) -> None:
            run(module)
            patch(module)

        loader.exec_module = exec_module
        return spec


def install() -> None:
    if TARGET in sys.modules:
        patch(sys.modules[TARGET])
    elif not any(type(f).__name__ == "Finder" and type(f).__module__ == __name__
                 for f in sys.meta_path):
        sys.meta_path.insert(0, Finder())
