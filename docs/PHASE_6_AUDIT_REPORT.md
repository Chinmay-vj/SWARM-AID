# Phase 6 readiness audit

**READY WITH LIMITATIONS** for trusted offline command-agent experiments and Phase 7 backend integration. This is a readiness verification by the implementing assistant before Phase 7, not an independent third-party audit.

## Environment and validation

Windows CPython 3.12.10 in the repository interpreter `.tools\python\python.exe`. Pydantic 2.14.4, pytest 8.4.2, Ruff 0.17.6 and mypy 1.20.2. pip check reported no broken requirements. pytest passed 124 tests with zero failures or skips and two PettingZoo deprecation warnings. Ruff passed. Strict mypy passed across 50 files. Python 3.11 was not exercised.

Ran the simulator headless with `--communication` on flood_basic and with `--command-agent` on all eight new scenarios. Each reached the horizon. Reproduced the Phase 6 report's six-agent flood table before the fix below.

## Findings

| Severity | Finding and disposition |
|---|---|
| High | In fusion mode every corroborating report produced a new incident revision each 100 ms tick, while a decision round trip takes at least 200 ms. Ten of eleven scripted six-agent flood decisions were rejected as revision mismatches. Fixed: while an unexpired recommendation awaits review, a report that leaves category and urgency level unchanged is held and folded into the next revision after the decision or expiry. Material changes still revise immediately. Nine of eleven decisions are now accepted; operator updates fell from 135 to 37 with unchanged first-sighting time and missed-person fraction. Regression `test_corroboration_keeps_pending_revision_decidable`. |
| Medium | The v1.2 command_alert, forwarded_report and human_incident_review types are described in `docs/specifications/MESSAGE_PROTOCOL.md` but not in `docs/communication/MESSAGE_PROTOCOL_GUIDE.md` channel mappings. Open. |
| Medium | Schema-version enforcement for the v1.2 types is tested for forwarded_report and command_alert through integration tests only; `tests/unit/test_contracts.py` has no v1.2 cases. Open. |
| Low | The default review window (1200 ms) is shorter than the freshness window (1500 ms). A report admitted 1200-1500 ms after observation fails recommendation validation and is counted as assessment_rejected. Open. |
| Low | The cyclone and landslide profiles are identical to flood and earthquake; those fixtures add no distinct terrain behaviour. Open. |
| Info | The `origin` remote is the placeholder `https://github.com/YOUR_USERNAME/SWARM-AID.git`. Local development is unaffected. |

## Limitations carried forward

The limitations in `docs/PHASE_6_COMPLETION_REPORT.md` remain: exact-cell association, heuristic urgency, a single seed with a scripted operator, checkpoint restore requiring a complete trusted journal, and no durable crash recovery. Held corroboration reaches the operator only after the decision or expiry, a delay bounded by `review_ms`.
