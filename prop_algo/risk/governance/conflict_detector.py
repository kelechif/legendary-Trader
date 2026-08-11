def detect_conflicts(metrics):
    conflicts = []

    if metrics["risk_variance"] > 0.5:
        conflicts.append("Risk imbalance")

    if metrics["anomaly_count"] > 3:
        conflicts.append("High anomaly pressure")

    if metrics["cluster_count"] > 0:
        conflicts.append("Exposure clustering")

    if metrics["liquidity"] < 0.6:
        conflicts.append("Liquidity stress")

    return conflicts
