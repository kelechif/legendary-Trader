from typing import Protocol, runtime_checkable


@runtime_checkable
class AgentProtocol(Protocol):
    name: str

    def observe(self, snapshot): ...

    def act(self): ...

    def reward(self, value): ...


def negotiate(intents):
    votes = {}

    for agent, intent in intents.items():
        votes.setdefault(intent["intent"], 0)
        votes[intent["intent"]] += 1

    # highest voted intent wins
    decision = max(votes, key=votes.get)
    return decision
