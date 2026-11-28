# Phase 12H handoff

Phase 12H has **not** started and needs an explicit owner request. Its scope is not yet defined.

## State

- Phase 12G: both 300,000-step runs complete and verified (`PHASE_12G_COMPLETION_REPORT.md`).
- Checkpoints: `D:\SWARM-AID-DATA\checkpoints\phase12\{ippo-s1,mappo-s1}`. Use `latest.pt` for
  the final policy; `best.pt` is the update-30 policy (see the report). Do not overwrite either.
- Curves and verification: `D:\SWARM-AID-DATA\runs\phase12\phase12g`.
- Source changes are uncommitted.

## Before any comparison claim

1. Owner records the authorization of the 12G runs and a decision on the policy-lease design.
2. Choose a harder, discriminating setting (for example larger maps, shorter horizon, fewer
   agents, or noisy field scenarios) and fix it before looking at results.
3. Fix the seed–scenario coupling in the launcher. This changes training data, so version it.
4. Define best-checkpoint selection that still works when coverage ties.
5. Run heuristic baselines and both policies on the same validation seeds.
6. Run several learner seeds per algorithm and report spread.
7. Log per-episode validation metrics and save the console output and launch command.

Editing `marl.py`, `marl_contract.py`, `marl_ppo.py` or the configuration makes the existing
checkpoints refuse to resume. Preserve those versions if the 12G runs must stay reproducible.

## Constraints still in force

Civilian search-and-rescue simulation only. Development seeds 12000–12999 and validation seeds
13000–13999 only. Seeds 900000–900099 stay unexecuted until the owner approves final evaluation.
Seeds 42–46 are retired as unseen. No commit or push without approval. Artifacts stay on D:.

## Preservation

The recorded hardware deadline (2026-11-27 14:19:35 UTC−8) has passed. Confirm how long this
machine remains available, then copy off it:

```powershell
powershell -ExecutionPolicy Bypass -File D:\SWARM-AID\scripts\migrate_phase11.ps1 -Destination E:\SWARM-AID-MIGRATION -IncludeOptional
```

Replace `E:`. First regenerate the manifest (`python -m evaluation.model1.phase11j migration`) so
that it includes the 12G artifacts, and wait for `VERIFIED`.
