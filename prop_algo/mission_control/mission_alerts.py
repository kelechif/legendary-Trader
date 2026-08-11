def generate_alerts(snapshot):
    alerts = []

    if snapshot["risk"]["liquidity"]["global_liquidity"] < 0.5:
        alerts.append("Liquidity stress")

    if snapshot["unified"]["stability"] < 0.3:
        alerts.append("System instability")

    if len(snapshot["risk"]["anomalies"]) > 5:
        alerts.append("Anomaly overload")

    risk = snapshot.get("risk") if isinstance(snapshot.get("risk"), dict) else {}
    execution = (
        snapshot.get("execution")
        if isinstance(snapshot.get("execution"), dict)
        else {}
    )
    risk_off = execution.get("risk_off") or risk.get("risk_off") or {}
    if isinstance(risk_off, dict) and (
        risk_off.get("active") or execution.get("blocked")
    ):
        reason = (
            execution.get("block_reason")
            or risk_off.get("reason")
            or "risk_off"
        )
        alerts.append(f"Risk-off active: {reason}")
    else:
        unified = (
            snapshot.get("unified")
            if isinstance(snapshot.get("unified"), dict)
            else {}
        )
        if str(unified.get("mode") or "").upper() == "SAFE_MODE":
            alerts.append("Risk-off active: SAFE_MODE")

    return alerts
