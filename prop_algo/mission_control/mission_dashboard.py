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
    if off.get("active"):
        reason = (
            execution.get("block_reason")
            or off.get("reason")
            or "risk_off"
        )
        return f"ACTIVE ({reason})"
    # Autopilot-only blocks must not paint the risk-off tile ACTIVE.
    br = str(execution.get("block_reason") or "")
    if execution.get("blocked") and br and br not in (
        "autopilot_off",
        "autopilot_paused",
    ):
        return f"ACTIVE ({br})"
    return "normal"


def _autopilot_status(snapshot):
    execution = (
        snapshot.get("execution")
        if isinstance(snapshot.get("execution"), dict)
        else {}
    )
    ap = execution.get("autopilot") or {}
    if not isinstance(ap, dict) or not ap:
        return None
    if ap.get("enabled") is False or ap.get("state") == "off":
        return "off"
    if ap.get("paused") or ap.get("allow") is False:
        return f"paused ({ap.get('reason') or 'paused'})"
    return "running"


def _multi_account_fields(snapshot):
    multi = snapshot.get("multi_account")
    market = snapshot.get("market") or {}
    if isinstance(multi, dict) and multi:
        accounts = multi.get("accounts")
        if not isinstance(accounts, dict):
            accounts = market if isinstance(market, dict) else {}
        count = multi.get("account_count")
        if count is None:
            count = len(accounts)
        return int(count), accounts
    if isinstance(market, dict):
        return len(market), market
    return 0, {}


def build_dashboard(snapshot):
    market = snapshot.get("market") or {}
    account = market.get("ACC1") or (next(iter(market.values())) if market else {})
    autonomy = snapshot.get("autonomy") if isinstance(snapshot.get("autonomy"), dict) else None
    account_count, accounts = _multi_account_fields(snapshot)
    return {
        "equity": account.get("equity"),
        "risk_mode": snapshot["governance"]["rules"]["execution_mode"],
        "unified_mode": snapshot["unified"]["mode"],
        "anomalies": snapshot["risk"]["anomalies"],
        "liquidity": snapshot["risk"]["liquidity"]["global_liquidity"],
        "learning_meta_mode": snapshot["learning"]["meta_mode"],
        "adapter": snapshot.get("adapter"),
        "account_count": account_count,
        "accounts": accounts,
        "autonomy_mode": (autonomy or {}).get("global_mode"),
        "marl_status": _marl_status(snapshot.get("marl")),
        "simulation_status": _simulation_status(snapshot.get("simulation")),
        "risk_off": _risk_off_status(snapshot),
        "autopilot": _autopilot_status(snapshot),
    }
