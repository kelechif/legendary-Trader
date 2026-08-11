import numpy as np
from .backtester import Backtester
from .fitness import compute_fitness

def walkforward(df, params, splits=3):
    size = len(df) // splits
    fitness_scores = []

    for i in range(splits):
        segment = df.iloc[i*size:(i+1)*size]
        bt = Backtester(segment, params)
        pnl = bt.run()
        metrics = compute_fitness(pnl)
        fitness_scores.append(metrics["fitness"])

    return float(np.mean(fitness_scores))
