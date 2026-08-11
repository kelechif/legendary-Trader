import torch
import torch.nn as nn
import torch.nn.functional as F

class AgentPolicy(nn.Module):
    def __init__(self, input_dim, output_dim):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, 64)
        self.fc2 = nn.Linear(64, 64)
        self.fc3 = nn.Linear(64, output_dim)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return self.fc3(x)

    def intent_logits(self, observations):
        """observations → intent logits"""
        return observations_to_intent_logits(self, observations)


def observations_to_intent_logits(policy, observations):
    """Map observations → intent logits via the policy network."""
    x = torch.as_tensor(observations, dtype=torch.float32)
    if x.dim() == 1:
        x = x.unsqueeze(0)
    return policy(x)
