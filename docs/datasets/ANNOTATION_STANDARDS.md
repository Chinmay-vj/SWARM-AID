# Annotation standards

Preserve each original annotation file and its checksum under the immutable release. Index it by portable path, type, label schema, source, review status and applicable sample IDs. Derived exports retain source reference, conversion code revision, options, class map and a new digest. Keep source-defined negative, ignore, occluded and uncertain states distinct.

| Task | Accepted source representation | Checks before conversion |
|---|---|---|
| Image classification | CSV, JSON or JSONL, one image key and source class set | Validate keys, vocabulary, multi-label semantics and reviewed absence. |
| Object detection | COCO JSON pixel xywh, YOLO normalized center xywh, Pascal VOC XML corners | Check image ID, category table, coordinate origin and inclusive/exclusive conventions. Require finite, positive boxes inside original dimensions. Store optional index boxes as pixel xywh. |
| Semantic segmentation | Integer masks or source polygons in JSON | Check image-to-mask mapping, same grid and dimensions, palette/ignore IDs and transform. Preserve indexed values when decoding. |
| Audio | CSV/JSON/JSONL with clip IDs, classes and optional start/end offsets | Validate sample rate and mono/stereo metadata, nonnegative ordered intervals inside duration. Record whether weak clip labels or timed events. |
| Multimodal | JSON/CSV pairing index | Record RGB/thermal source IDs, capture offsets, calibration and overlap. Report unmatched inputs and missing modalities. Freeze both together. |
| Structured incident | JSON/JSONL preserving typed report, incident revision and evidence IDs | Check mission, observed-at cutoff, reviewer/decision reference, uncertainty, citation membership and expiry. Distinguish rule, scripted and independent human sources. |

The 10A validator checks file integrity, extensions, defined label names, indexed pixel boxes, normalized YOLO rows, COCO top-level lists, VOC root, JSON/JSONL syntax, CSV header and PNG mask dimensions. Release-specific adapters must still check source object relationships, decode full media, validate mask classes, time intervals, alignment and semantic agreement before admitting training data. Original formats remain authoritative.
