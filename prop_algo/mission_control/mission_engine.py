try:
    from infra.modes import NORMAL, SAFE_MODE
except ImportError:  # package import as prop_algo.* (pytest / non-Docker)
    from prop_algo.infra.modes import NORMAL, SAFE_MODE

from .telemetry_bus import TelemetryBus
from .mission_state import MissionState
from .mission_alerts import generate_alerts
from .mission_controller import apply_mission_actions
from .mission_dashboard import build_dashboard


class MissionControlEngine:
    def __init__(self):
        self.bus = TelemetryBus()
        self.state = MissionState()

    def run(self, probes):
        for key, value in probes.items():
            self.bus.push(key, value)

        snapshot = self.bus.snapshot()
        dashboard = build_dashboard(snapshot)
        alerts = generate_alerts(snapshot)
        actions = apply_mission_actions(alerts)

        self.state.state["last_snapshot"] = dashboard
        self.state.state["alerts"] = alerts
        self.state.state["global_mode"] = (
            SAFE_MODE if "System instability" in alerts else NORMAL
        )

        return {
            "dashboard": dashboard,
            "alerts": alerts,
            "actions": actions,
            "global_mode": self.state.state["global_mode"]
        }
