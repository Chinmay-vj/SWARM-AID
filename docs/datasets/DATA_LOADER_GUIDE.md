# CPU data loaders

`evaluation.data.review_loaders.public_batches(folder, size, rate)` streams private source-index records in variable-length Python lists. It resolves source assets beneath the recorded root. RGB classification, COCO detection and class-index segmentation return original-coordinate arrays and source labels. Thermal previews retain the original image mode. Paired RGB–thermal inputs require an explicit pair identifier and synchronization reference. No WiSARD pair was inferred. CrisisMMD yields a source image and its normalized paired text. HumAID yields normalized text and its original class. Sensor inputs exclude the alarm, recording counter and group identifiers. The WAV loader returns mono waveform, log-Mel features, source and output rates, window, hop and filter count. The default preview batch size is one. Select only a small batch for high-resolution imagery.

`native_batches(batch, "model1", size)` yields symbolic readings and reports. `native_batches(batch, "model2", size)` yields the validated as-of feature projection. Both reject an entire mixed release containing reserved episodes. Use the frozen pilot validator for protected-partition integrity checks. Never concatenate protected pilot records into a development loader.

`training_partition.approved_training` verifies Phase 10A manifests and registry governance before yielding training-partition samples. `save_normalizer` checks a supplied operational manifest and its source IDs before fitting. The saved manifest digest and parameter digest identify the frozen transform consumed by `standardized`. Missing measurements remain missing. No public training release is approved. Preview indexes are review tools. On-the-fly RGB brightness accepts approved training records only. Letterboxing transforms boxes and resizes masks by nearest neighbour with an explicit padding ID.

```python
from pathlib import Path
from evaluation.data.review_loaders import public_batches
folder = Path("D:/SWARM-AID-DATA/processed/phase10g-v1/ESC-50")
batch = next(public_batches(folder, size=2, rate=16000))
```
