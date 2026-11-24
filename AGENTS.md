# Working in SWARM-AID

Read README.md, docs/DEVELOPMENT_ROADMAP.md and the relevant architecture and specification documents before changing a contract. Phase 1 ends at scaffolding, typed interfaces, validation and documentation. Start later phases only on explicit request.

Keep core Python 3.11/3.12 compatible and usable offline on a Windows CPU. Inject providers through interfaces/providers.py. Keep model and transport SDK imports in adapters. Declare dependencies in the appropriate optional extra. Preserve local memory ownership, synthetic evidence provenance, independent action validation and human authority over consequential decisions.

Use deterministic mission ticks and named seed streams in future simulations. Keep ground truth in the simulator/evaluator boundary. Preserve stable observation IDs across forwarding, validate sender identity outside the payload, and apply human decisions to a checked revision. Keep imagery and private artifacts out of logs and version control.

Update wire types, protocol documentation and validation tests together. Version incompatible changes explicitly. Run pytest, Ruff and strict mypy from the repository root and report actual results. Keep research hypotheses separate from results. Record assumptions, limitations and unverified work in the relevant phase report.
