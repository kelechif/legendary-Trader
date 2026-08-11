import random
import numpy as np
from .backtester import Backtester
from .fitness import compute_fitness

def robustness_test(df, params, trials=5):
    scores = []
    for _ in range(trials):
        perturbed = df.copy()
        perturbed["close"] = perturbed["close"] * (1 + random.uniform(-0.001, 0.001))
        bt = Backtester(perturbed, params)
        pnl = bt.run()
        metrics = compute_fitness(pnl)
        scores.append(metrics["fitness"])
    return float(np.mean(scores))
