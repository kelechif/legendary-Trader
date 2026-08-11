import torch

def load_model(path):
    model = torch.load(path, map_location="cpu")
    model.eval()
    return model
