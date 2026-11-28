"""Shared PPO core for IPPO and MAPPO over SearchEnv.

Both share one actor across agents that sees only that agent's local observation.
IPPO: shared critic on the same local observation.
MAPPO: shared critic on [own, mean of all, max of all] local observations. That pooled
input exists only during training; it contains no simulator ground truth.
"""

from dataclasses import dataclass
from typing import Any, Literal, cast

import numpy as np
import torch
from torch import Tensor, nn

from simulation.adapters import marl_contract as contract
from simulation.adapters.marl import SearchEnv

Algorithm = Literal["ippo", "mappo"]
ACTION_COUNT = len(contract.ACTIONS)


def _mlp(inputs: int, hidden: int, outputs: int, gain: float) -> nn.Sequential:
    layers = [nn.Linear(inputs, hidden), nn.Tanh(), nn.Linear(hidden, hidden), nn.Tanh(),
              nn.Linear(hidden, outputs)]
    for layer, scale in zip(layers[::2], (2**0.5, 2**0.5, gain), strict=True):
        assert isinstance(layer, nn.Linear)
        nn.init.orthogonal_(layer.weight, scale)
        nn.init.zeros_(layer.bias)
    return nn.Sequential(*layers)


def masked_log_probabilities(logits: Tensor, mask: Tensor) -> Tensor:
    if not bool(mask.any(-1).all()):
        raise ValueError("every agent needs at least one valid action")
    return logits.masked_fill(~mask, -1e9).log_softmax(-1)


def critic_input(algorithm: Algorithm, observations: Tensor) -> Tensor:
    """Rows are the agents present at one step."""
    if algorithm == "ippo":
        return observations
    pooled = torch.cat((observations.mean(0), observations.amax(0)))
    return torch.cat((observations, pooled.expand(len(observations), -1)), dim=1)


class ActorCritic(nn.Module):
    def __init__(self, algorithm: Algorithm, hidden: int) -> None:
        super().__init__()
        if algorithm not in ("ippo", "mappo"):
            raise ValueError("unknown algorithm")
        self.algorithm: Algorithm = algorithm
        self.actor = _mlp(contract.SIZE, hidden, ACTION_COUNT, 0.01)
        self.critic = _mlp(contract.SIZE * (1 if algorithm == "ippo" else 3), hidden, 1, 1.0)

    def policy(self, observations: Tensor, mask: Tensor) -> Tensor:
        """Decentralized execution: log probabilities from local observations only."""
        return masked_log_probabilities(self.actor(observations), mask)

    def value(self, inputs: Tensor) -> Tensor:
        return cast(Tensor, self.critic(inputs).squeeze(-1))


@dataclass
class Batch:
    observations: Tensor
    critic: Tensor
    masks: Tensor
    actions: Tensor
    log_probabilities: Tensor
    advantages: Tensor
    returns: Tensor


def gae(
    rewards: list[float], values: list[float], next_values: list[float],
    terminated: list[bool], done: list[bool], gamma: float, lam: float,
) -> list[float]:
    """One agent's trajectory. Termination drops the bootstrap; truncation keeps it."""
    advantages = [0.0] * len(rewards)
    running = 0.0
    for t in reversed(range(len(rewards))):
        bootstrap = 0.0 if terminated[t] else next_values[t]
        delta = rewards[t] + gamma * bootstrap - values[t]
        running = delta + (0.0 if done[t] else gamma * lam * running)
        advantages[t] = running
    return advantages


def _stack(agents: list[str], values: dict[str, Any], device: torch.device) -> Tensor:
    return torch.from_numpy(np.stack([values[a] for a in agents])).to(device)


