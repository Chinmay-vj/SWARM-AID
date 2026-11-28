# Phase 12 owner decision packet

## Recorded decisions (decision date 2026-11-28)

Source: explicit project-owner confirmation in the working conversation. No identity verification
or signature is implied.

| Item | Status | Recorded scope |
|---|---|---|
| D1 | APPROVED | Close the historical offline research scope of Phase 12 only |
| D2 | APPROVED | Keep checkpoints unchanged as offline artifacts; fuller assessment before expanded use |
| D3 | APPROVED | Learned policies stay offline; movement permission needs independent safety review |
| D4 | APPROVED | Require explicit development seeds; keep the historical scenario default |
| D5 | APPROVED | Results are exploratory only |
| D6 | **UNVERIFIED** | Historical 12G training authorization not confirmed; none is reconstructed |
| D7 | APPROVED | Commit verified changes after diff review; do not push |
| D8 | APPROVED | Defer new baselines and harder tasks |

Not authorized: snapshot compression or incremental storage, retraining, checkpoint conversion,
learned-policy experiments, a new permission architecture, final evaluation.

The options below are the packet as it was presented before these decisions.

## D1. Close which scopes?
- Options: (a) close A, offline research, with its recorded gaps; keep B partial and C blocked.
  (b) keep all of Phase 12 open.
- Recommended: **a**. Evidence: 12G to 12J reports, 453 passing tests.
- Consequence: no claim about operator readiness or algorithm ranking. Reversible: yes.
- Follow-up: record the date and your wording in this file.

## D2. Checkpoint compatibility
- Options: (a) keep checkpoints as historical offline artifacts only. (b) define a new identity
  version covering all runtime sources, then verify and decide. (c) retrain under that version.
- Recommended: **a** now; **b** before any further use. Evidence: only three sources are hashed.
- Consequence: learned policies stay disabled for operator missions. Reversible: yes; (c) costs
  about 2.7 hours per seed pair at the old budget and needs its own authorization.

## D3. Movement permission
- Options: (a) learned policies remain offline only. (b) require a mission authority for every
  learned path, designed and independently safety-reviewed before any integration.
- Recommended: **a** until a review is arranged. Evidence: 12I-FIX defect and open limits.
- Consequence: no operator-facing learned operation. Reversible: yes. Follow-up for (b): reviewer,
  per-drone and in-flight behaviour requirements.

## D4. Default seed 42
- Options: (a) require an explicit development seed in the mission form and tools; keep the
  historical scenario default. (b) change the scenario default in a new schema version.
  (c) leave as is.
- Recommended: **a**. Evidence: form, catalog, API model, CLI and demo scripts default to 42.
- Consequence: (b) changes behaviour of unseeded runs and needs reproducibility notes.
  Reversible: yes.

## D5. Evaluation methodology before any new comparison
- Options: (a) approve protocol `cep-1` (coverage AUC fixed first, independent seed–scenario
  pairing, pre-set checkpoint rule, separate selection and reporting seeds, three exploratory
  learner seeds). (b) amend it. (c) report existing results only.
- Recommended: **c** unless new experiments are wanted, then **a**.
- Consequence: (a) alone starts no experiment. Final seeds stay locked. Reversible: yes until
  experiments run.

## D6. Training authorization record
- Options: (a) state now, dated today, whether the 12G runs were authorized by you; it is recorded
  as a present statement, not a historical record. (b) leave it missing.
- Recommended: **a**, if true. Reversible: the statement can be corrected, not backdated.

## D7. Preservation
- Options: (a) commit the work and copy it off this machine. (b) copy only. (c) neither.
- Recommended: **a**. Evidence: all work since Phase 11 is uncommitted; no verified copy.
- Consequence of (c): loss of the machine loses the work. A commit is hard to undo once pushed.

## D8. Future research additions
- Options: (a) defer. (b) authorize a nearest-unsearched comparator and a harder task as separate
  future work.
- Recommended: **a** for closure. Reversible: yes.

## Related, outside Phase 12
Node.js installation, a PostgreSQL test database, snapshot compression, and the RTX 2060 residency
and precision settings remain pending from Phase 13.
