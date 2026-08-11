import random
import torch

class MARLAgent:
    def __init__(self, name, policy, trainer):
        self.name = name
        self.policy = policy
        self.trainer = trainer
        self.experience = []

    def act(self, obs):
        logits = self.policy(torch.tensor(obs, dtype=torch.float32))
        probs = torch.softmax(logits, dim=-1)
        action = int(torch.multinomial(probs, 1))
        return action, probs[action].item()

    def store(self, obs, action, reward):
        self.experience.append((obs, action, reward))

    def train(self):
        losses = []
        for obs, action, reward in self.experience:
            loss = self.trainer.update(obs, action, reward)
            losses.append(loss)
        self.experience = []
        return losses
