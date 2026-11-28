# Phase 11I handoff

State on 2026-11-27: pipeline implemented; **optimization training has not run**. Phase 11I is not complete.
Phase 11J is not started.

## Code

- `evaluation/model1/phase11i.py`: orchestrator (`prepare`, `smoke`, `run`, `finalize`).
- `evaluation/model1/phase11i_tasks.py`: experiment bodies. Editing it invalidates owner approval digests.
- `evaluation/model1/active_scope.py`: blocks thermal detector training and resume (enforced in `fit` and `wisard.run`).
- `training.fit(deadline=...)`: stops between epochs after checkpointing.
- Tests: `tests/unit/test_phase11i.py`.

Records are under `D:\SWARM-AID-DATA\runs\phase11i` (`optimization_progress.json`, `experiment_results.json`,
`final_model_selection.json`, `checkpoint_preservation.json`, `hardware_migration_manifest.json`, `logs\`,
`experiments\<name>\spec.json|result.json`). `thermal_exclusion_decision.json` is left unmodified, so it still
reads `PENDING_CONFIGURATION_UPDATE`; the enforcement above implements it.

## Run

From `D:\SWARM-AID`, with the real GPU expiry time:

```powershell
.\.venv\Scripts\python.exe -u -m evaluation.model1.phase11i run --deadline 2026-11-27T13:45:00-08:00
```

`--reserve-minutes` (default 30) is held back for Phase 11J and migration. The first deadline is recorded in
`deadline.json`; a later one needs `--extend`. `13:45` is an assumption, not a known expiry.

Resume: repeat the same command. Completed experiments are skipped; interrupted training resumes from its latest
checksummed epoch checkpoint. Add `--only <name> ...` to limit scope. `finalize` rebuilds records and preservation.

## Owner decision (blocks all training)

Earlier training starts were bound to a configuration SHA256, so the new configurations are not covered.
Blocked: `rescuenet`, `floodnet`, `flame` (authorization owner `chinmay`); `esc50`, `uci` (authorization owner
`Chinmy vijayvargiya`). RescueNet and FloodNet also warm start from the baseline checkpoint.
Exact digests are in `owner_decision.template.json`; specs are in `experiments\<name>\spec.json`.

Only the named owner may decide. To approve, copy the template to `owner_decision.approved.json`, remove any
experiment not approved, set `"decision": "APPROVE_TRAINING_START"` and set `"approved_at"` to the current
ISO 8601 time with offset. The file may be added while evaluations run; blocked experiments are rechecked once.

Not blocked (validation-only): `wisard_rgb_eval`, `uci_persistence`, `environment_fusion_eval`.

## Verified so far

- 28 focused tests passed; Ruff and strict mypy passed on affected files; `pip check` and `git diff --check` clean.
- Synthetic smoke run: live batch/epoch logging, checkpoints, deadline line.
- UCI: baseline MAE reproduced (0.683288). On 1,093 identical eligible samples, model 0.687920 and
  persistence 0.556908. The model lacks CO history that persistence uses.
- Fusion stress test: neural never beat deterministic voting; retain the simpler approach. With one weakly wrong
  modality all methods degrade badly (neural accuracy 0.34).
- RescueNet, FloodNet and FLAME baseline weights load; every FLAME train/validation asset is in its cache.

## Unverified

Real training paths (including batch probe, resume on real data) and `wisard_rgb_eval` have not executed.
Time budgets are estimates. RTX 2060 guidance is unmeasured. The reserved test set was not accessed.
