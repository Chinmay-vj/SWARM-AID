# Phase 13 handoff: performance and efficiency (proposed, not started)

Needs an explicit owner request. Read `PHASE_12_FINAL_REPORT.md` first; do not repeat Phase 12
work. Named by capability, as `AGENTS.md` asks.

## Proposed scope

| Part | Capability |
|---|---|
| 13A | System performance profiling |
| 13B | Perception (Model 1) inference profiling |
| 13C | Model 2 processing profiling |
| 13D | Communication and backend profiling |
| 13E | Memory and resource efficiency |
| 13F | Dashboard verification |
| 13G | Bounded symbolic simulation scalability |
| 13H | Final optimization verification |

Existing starting points: 12 ms per environment step at 6 agents and 57 ms at 20; rollout is about
99% of training time; CPU is faster than GPU for these small networks.

## Carried restrictions

- Learned policies stay disabled on operator-facing missions
  (`Fleet.allow_external_policy=False`).
- Optimization does not authorize any change to safety, authorization or operator behaviour. The
  operator-authority tests must keep passing.
- `engine.py`, sensors, safety and fleet code are not in checkpoint identity. Optimizing them can
  silently change policy behaviour; rerun the 12I-FIX replay check
  (`phase12i_fix\replay_check.py`) and record the result under a new folder.
- No training. Seeds 900000–900099 locked; 42–46 retired. Artifacts stay on D:. No commit or push
  without approval.

## Watch for

- Demo scripts, connected end-to-end tests and CLI runs still default to seed 42 and are not
  guarded. Pass a development seed.
- PostgreSQL was unavailable; dashboard checks need the frontend dependencies.
- Project mypy has 6 existing errors in `tests/unit/test_phase11_model1.py`.
- Source is uncommitted and no off-machine copy is verified; the migration manifest predates
  Phase 12G. See `PHASE_12H_HANDOFF.md` for the commands.
