# Phase 10B readiness

**Ready for manual release verification. Acquisition approval is pending for all 11 candidates.** The registry can record unknown values, the offline validator can check a combined manifest collection, and the storage plan supports an external Windows drive. The synthetic fixture exercises the metadata path only.

| Suggested verification order | Reason and release-specific decision |
|---|---|
| 1. HERIDAL, VisDrone | Assess aerial human detection first. Verify release, distribution terms, flight groups, licence and privacy scope, annotation format, small-person labels and suitability of true negative scenes. |
| 2. HIT-UAV, KAIST, FLIR ADAS | Check thermal encoding, sequence keys and conditions. Verify registration for any fusion subset. Record the viewpoint difference between roadway and aerial data. |
| 3. FloodNet, RescueNet, xBD | Check disaster event and geographic overlap, mask/polygon semantics and pre/post pairing. A release with a single event supports within-event evaluation only. |
| 4. ESC-50, FSD50K, AudioSet | Evaluate source/clip rights and availability separately, then the need for a future operational audio contract. Audio remains a research-only modality. |
| 5. Integrated symbolic episodes | Define episode inventory, reserved seeds, task/incident grouping and separation of operational records from research truth. Independent expert review is a separate source of assessment targets. |

No listed source yet establishes a complete fire/smoke corpus, calibrated environmental sensor series, disaster-specific aligned RGB/thermal coverage or independently reviewed command assessments. Record those as coverage gaps.

Before the first approved acquisition, pin the intended release, its verified official location and terms, reviewer and permitted use, privacy decision, expected size, target-volume budget, label and group mapping and an immutable staging destination. Record unresolved fields in the registry. Before admitting samples into a training or evaluation release, verify file availability, hashes, codec/annotation semantics and full-collection leakage checks. Freeze split and manifest digests. Phase 10A provides the tooling and specifications; the first collection decision belongs to Phase 10B.
