try:
    from infra.modes import NORMAL, SAFE_MODE
except ImportError:  # package import as prop_algo.* (pytest / non-Docker)
    from prop_algo.infra.modes import NORMAL, SAFE_MODE

from .control_state import get_control_state, mode_override_from_control
from .telemetry_bus import TelemetryBus
from .mission_state import MissionState
from .mission_alerts import generate_alerts
from .mission_controller import apply_mission_actions
from .mission_dashboard import build_dashboard


class MissionControlEngine:
    def __init__(self):
        self.bus = TelemetryBus()
        self.state = MissionState()

    def run(self, probes, control=None):
        for key, value in probes.items():
            self.bus.push(key, value)

        snapshot = self.bus.snapshot()
        dashboard = build_dashboard(snapshot)
        alerts = generate_alerts(snapshot)
        actions = apply_mission_actions(alerts)

        stream_mode = SAFE_MODE if "System instability" in alerts else NORMAL
        ctrl = control if control is not None else get_control_state()
        override_mode, override_reason = mode_override_from_control(ctrl)
        if override_mode:
            global_mode = override_mode
            mode_reason = override_reason
        else:
            global_mode = stream_mode
            mode_reason = (
                "system_instability" if stream_mode == SAFE_MODE else "normal"
            )

        self.state.state["last_snapshot"] = dashboard
        self.state.state["alerts"] = alerts
        self.state.state["global_mode"] = global_mode
        self.state.state["global_mode_reason"] = mode_reason
        self.state.state["stream_global_mode"] = stream_mode

        return {
            "dashboard": dashboard,
            "alerts": alerts,
            "actions": actions,
            "global_mode": global_mode,
            "global_mode_reason": mode_reason,
            "stream_global_mode": stream_mode,
        }
