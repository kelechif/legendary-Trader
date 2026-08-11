def enforce_governance_rules(state):
    if "Switch to LIMIT_ONLY" in state["last_actions"]:
        return {"execution_mode": "LIMIT_ONLY"}

    return {"execution_mode": "ADAPTIVE"}
