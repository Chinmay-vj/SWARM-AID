from agents.drone_agent.components import Settings
from agents.shared.domain import Action, Cell, DroneState, Intent, SensorFrame, TaskLease
from simulation.core.engine import Move


def authorize(
    proposal: Action,
    fallback: Move,
    frame: SensorFrame,
    now: int,
    lease: TaskLease | None,
    settings: Settings,
    state: DroneState,
    override: str,
    online: bool,
    bounds: tuple[int, int],
    restricted: frozenset[Cell],
) -> tuple[Move, str, str]:
    if state == DroneState.ENDED or override == "end":
        return Move.INACTIVE, "approved", "terminal"
    if override == "pause" or state != DroneState.ACTIVE:
        return Move.HOLD, "modified", "operator or lifecycle hold"
    if frame.battery_fraction <= settings.reserve:
        return Move.HOLD, "modified", "battery reserve"
    if proposal.intent == Intent.END and (
        not lease or now >= lease.expires_ms or proposal != lease.action
    ):
        return Move.HOLD, "rejected", "retirement lacks authority"
    if proposal.intent == Intent.END:
        return Move.INACTIVE, "approved", "retire simulated agent"
    if proposal.intent == Intent.HOLD:
        return fallback, "approved", "stationary activity"
    p = frame.cell
    target = proposal.target
    if (
        not online
        or not settings.movement
        or not lease
        or now >= lease.expires_ms
        or proposal != lease.action
    ):
        return Move.HOLD, "rejected", "movement lacks current authority"
    if p is None or frame.tick_ms != now or target is None:
        return Move.HOLD, "human_review_required", "position unavailable or delayed"
    dx = (target.x > p.x) - (target.x < p.x)
    dy = 0 if dx else (target.y > p.y) - (target.y < p.y)
    x, y = p.x + dx, p.y + dy
    if (
        target.x >= bounds[0]
        or target.y >= bounds[1]
        or target in restricted
        or not (0 <= x < bounds[0] and 0 <= y < bounds[1])
        or Cell(x=x, y=y) in restricted
    ):
        return Move.HOLD, "rejected", "outside authorized area"
    move = {
        (1, 0): Move.EAST,
        (-1, 0): Move.WEST,
        (0, 1): Move.SOUTH,
        (0, -1): Move.NORTH,
        (0, 0): Move.OBSERVE,
    }[dx, dy]
    return move, "approved", "leased simulated step"
