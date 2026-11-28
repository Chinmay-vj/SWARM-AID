# SWARM-AID Phase 11I Completion Report

Generated 2026-11-27T21:23:52.801579+00:00 by the orchestrator from saved results.

**Status: COMPLETE**

## Experiments

| Experiment | Status | Minutes | Reason |
|---|---|---:|---|
| wisard_rgb_eval | completed | 10.2 |  |
| uci_persistence | completed | 0.0 |  |
| environment_fusion_eval | completed | 0.0 |  |
| rescuenet | completed | 32.1 |  |
| floodnet | completed | 24.5 |  |
| esc50 | completed | 3.6 |  |
| flame | completed | 12.5 |  |
| uci | completed | 0.5 |  |

## Selection (validation only)

| Model | Metric | Baseline | Optimized | Selected | Peak GPU MiB |
|---|---|---:|---:|---|---:|
| RescueNet | macro_iou | 0.602553 | 0.631604 | optimized | 7765 |
| FloodNet | macro_iou | 0.668333 | 0.684977 | optimized | 7542 |
| ESC-50 | macro_f1 | 0.341130 | 0.625182 | optimized | 177 |
| FLAME | macro_f1 | 0.985144 | 0.974506 | baseline | 2346 |
| UCI Air Quality | mae | 0.683289 | 0.673876 | optimized | 32 |
| WiSARD RGB | map50 | 0.105056 | - | baseline | 0 |
| EnvironmentalFusion | macro_f1 | 1.000000 | - | baseline | 0 |
| WiSARD Thermal |  | nan | - | excluded | 0 |

## wisard_rgb_eval

```json
{
  "full_validation_baseline_map50": 0.10505597843466444,
  "limitations": [
    "Fixed evenly spaced validation subset; not comparable with full-validation mAP50",
    "Validation already used for checkpoint selection; reserved test untouched",
    "Low mAP50: unreliable for person finding; never evidence that an area is clear"
  ],
  "selection": "retain_baseline",
  "spec_sha256": "7c29b1f2ad77838f2f613ba8d508641dc8751426a97e7ed5f746db99a1901cea",
  "status": "completed",
  "subset_results_by_inference_size": {
    "1024": {
      "images": 256,
      "map50": 0.02390383933422825,
      "map50_95": 0.004094620619644042,
      "peak_gpu_MiB": 850.62060546875,
      "precision": 0.021702061695861107,
      "recall": 0.26515151515151514,
      "seconds": 23.847280000001774
    },
    "512": {
      "images": 256,
      "map50": 0.10819967469161614,
      "map50_95": 0.021678718253758673,
      "peak_gpu_MiB": 275.20751953125,
      "precision": 0.10233393177737882,
      "recall": 0.32386363636363635,
      "seconds": 18.327528900001198
    },
    "800": {
      "images": 256,
      "map50": 0.036777112195810174,
      "map50_95": 0.0066212602247470425,
      "peak_gpu_MiB": 552.30322265625,
      "precision": 0.03921038399134667,
      "recall": 0.2746212121212121,
      "seconds": 20.12591919999977
    }
  }
}
```

## uci_persistence

```json
{
  "baseline_model_mae_all": 0.683288037776947,
  "baseline_model_mae_eligible": 0.6879202723503113,
  "eligible_samples": 1093,
  "fairness": "Persistence reads the last past CO(GT) value; the model inputs do not include CO(GT) history, so the comparison favours persistence in information access. No future values are used by either method.",
  "input_features": [
    "PT08.S1(CO)",
    "PT08.S2(NMHC)",
    "PT08.S3(NOx)",
    "PT08.S4(NO2)",
    "PT08.S5(O3)",
    "T",
    "RH",
    "AH"
  ],
  "persistence_mae_eligible": 0.5569075345993042,
  "spec_sha256": "379b9907d8742b0ca9981217bfdc6d1a69fcc9f07a92f90da8647ed624dbc6a2",
  "status": "completed",
  "validation_samples": 1198
}
```

## environment_fusion_eval

```json
{
  "conditions": {
    "clean": {
      "category_voting": {
        "accuracy": 1.0,
        "macro_f1": 1.0
      },
      "confidence_weighted": {
        "accuracy": 1.0,
        "macro_f1": 1.0
      },
      "coverage": 1.0,
      "neural": {
        "accuracy": 1.0,
        "macro_f1": 1.0
      },
      "samples": 484
    },
    "drop_half": {
      "category_voting": {
        "accuracy": 1.0,
        "macro_f1": 1.0
      },
      "confidence_weighted": {
        "accuracy": 1.0,
        "macro_f1": 1.0
      },
      "coverage": 0.6219007968902588,
      "neural": {
        "accuracy": 0.9933554530143738,
        "macro_f1": 0.9898809523809524
      },
      "samples": 484
    },
    "noise_0.2": {
      "category_voting": {
        "accuracy": 0.977225661277771,
        "macro_f1": 0.9723731513013132
      },
      "confidence_weighted": {
        "accuracy": 0.9855072498321533,
        "macro_f1": 0.9818000919714199
      },
      "coverage": 0.9979338645935059,
      "neural": {
        "accuracy": 0.9751552939414978,
        "macro_f1": 0.9708218846736638
      },
      "samples": 484
    },
    "noise_0.5": {
      "category_voting": {
        "accuracy": 0.8092243075370789,
        "macro_f1": 0.7702198212820196
      },
      "confidence_weighted": {
        "accuracy": 0.8259958028793335,
        "macro_f1": 0.7887180023002123
      },
      "coverage": 0.9855371713638306,
      "neural": {
        "accuracy": 0.7861635088920593,
        "macro_f1": 0.7582251522246055
      },
      "samples": 484
    },
    "one_wrong_strong": {
      "category_voting": {
        "accuracy": 0.0981818214058876,
        "macro_f1": 0.07586925183870086
      },
      "confidence_weighted": {
        "accuracy": 0.0,
        "macro_f1": 0.0
      },
      "coverage": 0.5681818127632141,
      "neural": {
        "accuracy": 0.08363636583089828,
        "macro_f1": 0.08270395406101747
      },
      "samples": 484
    },
    "one_wrong_weak": {
      "category_voting": {
        "accuracy": 0.42768594622612,
        "macro_f1": 0.37009597790244436
      },
      "confidence_weighted": {
        "accuracy": 0.4917355477809906,
        "macro_f1": 0.4512365138966533
      },
      "coverage": 1.0,
      "neural": {
        "accuracy": 0.33677685260772705,
        "macro_f1": 0.32139067231131546
      },
      "samples": 484
    }
  },
  "limitations": [
    "Perturbations of correlated symbolic validation rows; not real multimodal evidence",
    "Macro F1 is over accepted rows; read together with coverage"
  ],
  "spec_sha256": "ca5d9511aaf5eafa13fc093956ad4893fa2b0d759e4e5661214b4500a86573d7",
  "status": "completed"
}
```

## Limitations

- Validation was used for early stopping and selection; reserved test not accessed.
- Segmentation optimizations are warm-started, so they include the baseline training.
- FLAME partitions are temporal; parent-video independence is unverified.
- Publisher segmentation partitions do not establish site or flight independence.
- ESC-50 environmental classes do not establish human distress.
- WiSARD RGB reliability is low; no physical deployment or autonomous control use.
- UCI persistence uses CO history that the model does not receive.
- Preserved copies share one drive and are not independent backups.
- Phase 11J was not started. Final test evaluation needs separate owner authorization.

Configurations, checkpoints and digests are recorded under `D:\SWARM-AID-DATA\runs\phase11i`.
