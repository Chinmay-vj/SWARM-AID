from pathlib import Path
from uuid import UUID

import pytest

from agents.shared.domain import Cell
from evaluation.experiment_runner import episode
from simulation.adapters.task_registry import SurveyTask
from simulation.core.configuration import Scenario, load


def test_task_authority_and_expiry() -> None:
    t = SurveyTask(UUID(int=1), UUID(int=2), "d0", Cell(x=0, y=0), 0, 10)
    with pytest.raises(ValueError):
        t.update("d1", 2, "in_progress", "foreign")
    t.update("d0", 2, "in_progress", "received")
    with pytest.raises(ValueError):
        t.update("d0", 10, "completed", "late", UUID(int=3))
    t.update("d0", 10, "expired", "deadline")
    with pytest.raises(ValueError):
        t.update("d0", 11, "in_progress", "replay")
    assert [v.state for v in t.history] == [
        "created",
        "available",
        "assigned",
        "in_progress",
        "expired",
    ]


@pytest.mark.parametrize(
    "scenario",
    [
        "flood_basic",
        "flood_unavailable",
        "flood_server_unavailable",
        "wildfire_basic",
        "earthquake_basic",
        "flood_network_partition",
        "flood_network_loss",
        "flood_network_delay",
        "flood_multiple",
    ],
)
def test_shared_replay(scenario: str) -> None:
    config = Scenario.model_validate(load(scenario).model_dump() | {"horizon": 8})
    result = episode(config, "shared_information")
    assert result == episode(config, "shared_information")
    history = result["mission_history"]
    assert isinstance(history, list) and history[-1] == (800, "completed")


def test_custom_policy_rejected_before_movement() -> None:
    from agents.shared.coordination import MissionContext
    from simulation.adapters.model1 import Fleet
    from simulation.core.engine import Engine

    class Outside:
        def target(
            self, mission: MissionContext, member: str, round_index: int, reported: frozenset[Cell]
        ) -> Cell:
            return Cell(x=mission.width, y=0)

    engine = Engine(load("flood_basic"))
    fleet = Fleet(engine, policy=Outside())
    fleet.advance(engine)
    assert fleet.assignments and fleet.assignments.issued == 0
    assert len(fleet.assignments.conflicts) == len(engine.drones)
    fleet.assignments.transition(0, "paused")
    with pytest.raises(ValueError):
        fleet.assignments.transition(0, "initializing")


def test_matched_exports(tmp_path: Path) -> None:
    import json

    from evaluation.experiment_runner import Experiment, run

    path = run(
        Experiment(
            scenarios=("flood_basic",),
            agents=(1,),
            seeds=(42,),
            policies=("independent", "fixed_sector"),
        ),
        tmp_path,
    )
    first, second = [json.loads(p.read_text()) for p in sorted(path.glob("episode-*.json"))]
    assert first["scenario"] == second["scenario"]
    assert first["tasks_issued"] == 0 < second["tasks_issued"]
    assert len((path / "comparison.csv").read_text().splitlines()) == 3


def test_sample_levels_are_unique() -> None:
    from evaluation.experiment_runner import Experiment

    with pytest.raises(ValueError, match="duplicate experiment levels"):
        Experiment(
            scenarios=("flood_basic",), agents=(1,), seeds=(42, 42), policies=("independent",)
        )


def test_report_identity_and_missing_location() -> None:
    from communication.messages import (
        EnvironmentalObservation,
        HazardDetection,
        PossibleHumanDetection,
    )
    from simulation.adapters.model1 import Fleet
    from simulation.core.engine import Engine

    engine = Engine(load("flood_basic"))
    fleet = Fleet(engine, coordination="shared_information")
    assert fleet.network and fleet.assignments
    for _ in range(3):
        fleet.advance(engine)
    history = fleet.network.history["command"]
    for msg in history:
        payload = msg.payload
        if isinstance(payload, (EnvironmentalObservation, HazardDetection, PossibleHumanDetection)):
            obs = payload.observation.model_copy(
                update={"observation_id": UUID(int=711), "cell": None}
            )
            new = msg.model_copy(
                update={"payload": payload.model_copy(update={"observation": obs})}
            )
            conflict = obs.model_copy(update={"cell": Cell(x=11, y=9)})
            history.extend(
                (
                    new,
                    new,
                    msg.model_copy(
                        update={"payload": payload.model_copy(update={"observation": conflict})}
                    ),
                )
            )
            break
    else:
        pytest.fail("fixture produced no observation")
    before = set(fleet.assignments.reported)
    count = fleet.assignments.repeated_reports
    fleet.assignments.advance(fleet.network, engine.t * engine.config.tick_ms)
    assert fleet.assignments.observations[UUID(int=711)].cell is None
    assert fleet.assignments.repeated_reports == count + 2
    assert fleet.assignments.reported == before
    assert fleet.assignments.conflicts[-1][2] == "conflicting observation identity"
