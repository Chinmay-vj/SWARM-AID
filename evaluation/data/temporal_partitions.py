"""Propose reproducible chronological development partitions for stationary sources."""

from collections.abc import Iterable
from datetime import datetime


def chronological(
    groups: Iterable[tuple[str, str, str]], train: float = 0.7, validation: float = 0.15
) -> dict[str, str]:
    """Keep intervals intact, coalesce overlaps, and allocate whole ordered blocks."""
    if not (0 < train < 1 and 0 < validation < 1 - train):
        raise ValueError("invalid chronological partition")
    unique: dict[str, tuple[datetime, datetime]] = {}
    for key, start, stop in groups:
        a, b = datetime.fromisoformat(start), datetime.fromisoformat(stop)
        if b < a:
            raise ValueError("invalid interval")
        if key in unique:
            prev_a, prev_b = unique[key]
            a, b = min(a, prev_a), max(b, prev_b)
        unique[key] = a, b
    blocks: list[list[str]] = []
    end = None
    for key, (a, b) in sorted(unique.items(), key=lambda item: item[1]):
        if end is None or a > end:
            blocks.append([])
            end = b
        else:
            end = max(end, b)
        blocks[-1].append(key)
    if len(blocks) < 3:
        return {key: "unassigned" for key in unique}
    n = len(blocks)
    first = max(1, min(n - 2, round(n * train)))
    second = max(first + 1, min(n - 1, round(n * (train + validation))))
    return {
        key: ("train" if i < first else "validation" if i < second else "test")
        for i, block in enumerate(blocks)
        for key in block
    }
