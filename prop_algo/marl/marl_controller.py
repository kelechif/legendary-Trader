class MARLController:
    def __init__(self, agents, env):
        self.agents = agents
        self.env = env

    def step(self, snapshot, rewards):
        actions = {}

        # 1. Agents act
        for agent in self.agents:
            obs = self.env.get_observation(snapshot, agent.name)
            action, confidence = agent.act(obs)
            actions[agent.name] = {"action": action, "confidence": confidence}
            agent.store(obs, action, rewards[agent.name])

        # 2. Train agents
        losses = {}
        for agent in self.agents:
            losses[agent.name] = agent.train()

        return {"actions": actions, "losses": losses}
