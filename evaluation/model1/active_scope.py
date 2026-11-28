"""Active Model 1 scope. Exclusions never delete historical artifacts or modality support."""

# Owner decision: D:/SWARM-AID-DATA/runs/phase11i/thermal_exclusion_decision.json
EXCLUDED_TRAINING_TASKS = frozenset({"wisard-thermal-human-detection"})


def require_trainable_task(task_id: str) -> None:
    """Block new training and resumption for excluded detectors."""
    if task_id in EXCLUDED_TRAINING_TASKS:
        raise ValueError(f"task excluded from the active pipeline by owner decision: {task_id}")
