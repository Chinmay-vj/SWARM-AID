# TESTING GUIDE

Run python -m pytest -q tests/integration/test_transport.py for the transport suite and python -m pytest -q for all regressions. Tests cover schema, malformed input, permissions, group fan-out, oversize payloads, identity reuse, loss, replay, reordering, queue saturation, heartbeat timeouts, stale reports, recovery and lease cancellation. The human fixture exercises incident review, decision exchanges and a revision-bound override. Use --communication --output runs to capture comparable JSON metrics and JSONL events.
