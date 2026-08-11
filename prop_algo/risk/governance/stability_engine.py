def apply_stability_actions(conflicts, state):
    actions = []

    for c in conflicts:
        if "Risk imbalance" in c:
            actions.append("Rebalance risk budgets")

        if "anomaly" in c:
            actions.append("Reduce execution speed")

        if "cluster" in c:
            actions.append("Reduce correlated exposure")

        if "Liquidity" in c:
            actions.append("Switch to LIMIT_ONLY")

    state["last_actions"] = actions
    return actions
