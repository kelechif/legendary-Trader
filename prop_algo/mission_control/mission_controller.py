def apply_mission_actions(alerts):
    actions = []

    if "Liquidity stress" in alerts:
        actions.append("Switch execution to LIMIT_ONLY")

    if "System instability" in alerts:
        actions.append("Reduce position sizes")

    if "Anomaly overload" in alerts:
        actions.append("Throttle trading frequency")

    return actions
