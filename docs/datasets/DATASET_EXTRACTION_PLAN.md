# Extraction plan awaiting inventory and review

No extraction destination has been created. All source locations are in the [audit inventory](DATASET_ACQUISITION_AUDIT.md). For each actual archive below, the additional expanded bytes, scratch bytes and local structure remain unknown. The families shown are expected content for inspection, not discovered archive paths.

| Source under the named raw directory | Expected structure to inspect | Destination if later approved |
|---|---|---|
| HERIDAL, archive name unknown | Images and COCO JSON by split; export README or metadata | Existing verified extracted files in place; otherwise a fresh release subdirectory within raw/rgb/HERIDAL |
| SARD, archive name unknown | Image/annotation splits and source frame identifiers | Same policy within raw/rgb/SARD |
| FloodNet, archive name unknown | Train/validation/test RGB and mask directories, label map | Same policy within raw/rgb/FloodNet |
| RescueNet, archive name unknown | Original indexed masks and RGB by split; optional color previews | Same policy within raw/rgb/RescueNet |
| FLAME/Training.zip and FLAME/Test.zip, expected | Fire and non-fire classification folders | Separate archive namespaces beneath a fresh release directory within raw/rgb/FLAME |
| FLAME/Masks.zip, expected; segmentation-image component unverified | Masks and independently identified corresponding frames | Same release, separate namespaces; defer segmentation materialization until pairs are justified |
| WiSARD, archive name unknown | Visual-only, thermal-only and multimodal sets, or one-flight sample | Same policy within raw/multimodal/WiSARD; reference shared source frames once |
| ESC-50, archive name unknown | Audio, metadata CSV, source ledger and documentation | Same policy within raw/audio/ESC-50 |

1. Enumerate existing files only within the seven paths. Record file signatures, sizes, nested archives, download fragments and source digests. For ZIP, examine the central directory and stream members to verify decompression and CRC without writing payloads. For other formats use the matching read-only integrity test. A passing CRC verifies internal consistency; compare a publisher checksum where available.
2. Normalize each proposed member path for Windows. Reject absolute/drive/UNC paths, parent traversal, alternate streams, reserved names, links and reparse points, case-folded collisions, and paths resolving outside the intended destination. Check for encrypted members, unexpected expansion and collisions with existing files before writing anything.
3. Derive the expanded estimate from member lengths. Compare existing extracted assets by size and digest, including across archives. For a streaming extractor, incremental peak is new uncompressed bytes plus actual D:-based scratch, filesystem overhead and any temporary copy required by the tool. Nested archives require a separate expanded-size estimate. Do not budget a second full extracted tree as scratch by default.
4. Retain the original user layout and every archive. Use an empty release namespace only for genuinely absent material, with no overwrite. Keep work directories and temporary files on D:. Record release-relative manifest paths and validate identifiers, counts, label maps, pairing and splits as described in the [compatibility report](DATASET_COMPATIBILITY_REPORT.md).
5. Submit the measured per-archive plan, free space after peak, duplicate findings and governance status for review before extraction.
