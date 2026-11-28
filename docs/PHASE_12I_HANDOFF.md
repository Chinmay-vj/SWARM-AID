# Phase 12I handoff

Phase 12I has **not** started. Its scope is undefined and it needs an explicit owner request. Do
not repeat the 12G verification or the 12H investigation; read `PHASE_12H_COMPLETION_REPORT.md`.

## Readiness

- Ready: owner decisions, protocol approval, exploratory analysis of existing episode records.
- Not ready: any claim comparing IPPO and MAPPO, further training, or final evaluation.

## Owner decisions

Recorded unapproved in `D:\SWARM-AID-DATA\runs\phase12\phase12h\owner_decision_pending.json`:

1. Movement-lease abstraction (simulation only).
2. A record of the Phase 12G training authorization.
3. A harder task: for example fewer agents, shorter horizon or larger map, with varied starts and
   blocked cells. Fix it before looking at results.
4. Seed–scenario pairing fix and the new checkpoint-selection rule.
5. Adding a nearest-unsearched baseline.
6. Training budget: 1.4 h pilot, 8.3 h (3 seeds) or 13.8 h (5 seeds).
7. Whether to revise the `corroborated` and `resolved_uncertainty` reward terms (new version).
8. Protected final evaluation on 900000–900099.

Also decide whether the `latency: 2` immobility in `earthquake_field` is intended.

## State

- Checkpoints unchanged in `D:\SWARM-AID-DATA\checkpoints\phase12`; use `latest.pt` provisionally.
- Evaluator: `evaluation/marl_robustness.py`; fixtures: `tests/integration/test_phase12h.py`.
- The evaluator skips episodes already in `robustness_episodes.jsonl`. Use a new output folder if
  the evaluator, checkpoints or conditions change.
- Changing `marl.py`, `marl_contract.py` or `marl_ppo.py` makes the checkpoints fail identity
  checks.
- Exposed validation seeds: 13000–13008 and 13100–13104.
- Nothing is committed. The migration manifest predates 12G and 12H artifacts; see
  `PHASE_12H_HANDOFF.md` for the preservation commands. No off-machine copy is verified.

## Constraints

Civilian search-and-rescue simulation only. Seeds 42–46 retired; 900000–900099 untouched. No
training, commit or push without approval. Artifacts stay on D:.
