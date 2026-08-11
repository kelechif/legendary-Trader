import numpy as np


def fuse_signals(signals):
    vec = np.array([
        signals["risk_var"],
        signals["anomaly_count"],
        signals["cluster_count"],
        signals["liquidity"],
    ], dtype=float)
    return vec / (np.linalg.norm(vec) + 1e-9)
