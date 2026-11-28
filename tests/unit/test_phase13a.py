"""Profiling can only use development seeds; latency summaries do not invent percentiles."""

import pytest

from evaluation import phase13a_profile as profile


@pytest.mark.parametrize("seed", [42, 46, 3500, 13000, 900000, 900099])
def test_profiling_refuses_everything_but_its_development_seeds(seed: int) -> None:
    with pytest.raises(ValueError, match="development seeds"):
        profile.require_profiling_seed(seed)


def test_profiling_seed_and_percentiles() -> None:
    assert profile.require_profiling_seed(profile.SEED) == 12990
    assert profile.stats([1.0] * 19)["p95_ms"] is None
    assert profile.stats([float(i) for i in range(1, 101)])["p95_ms"] == 95