def run_episode(
    env: SearchEnv, model: ActorCritic, seed: int, generator: torch.Generator | None,
    gamma: float, lam: float, device: torch.device,
) -> tuple[list[tuple[Any, ...]], dict[str, Any]]:
    """Sample with `generator`, or act greedily without it. Returns per-agent transitions."""
    observations, infos = env.reset(seed=seed)
    tracks: dict[str, list[dict[str, Any]]] = {a: [] for a in env.possible_agents}
    while env.agents:
        agents = list(env.agents)
        local = _stack(agents, observations, device)
        masks = torch.from_numpy(
            np.stack([infos[a]["action_mask"] for a in agents])).bool().to(device)
        with torch.no_grad():
            log_probabilities = model.policy(local, masks)
            central = critic_input(model.algorithm, local)
            values = model.value(central)
        if generator is None:
            chosen = log_probabilities.argmax(-1).cpu()
        else:
            chosen = torch.multinomial(
                log_probabilities.exp().cpu(), 1, generator=generator).squeeze(-1)
        observations, rewards, terminated, truncated, infos = env.step(
            {a: int(contract.ACTIONS[int(chosen[i])]) for i, a in enumerate(agents)})
        with torch.no_grad():
            following = model.value(
                critic_input(model.algorithm, _stack(agents, observations, device)))
        for i, a in enumerate(agents):
            tracks[a].append({
                "observation": local[i], "critic": central[i], "mask": masks[i],
                "action": int(chosen[i]), "logp": float(log_probabilities[i, int(chosen[i])]),
                "value": float(values[i]), "next": float(following[i]),
                "reward": rewards[a], "terminated": terminated[a],
                "done": terminated[a] or truncated[a],
            })
    rows: list[tuple[Any, ...]] = []
    for track in tracks.values():
        if not track:
            continue
        advantages = gae(
            [s["reward"] for s in track], [s["value"] for s in track],
            [s["next"] for s in track], [s["terminated"] for s in track],
            [s["done"] for s in track], gamma, lam)
        rows += [(s["observation"], s["critic"], s["mask"], s["action"], s["logp"], adv,
                  adv + s["value"]) for s, adv in zip(track, advantages, strict=True)]
    return rows, env.episode_metrics()


def make_batch(rows: list[tuple[Any, ...]], device: torch.device) -> Batch:
    columns = list(zip(*rows, strict=True))
    return Batch(
        torch.stack(columns[0]), torch.stack(columns[1]), torch.stack(columns[2]),
        torch.tensor(columns[3], device=device),
        torch.tensor(columns[4], dtype=torch.float32, device=device),
        torch.tensor(columns[5], dtype=torch.float32, device=device),
        torch.tensor(columns[6], dtype=torch.float32, device=device),
    )


def update(
    model: ActorCritic, optimizer: torch.optim.Optimizer, batch: Batch,
    settings: dict[str, Any], generator: torch.Generator,
) -> dict[str, float]:
    size = len(batch.actions)
    advantages = (batch.advantages - batch.advantages.mean()) / (
        batch.advantages.std(unbiased=False) + 1e-8)
    totals = dict.fromkeys(("policy_loss", "value_loss", "entropy", "approx_kl",
                            "clip_fraction", "gradient_norm"), 0.0)
    count = 0
    for _ in range(settings["epochs"]):
        order = torch.randperm(size, generator=generator).to(batch.actions.device)
        for chunk in torch.split(order, settings["minibatch"]):
            log_probabilities = model.policy(batch.observations[chunk], batch.masks[chunk])
            chosen = log_probabilities.gather(1, batch.actions[chunk, None]).squeeze(1)
            log_ratio = chosen - batch.log_probabilities[chunk]
            ratio = log_ratio.exp()
            clip = settings["clip"]
            policy_loss = -torch.minimum(
                ratio * advantages[chunk],
                ratio.clamp(1 - clip, 1 + clip) * advantages[chunk]).mean()
            value_loss = (model.value(batch.critic[chunk]) - batch.returns[chunk]).square().mean()
            safe = log_probabilities.masked_fill(~batch.masks[chunk], 0)
            entropy = -(safe.exp() * batch.masks[chunk] * safe).sum(-1).mean()
            loss = (policy_loss + settings["value_coefficient"] * value_loss
                    - settings["entropy_coefficient"] * entropy)
            if not torch.isfinite(loss):
                raise FloatingPointError("nonfinite PPO loss")
            optimizer.zero_grad(set_to_none=True)
            torch.autograd.backward(loss)
            norm = torch.nn.utils.clip_grad_norm_(
                model.parameters(), settings["max_gradient_norm"], error_if_nonfinite=True)
            optimizer.step()
            for name, value in (
                ("policy_loss", policy_loss), ("value_loss", value_loss), ("entropy", entropy),
                ("approx_kl", (ratio - 1 - log_ratio).mean()),
                ("clip_fraction", ((ratio - 1).abs() > clip).float().mean()),
                ("gradient_norm", norm),
            ):
                totals[name] += float(value.detach())
            count += 1
    return {name: value / count for name, value in totals.items()}
