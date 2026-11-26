# Phase 10I-D1 handoff proposal: independent human review

**Proposal only. D1 has not started.** The current candidate pass leaves the
review queue pending and creates no annotations.

## Proposed scope

1. Obtain explicit owner authorization for a bounded, local review session.
2. Select qualified independent reviewers and define an adjudication protocol
   before exposing review examples.
3. Use the existing queue at
   `D:\SWARM-AID-DATA\manifests\phase10i-b1-c1-v1\human_review_queue.jsonl`;
   retain its IDs, source hashes, and pending state. Never replace source
   records or alter protected evaluation data.
4. Review the 152 queued examples: empty HERIDAL/SARD rows, flagged WiSARD
   sidecars, and deterministic FloodNet/RescueNet class/split mask examples.
5. Capture independent decisions, reviewer identity, timestamp, protocol
   version, and disagreement/adjudication status in a new versioned artifact.
6. Keep these decisions as human review evidence, not as permission or
   automatic training labels. Preserve uncertainty and abstentions.

## Required safeguards

- No fabricated or retrospective annotation; no majority vote without a
  predeclared rule.
- Human presence does not establish distress.
- Environmental audio labels do not establish distress.
- Do not infer missing flight/site/video IDs from filename proximity.
- Keep imagery and private review evidence on D:; do not put examples or
  personal data in logs, Git, or external services.
- Stop and escalate if a source's terms do not authorize the proposed review.

## Entry gate and exit evidence

The owner must authorize the review purpose, dataset terms, reviewer access,
retention, and storage. Proposed exit evidence is a signed protocol, a
versioned review ledger, disagreement summary, queue reconciliation, and
independent audit of provenance. D1 must not approve a dataset or start model
training. Further work needs explicit user authorization.
