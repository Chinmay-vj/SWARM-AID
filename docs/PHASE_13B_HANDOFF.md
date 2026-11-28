# Phase 13B handoff: perception inference

Not started; needs an explicit owner request. Read `PHASE_13A_COMPLETION_REPORT.md`; do not repeat
the baseline.

## Candidate work, safe to outputs

1. Import torchvision and warm resident models at startup (cold start only).
2. Decode each image once when several models consume it; require bit-identical tensors.
3. Review residency (`max_resident=2` against seven models) to avoid reload churn; measure first.
4. Test whether FP16 is worthwhile: it was slower than FP32 here at batch 1. Changing the
   configured precision changes numerics and needs approval.

## Acceptance

Same checkpoints and preprocessing, bit-identical inputs, equal outputs at the same precision and
device, same abstention and unavailable behaviour, thermal still excluded, no claim that detection
or audio means distress. Compare against `model1_baseline.json` under the same conditions and
write results to a new folder under `D:\SWARM-AID-DATA\runs\phase13`.

## Constraints

No training, weight, resolution, architecture or quantization changes. Learned policies stay
disabled on operator-facing missions. Seeds: development only; 900000–900099 locked. No commit or
push without approval. Source is uncommitted and no off-machine copy is verified.

Note: the larger measured system cost is backend persistence (13D); the owner may prefer to do it
first.
