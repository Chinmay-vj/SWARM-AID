# Phase 12J handoff

Phase 12J has **not** started. Its scope is undefined and needs an explicit owner request. Do not
repeat 12G–12I work; read `PHASE_12I_FIX_REPORT.md`.

## State

- Mission-wide pause is corrected in `Fleet.advance` (`simulation/adapters/model1.py`).
- Learned policies are disabled on operator-facing fleets (`Fleet.allow_external_policy=False`).
  Do not set it outside verification until the owner decides compatibility.
- Checkpoints are unchanged. The launcher identity check passes but does not cover `model1.py`.
- Full suite: 427 passed, 3 skipped.

## Owner decisions

1. Checkpoint compatibility with the corrected runtime, and whether identity should cover more
   sources (a new version; do not rewrite existing metadata).
2. Movement-lease design, including mission authority for standalone SearchEnv.
3. The earlier items in `D:\SWARM-AID-DATA\runs\phase12\phase12i\owner_decisions.json`; all remain
   pending.

## Outstanding

- Verify the backend operator-pause route end to end.
- Replace default scenario seed 42 in tests and configuration, or keep running tests with the
  guard: set `PYTHONPATH` to `D:\SWARM-AID-DATA\runs\phase12\phase12i_fix\seed_guard`, and leave
  `SWARM_ALLOW_LEGACY_RESERVED_SEEDS` unset. The guard lives outside the repository.
- Comparative claims need protocol approval, a harder task and several trained runs.
- Nothing is committed. The migration manifest predates 12G–12I artifacts and no off-machine copy
  is verified; see `PHASE_12H_HANDOFF.md`.

## Constraints

Civilian search-and-rescue simulation only. Seeds 42–46 retired; 900000–900099 locked. No training,
commit or push without approval. Artifacts stay on D:.
