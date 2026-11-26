# Release acceptance

| Gate | Evidence required for a future release |
|---|---|
| Identity and integrity | Pin source/version, access date, citation, original sample IDs, file formats, hashes and exact byte totals. Resolve all references under an approved root. Quarantine mismatches. Partial or candidate status is ineligible. |
| Task relevance | Inspect a stratified sample by modality, platform, location and event. Report aerial vs ground viewpoint, height where documented, day/night, weather, scene scale and data gaps. |
| Labels | Review source definitions and ignore rules, compare independent annotation where available, quantify disagreement and uncertain labels. Record positive, reviewed negative and ambiguous counts separately. Missing annotation never implies absence. |
| Visual | Decode originals, preserve dimensions and bit depth, measure small/occluded objects, saturation, blur and compression. For thermal, record sensor band/calibration and radiometric vs display-only encoding or unknown. |
| Acoustic and sensors | Check duration, sample rate, clipping, noise, speech privacy, clock units, calibration and gaps. Distinguish audio tags from timed events. |
| Pairing | Review synchronization, spatial alignment and common scene coverage. Record per-source tolerances and measured alignment error. |
| Sampling | Tabulate class and group counts, negative scenes, imbalance, disaster/location diversity, modality dropout and duplicates by split. Include failure counts and denominators. |
| Rights and reproduction | Record rights and privacy decisions, group split version, source and derived checksums, transform configuration and report digest. |

Task owners must set acceptance thresholds using the intended task and representative source metadata before collection or training. No empirical thresholds or quality results have been established in 10A. File verification checks byte-level integrity against supplied hashes. Full codec decoding, semantic source checks, near-duplicate matching and expert review are source-onboarding work.
