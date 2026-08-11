def _marl_status(marl):
    if not isinstance(marl, dict):
        return None
    actions = marl.get("actions")
    if isinstance(actions, dict) and actions:
        return f"agents={len(actions)}"
    if "status" in marl:
        return str(marl["status"])
    return "active"


def _simulation_status(simulation):
    if not isinstance(simulation, dict):
        return None
    status = simulation.get("status")
    steps = simulation.get("steps")
    if status is not None and steps is not None:
        return f"{status} ({steps} steps)"
    if status is not None:
        return str(status)
    return "active"


def _risk_off_status(snapshot):
    risk = snapshot.get("risk") if isinstance(snapshot.get("risk"), dict) else {}
    execution = (
        snapshot.get("execution")
        if isinstance(snapshot.get("execution"), dict)
        else {}
    )
    off = execution.get("risk_off") or risk.get("risk_off") or {}
    if not isinstance(off, dict):
        return None
    if off.get("enabled") is False:
        return "off"
    if off.get("active") or execution.get("blocked"):
        reason = (
            execution.get("block_reason")
            or off.get("reason")
            or "risk_off"
        )
        return f"ACTIVE ({reason})"
    return "normal"


def build_dashboard(snapshot):
    market = snapshot.get("market") or {}
    account = market.get("ACC1") or (next(iter(market.values())) if market else {})
    autonomy = snapshot.get("autonomy") if isinstance(snapshot.get("autonomy"), dict) else None
    return {
        "equity": account.get("equity"),
        "risk_mode": snapshot["governance"]["rules"]["execution_mode"],
        "unified_mode": snapshot["unified"]["mode"],
        "anomalies": snapshot["risk"]["anomalies"],
        "liquidity": snapshot["risk"]["liquidity"]["global_liquidity"],
        "learning_meta_mode": snapshot["learning"]["meta_mode"],
        "adapter": snapshot.get("adapter"),
        "autonomy_mode": (autonomy or {}).get("global_mode"),
        "marl_status": _marl_status(snapshot.get("marl")),
        "simulation_status": _simulation_status(snapshot.get("simulation")),
        "risk_off": _risk_off_status(snapshot),
    }
