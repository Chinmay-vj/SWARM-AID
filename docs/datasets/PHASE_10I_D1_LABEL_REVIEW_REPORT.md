# Phase 10I-D1 human label-review status

**Status: packet prepared; independent human review pending.** No labels,
corrections, adjudications, or source-policy interpretations were created.

## Queue and evidence

The 152 original review IDs and source paths from the B1/C1 queue are
preserved in the D-drive-only packet
`D:\SWARM-AID-DATA\manifests\phase10i-d1-e1-v2\human_review_packet.jsonl`.
The original queue was not overwritten. Its SHA-256 is
`27756a014f2021eab94863b4ed3dad73a1d69602a644fb3447e2e083631653ff`.

| Source | Count | Review intent |
|---|---:|---|
| HERIDAL | 30 | Interpret empty COCO annotations under source policy |
| SARD | 30 | Interpret empty COCO annotations under source policy |
| WiSARD | 30 | Classify flagged box geometry/source-format issues |
| FloodNet | 29 | Compare selected mask classes with publisher legend and scene |
| RescueNet | 33 | Compare selected mask classes with publisher legend and scene |

Every item resolves to an indexed, readable source file and has a current
SHA-256. For 90 indexed image rows, the current digest matches the Phase 10G
index digest. The remaining 62 mask paths are present in the Phase 10G index;
that index has no per-mask digest, so their recorded hashes are current
baselines, not historical comparisons. A read-only pixel check found all 63
queued focus-class IDs in their associated masks. These checks do not replace
human visual review or establish label correctness.

## Blank decision template

The packet provides two independent reviewer slots per item. Each slot has
blank reviewer identity, decision, rationale, timestamp, and evidence
references. Allowed decisions are `ACCEPT`, `REJECT`,
`CORRECTION_REQUIRED`, `INSUFFICIENT_EVIDENCE`, and `DEFERRED`. The packet
contains zero decisions and 304 blank decision slots.

Human review must not convert an empty annotation into a negative example
without source-policy evidence, infer distress from human presence, infer
thermal calibration or RGB/thermal pairing, or infer missing capture/site
identifiers. The review queue is evidence for adjudication, not training
permission.

## Return requirements

Return a new versioned packet with every completed decision bound to the
original review ID and source digest, reviewer identity, time, protocol
version, rationale, evidence reference, and disagreement/adjudication
status. Preserve abstentions and uncertainty. Keep source imagery and any
private review evidence on the authorized D-drive location; do not add them
to Git or logs. If terms do not authorize a review action, defer and escalate
to the source owner.
