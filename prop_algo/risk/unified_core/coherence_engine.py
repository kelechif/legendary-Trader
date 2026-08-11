def compute_coherence(signals):
    coherence = 1.0
    if signals["exec_mode"] == "LIMIT_ONLY":
        coherence -= 0.2
    if signals["anomaly_count"] > 3:
        coherence -= 0.3
    return max(0.0, coherence)
