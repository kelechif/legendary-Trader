class AgentMemory:
    def __init__(self):
        self.history = []

    def log(self, decision, intents):
        self.history.append({"decision": decision, "intents": intents})
