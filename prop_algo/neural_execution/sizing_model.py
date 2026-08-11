import torch

class SizingModel:
    def __init__(self, model):
        self.model = model

    def predict(self, features):
        x = torch.tensor(features, dtype=torch.float32)
        return float(self.model(x))
