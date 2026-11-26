# Simulation limitations and Phase 10F specification

The simulator emits deterministic symbolic readings with an opaque Evidence key. It has no RGB, thermal or audio renderer, and the simulator does not upload evidence media. A symbolic possible-human report tests provenance and decision logic. It supplies no information about pixel-level detection, acoustic performance or human condition. Several disaster profiles share dynamics and differ mainly by tile labels. No missing-person fixture exists. Naturally generated conflicts are sparse; record any injected conflicts as such.

| Open limitation | Phase 10 impact | Phase 11 provider work | Phase 12 MARL work | Final evaluation implication |
|---|---|---|---|---|
| Label-only profile diversity and missing fixture | Stratify releases and document equivalent scenarios | Physical perception needs external samples | Weak environment diversity | Avoid independent-disaster or field-validity claims |
| PostgreSQL/PostGIS unverified | SQLite/local exports support intake | Cross-database persistence unverified | Relevant if DB-backed traces used | Reproduce on deployed backend before portability claims |
| Interrupted simulation cannot resume exactly | Quarantine partial episodes or rerun from seed | Avoid incomplete label windows | Exclude broken trajectories | Record failures/restarts and denominators |
| PettingZoo bypasses integrated stack | Identify trace origin | Limited value for fused/transported provider comparisons | Integrated policy boundary required | Compare like execution paths |
| Trained-provider selection open | Record intended consumer only | Configuration/factory required | Needed for learned-policy comparisons | Pin selected provider and fallback behavior |
| Model artifact resolution open | Asset references and integrity only | Scoped resolver and compatible decoding required | Relevant for learned observation/policy artifacts | Reproduce which actual bytes were loaded |
| Provider-version provenance incomplete | Record release/config/code digest and unknown provider version | Record provider per finding/revision | Record behavior-policy version | Prevent unsupported attribution of performance changes |

### Phase 10F proposed acceptance specification

1. Inventory equivalent disaster configurations and define distinct mechanisms with domain reviewers, including flood extent/change, smoke/visibility and debris/access. For each mechanism specify agent-visible effects, noise assumptions, evaluator-only truth and matched baseline configurations.
2. Specify a missing-person search fixture with synthetic identity, presence/absence, uncertainty and occlusion. Include reviewed-negative locations, missing modalities and alternative explanations. Keep truth accessible only to evaluator and sensors.
3. Define scenario variants and named seed streams with independent held-out locations and events. Keep evaluation seeds 42–46 reserved. Record per-scenario config digest, mechanism version and expected symbolic traces.
4. Verify deterministic replay, scoped observations, consistent mission timing, safety enforcement and unchanged legacy scenarios. Demonstrate a measurable observation or environmental transition difference across new profiles at matched seed. Exercise stale, conflicting and forwarded evidence and report their frequencies.
5. Publish scenario cards, acceptance tests, limitations and a baseline comparison with separate operational and evaluator metrics. Treat physical media generation as a separately specified capability requiring validation against real sensor data.

These are future acceptance criteria. Phase 10A changes only offline data infrastructure.
