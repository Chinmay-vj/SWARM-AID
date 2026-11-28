"""Loaded by Python child processes of the test run (conftest puts this folder on PYTHONPATH)."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import seed_guard

seed_guard.install()
