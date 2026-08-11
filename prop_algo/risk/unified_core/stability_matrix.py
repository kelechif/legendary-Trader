def compute_stability(vec):
    return max(0.0, min(1.0, 1.0 - vec[0] - vec[1] * 0.2))
