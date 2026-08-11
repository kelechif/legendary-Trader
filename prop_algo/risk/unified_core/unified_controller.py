from infra.modes import ADAPTIVE, NORMAL, SAFE_MODE


def control_unified(stability, coherence):
    if stability < 0.3:
        return {"mode": SAFE_MODE, "actions": ["Reduce risk"]}
    if coherence < 0.5:
        return {"mode": ADAPTIVE, "actions": ["Align subsystems"]}
    return {"mode": NORMAL, "actions": []}
