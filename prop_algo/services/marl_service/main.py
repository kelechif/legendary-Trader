import os
import sys
import time
from pathlib import Path

_PROP_ALGO = Path(__file__).resolve().parents[2]
_ROOT = _PROP_ALGO.parent
for _p in (_ROOT, _PROP_ALGO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from infra.stream import Stream
from marl.policy import AgentPolicy
from marl.trainer import AgentTrainer
from marl.marl_agent import MARLAgent
from marl.environment import MultiAgentEnv
from marl.marl_controller import MARLController


def main():
    # Cap CPU: mission/autonomy streams stay hot; avoid continuous torch train steps.
    loop_sleep = float(os.getenv("MARL_LOOP_SLEEP", "2"))
    threads = max(1, int(os.getenv("MARL_TORCH_THREADS", "1")))
    block_ms = int(os.getenv("STREAM_BLOCK_MS", "1000"))
    try:
        import torch

        torch.set_num_threads(threads)
        torch.set_num_interop_threads(1)
    except Exception:
        pass

    bus = Stream()
    env = MultiAgentEnv()

    def make_agent(name, in_dim, out_dim):
        policy = AgentPolicy(in_dim, out_dim)
        return MARLAgent(name, policy, AgentTrainer(policy))

    agents = [
        make_agent("StrategyAgent", 3, 2),
        make_agent("RiskAgent", 3, 3),
        make_agent("ExecutionAgent", 3, 2),
        make_agent("GovernanceAgent", 3, 2),
        make_agent("ResearchAgent", 3, 2),
        make_agent("MarketAgent", 3, 2),
    ]

    controller = MARLController(agents, env)

    while True:
        snapshot = bus.consume(
            "mission_stream", "marl_group", "marl_consumer", block=block_ms
        )
        rewards = bus.consume(
            "autonomy_stream", "marl_group", "marl_consumer", block=block_ms
        )

        if snapshot and rewards:
            # autonomy_stream may not always have "rewards"; fall back to agents.compute_rewards(snapshot)
            reward_map = rewards.get("rewards") if isinstance(rewards, dict) else None
            if reward_map is None:
                from agents.agent_rewards import compute_rewards
                reward_map = compute_rewards(snapshot)
            result = controller.step(snapshot, reward_map)
            bus.publish("marl_stream", result)
            if loop_sleep > 0:
                time.sleep(loop_sleep)


if __name__ == "__main__":
    main()
