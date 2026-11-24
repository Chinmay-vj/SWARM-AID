from random import Random

from simulation.sensors.mock import Packet


def choose(policy: str, obs: Packet, step: int, seed: int) -> int:
    if policy == "stationary":
        return 5
    if policy == "random":
        return Random(f"policy/{seed}/{obs.frame.agent_id}/{step}").randrange(5)
    return (2, 3, 4, 1)[step // 3 % 4]
