"""Auto-loop: ZeroDTERegime on live 5m bars → Moomoo 0DTE vertical."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from services.execution_engine.moomoo_options_broker import use_moomoo_options
from services.execution_engine.ts_bridge import trading_halted
from services.options_engine.moomoo_intraday import attach_vix, fetch_intraday_candles
from services.options_engine.zero_dte_executor import check_and_close_stops, execute_0dte_signal, session_status
from services.shared.config import DATA_DIR, OPTIONS_CFG, get_strategy_params
from services.shared import log_channels
from services.strategy_engine.registry import choose_signal


@dataclass
class LoopState:
    session_date: str = ""
    tickets_today: int = 0
    last_bar_key: str = ""
    last_signal: str = "HOLD"
    history: list = field(default_factory=list)
    open_trades: list = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> LoopState:
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})
        except (json.JSONDecodeError, TypeError):
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.__dict__, indent=2), encoding="utf-8")

    def reset_if_new_day(self) -> None:
        today = date.today().isoformat()
        if self.session_date != today:
            self.session_date = today
            self.tickets_today = 0
            self.last_bar_key = ""
            self.last_signal = "HOLD"


def _state_path() -> Path:
    rel = OPTIONS_CFG.get("moomoo", {}).get("loop", {}).get("state_file", "0dte_loop_state.json")
    p = Path(rel)
    if p.is_absolute():
        return p
    if str(rel).startswith("data/"):
        return DATA_DIR.parent / rel
    return DATA_DIR / rel


def _signal_to_direction(signal: str) -> str | None:
    if signal == "BUY":
        return "bullish"
    if signal == "SELL":
        return "bearish"
    return None


def run_once(state: LoopState | None = None) -> dict:
    """Single iteration: fetch bars, evaluate regime, maybe execute."""
    if not use_moomoo_options():
        return {"status": "error", "reason": "moomoo_options_not_configured"}

    state = state or LoopState.load(_state_path())
    state.reset_if_new_day()

    if trading_halted():
        return {"status": "skipped", "reason": "kill_switch", "state": state.__dict__}

    candles = fetch_intraday_candles()
    if not candles:
        return {"status": "skipped", "reason": "no_candles", "state": state.__dict__}

    candles = attach_vix(candles)
    params = get_strategy_params("ZeroDTERegime") or {}
    signal = choose_signal("ZeroDTERegime", [], params, candles)
    last = candles[-1]
    bar_key = last.get("time_key", str(last.get("time_hhmm", "")))
    spot = float(last.get("close", 0))

    result_stops = None
    if state.open_trades:
        state.open_trades, stopped = check_and_close_stops(last, state.open_trades)
        if stopped:
            result_stops = stopped

    result = {
        "status": "idle",
        "signal": signal,
        "bar_key": bar_key,
        "close": last.get("close"),
        "time_hhmm": last.get("time_hhmm"),
        "tickets_today": state.tickets_today,
        "session": session_status(),
        "stopped": result_stops,
        "open_trades": len(state.open_trades),
    }

    direction = _signal_to_direction(signal)
    if not direction:
        state.last_signal = signal
        state.save(_state_path())
        result["state"] = state.__dict__
        return result

    if bar_key == state.last_bar_key and signal == state.last_signal:
        result["status"] = "skipped"
        result["reason"] = "duplicate_bar_signal"
        result["state"] = state.__dict__
        return result

    exec_result = execute_0dte_signal(direction, tickets_used=state.tickets_today)
    result["execution"] = exec_result
    result["status"] = exec_result.get("status", "unknown")

    if exec_result.get("status") in ("ok", "simulated"):
        state.tickets_today += 1
        state.last_bar_key = bar_key
        state.last_signal = signal
        short = exec_result.get("short_leg", {})
        long = exec_result.get("long_leg", {})
        state.open_trades.append(
            {
                "entry_time": bar_key,
                "direction": direction,
                "credit": exec_result.get("credit"),
                "credit_source": exec_result.get("credit_source"),
                "short_strike": short.get("strike"),
                "long_strike": long.get("strike"),
                "short_code": short.get("code"),
                "long_code": long.get("code"),
                "spot_entry": spot,
            }
        )
        state.history.append(
            {
                "time": datetime.now().isoformat(),
                "signal": signal,
                "direction": direction,
                "bar_key": bar_key,
                "execution": exec_result,
            }
        )
        log_channels.log_event(
            "execution",
            "0dte_loop_fire",
            signal=signal,
            direction=direction,
            tickets=state.tickets_today,
        )
    elif exec_result.get("reason") == "outside_window":
        result["status"] = "waiting_window"
    else:
        state.last_signal = signal

    state.save(_state_path())
    result["state"] = state.__dict__
    return result


def run_loop(interval_sec: float | None = None, max_iterations: int | None = None) -> None:
    """Poll until Ctrl+C or max_iterations."""
    loop_cfg = OPTIONS_CFG.get("moomoo", {}).get("loop", {})
    interval = float(interval_sec or loop_cfg.get("interval_sec", 60))
    state = LoopState.load(_state_path())
    n = 0

    log_channels.log_event("execution", "0dte_loop_start", interval_sec=interval)
    while True:
        n += 1
        if max_iterations is not None and n > max_iterations:
            break
        try:
            outcome = run_once(state)
            state = LoopState.load(_state_path())
            log_channels.log_event("execution", "0dte_loop_tick", **{k: outcome.get(k) for k in ("status", "signal", "reason")})
        except Exception as exc:
            log_channels.log_event("execution", "0dte_loop_error", error=str(exc))
        time.sleep(interval)
