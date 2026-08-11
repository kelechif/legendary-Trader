from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .websocket import router

try:
    from mission_control.control_state import (
        get_control_state,
        pause_autopilot,
        resume_autopilot,
        set_force_safe,
        set_trading_halt,
    )
except ImportError:
    from prop_algo.mission_control.control_state import (
        get_control_state,
        pause_autopilot,
        resume_autopilot,
        set_force_safe,
        set_trading_halt,
    )

_STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Mission UI",
    description=(
        "Mission Control dashboard and operator control plane. "
        "Local compose endpoints are auth-free — do not expose publicly."
    ),
)
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


class ForceSafeBody(BaseModel):
    active: bool = Field(True, description="When true, force SAFE note / pause")


class TradingHaltBody(BaseModel):
    active: bool = Field(True, description="When true, halt trading via control plane")


def _control_payload(state: dict[str, Any] | None = None) -> dict[str, Any]:
    s = state if state is not None else get_control_state()
    return {
        "autopilot_paused": bool(s.get("autopilot_paused")),
        "trading_halt": bool(s.get("trading_halt")),
        "force_safe": bool(s.get("force_safe")),
        "auth": "none",
        "note": "auth-free local compose control plane",
    }


@app.get("/")
def index():
    with open(_STATIC / "dashboard.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/control")
def api_control_status():
    """Current shared control-plane flags (Redis / file)."""
    return _control_payload()


@app.post("/api/control/autopilot/pause")
def api_pause_autopilot():
    """Pause autopilot without restarting containers."""
    return _control_payload(pause_autopilot())


@app.post("/api/control/autopilot/resume")
def api_resume_autopilot():
    """Resume autopilot (clears control-plane pause flag only)."""
    return _control_payload(resume_autopilot())


@app.post("/api/control/safe")
def api_force_safe(body: ForceSafeBody | None = None):
    """Toggle operator force-SAFE note (pauses autopilot as SAFE_MODE)."""
    active = True if body is None else bool(body.active)
    return _control_payload(set_force_safe(active))


@app.post("/api/control/halt")
def api_trading_halt(body: TradingHaltBody | None = None):
    """Toggle trading_halt control-plane flag."""
    active = True if body is None else bool(body.active)
    return _control_payload(set_trading_halt(active))
