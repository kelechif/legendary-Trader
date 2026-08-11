def generate_alerts(snapshot):
    alerts = []

    if snapshot["risk"]["liquidity"]["global_liquidity"] < 0.5:
        alerts.append("Liquidity stress")

    if snapshot["unified"]["stability"] < 0.3:
        alerts.append("System instability")

    if len(snapshot["risk"]["anomalies"]) > 5:
        alerts.append("Anomaly overload")

    return alerts
