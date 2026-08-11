from .agent_protocol import negotiate
from .agent_memory import AgentMemory
from .agent_rewards import compute_rewards


class AgentController:
    def __init__(self, agents):
        self.agents = agents
        self.memory = AgentMemory()

    def step(self, snapshot):
        intents = {}

        for agent in self.agents:
            agent.observe(snapshot)
            intents[agent.name] = agent.act()

        decision = negotiate(intents)
        rewards = compute_rewards(snapshot)

        for agent in self.agents:
            agent.reward(rewards[agent.name])

        self.memory.log(decision, intents)

        return {"decision": decision, "rewards": rewards}
