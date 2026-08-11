def collect_global_metrics(risk_budgets, anomalies, clusters, liquidity):
    return {
        "risk_variance": max(risk_budgets.values()) - min(risk_budgets.values()),
        "anomaly_count": len(anomalies),
        "cluster_count": len(clusters),
        "liquidity": liquidity["global_liquidity"],
    }
