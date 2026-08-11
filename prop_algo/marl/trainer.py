import torch
import torch.optim as optim

class AgentTrainer:
    def __init__(self, policy, lr=1e-3):
        self.policy = policy
        self.optimizer = optim.Adam(policy.parameters(), lr=lr)

    def update(self, obs, action, reward):
        logits = self.policy(torch.tensor(obs, dtype=torch.float32))
        log_probs = torch.log_softmax(logits, dim=-1)
        loss = -log_probs[action] * reward

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return float(loss.item())
