def adapt_signals(risk_budgets, anomalies, clusters, liquidity, governance):
    return {
        "risk_var": max(risk_budgets.values()) - min(risk_budgets.values()),
        "anomaly_count": len(anomalies),
        "cluster_count": len(clusters),
        "liquidity": liquidity["global_liquidity"],
        "exec_mode": governance["rules"]["execution_mode"],
    }
