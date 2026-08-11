import torch
import torch.nn.functional as F

class RoutePredictor:
    def __init__(self, model):
        self.model = model

    def predict(self, features):
        x = torch.tensor(features, dtype=torch.float32)
        logits = self.model(x)
        probs = F.softmax(logits, dim=-1)
        routes = ["MARKET", "LIMIT", "VWAP"]
        return routes[int(torch.argmax(probs))]
