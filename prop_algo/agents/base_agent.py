class BaseAgent:
    def __init__(self, name):
        self.name = name
        self.state = {}
        self.memory = []
        self.last_reward = 0

    def observe(self, snapshot):
        raise NotImplementedError

    def act(self):
        raise NotImplementedError

    def reward(self, value):
        self.last_reward = value
        self.memory.append(value)
