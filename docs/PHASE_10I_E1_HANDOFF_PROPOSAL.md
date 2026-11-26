# Phase 10I-E1 handoff proposal: source governance decisions

**Proposal only. E1 has not started.** All public-source licences remain
unverified in the registry and privacy remains pending.

## Proposed scope

For each of the ten Model 1 sources, an authorized data steward and legal or
privacy reviewer should:

1. Bind the local archive/index to the exact publisher release and version.
2. Obtain primary source terms, attribution requirements, and any
   research-only, non-commercial, derivative, or redistribution restrictions.
3. Record an explicit purpose-specific determination covering local
   inspection, training, evaluation, retention, redistribution, and any
   third-party/cloud processing.
4. Complete privacy and sensitive-content review, including aerial
   person imagery, audio with human sounds, timestamps/location, and
   display-coded thermal imagery.
5. Update a new versioned registry/governance snapshot with evidence
   references and reviewer identity; preserve current `unverified` and
   `pending` states until a decision is documented.

## Source-specific attention

- Reconcile UCI's CC BY 4.0 metadata with its research-only/commercial
  exclusion statement.
- Distinguish RescueNet's CC BY-NC-ND 4.0 dataset statement from the code
  repository's MIT licence.
- Obtain clip-level ESC-50 terms and attribution evidence.
- Do not infer permission from a project page, local README, access to a
  downloaded file, or source-code licence.
- Do not treat source-reported terms as clearance for a different use.

## Required gate

No training or redistribution is allowed unless the exact release, checksum,
purpose, governance status, privacy review, and release manifest have all
been approved by the authorized owner. The existing approval safeguards must
remain intact. This proposal grants no permission, changes no registry status,
and does not authorize Phase 11 or Phase 10I-E1 execution.
