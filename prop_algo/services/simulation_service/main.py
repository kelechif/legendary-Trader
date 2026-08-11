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
from marl.marl_controller import MARLController
from marl.policy import AgentPolicy
from marl.trainer import AgentTrainer
from marl.marl_agent import MARLAgent
from marl.environment import MultiAgentEnv
from simulation.sim_env import SimulationEnv
from marl.marl_sim_loop import MARLSimLoop


def main():
    bus = Stream()
    # Cap CPU: avoid tight-looping torch sims between batches.
    loop_sleep = float(os.getenv("SIMULATION_LOOP_SLEEP", "2"))
    steps = int(os.getenv("SIMULATION_STEPS", "50"))
    threads = max(1, int(os.getenv("SIMULATION_TORCH_THREADS", "1")))
    try:
        import torch

        torch.set_num_threads(threads)
        torch.set_num_interop_threads(1)
    except Exception:
        pass

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

    controller = MARLController(agents, MultiAgentEnv())
    sim_env = SimulationEnv()
    sim_loop = MARLSimLoop(controller, sim_env)

    # Continuous loop so the container stays healthy under restart policies.
    while True:
        sim_loop.run(steps=steps)
        bus.publish(
            "simulation_stream",
            {"status": "completed", "steps": steps},
        )
        if loop_sleep > 0:
            time.sleep(loop_sleep)


if __name__ == "__main__":
    main()
