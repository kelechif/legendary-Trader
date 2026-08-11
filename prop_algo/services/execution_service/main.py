import sys
import time
from pathlib import Path

_PROP_ALGO = Path(__file__).resolve().parents[2]
_ROOT = _PROP_ALGO.parent
for _p in (_ROOT, _PROP_ALGO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.adapters.factory import register_broker_accounts
from core.registry.registry import Registry
from infra.metrics import Metrics
from infra.stream import Stream
from neural_execution import NeuralExecutionEngine
from trading.execution.execution_optimizer import ExecutionOptimizer
from trading.risk_off import RiskOffEngine, execution_gate, merge_risk_factors


def _mean_budget(budgets) -> float:
    if not isinstance(budgets, dict) or not budgets:
        return 1.0
    vals = []
    for v in budgets.values():
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    return sum(vals) / len(vals) if vals else 1.0


def _feature_vectors(signals, risk, gov):
    """Build compact numeric features for neural / heuristic predictors."""
    budgets = (risk or {}).get("budgets") or {}
    liquidity = ((risk or {}).get("liquidity") or {}).get("global_liquidity", 0.5)
    anomalies = (risk or {}).get("anomalies") or []
    rules = (gov or {}).get("rules") or {}
    mode = str(rules.get("execution_mode", "NORMAL")).upper()
    mode_score = {"NORMAL": 1.0, "LIMIT_ONLY": 0.4, "HALT": 0.0}.get(mode, 0.7)

    n_signals = len(signals) if isinstance(signals, dict) else 0
    market_features = [float(n_signals), float(liquidity)]
    risk_features = [
        _mean_budget(budgets),
        float(len(anomalies)),
        float(liquidity),
    ]
    gov_features = [mode_score, float(len((gov or {}).get("conflicts") or []))]
    return market_features, risk_features, gov_features


def main():
    registry = Registry()
    kind = register_broker_accounts(registry)
    print(f"execution_service broker adapter={kind}", flush=True)
    exec_engine = ExecutionOptimizer(registry)
    bus = Stream()
    metrics = Metrics(8002)

    neural_on = NeuralExecutionEngine.enabled()
    neural_engine = NeuralExecutionEngine.build() if neural_on else None
    print(
        f"execution_service neural_execution="
        f"{'on' if neural_on else 'off'}"
        f" backend={getattr(neural_engine, 'backend', 'disabled')}",
        flush=True,
    )
    print(
        f"execution_service risk_off="
        f"{'on' if RiskOffEngine.enabled() else 'off'}",
        flush=True,
    )

    while True:
        signals = bus.consume("strategy_signal_stream", "exec_group", "exec_consumer")
        risk = bus.consume("risk_stream", "exec_group", "exec_consumer")
        gov = bus.consume("governance_stream", "exec_group", "exec_consumer")
        unified = bus.consume("unified_core_stream", "exec_group", "exec_consumer")

        if not signals or not risk or not gov:
            continue

        risk_off = (risk or {}).get("risk_off") or {}
        rules = (gov or {}).get("rules") or {}
        gov_mode = str(rules.get("execution_mode", ""))
        unified_mode = str((unified or {}).get("mode") or "")

        blocked, gate_reason = execution_gate(
            risk_off,
            unified_mode=unified_mode or None,
            gov_mode=gov_mode or None,
        )

        advice = {
            "route": "MARKET",
            "slippage": 0.0005,
            "volatility": 0.001,
            "size": 0.1,
            "backend": "disabled",
        }
        if neural_engine is not None and not blocked:
            try:
                m_f, r_f, g_f = _feature_vectors(signals, risk, gov)
                advice = neural_engine.run(m_f, r_f, g_f)
            except Exception as exc:
                # Never take down the service for a predictor failure.
                print(f"neural_execution fallback: {exc}", flush=True)
                advice = {
                    "route": "MARKET",
                    "slippage": 0.0005,
                    "volatility": 0.001,
                    "size": 0.1,
                    "backend": "error_fallback",
                }

        # Governance LIMIT_ONLY overrides neural MARKET preference.
        if str(rules.get("execution_mode", "")).upper() == "LIMIT_ONLY":
            advice["route"] = "LIMIT"

        risk_factors = merge_risk_factors(risk.get("budgets"), risk_off)
        if blocked:
            advice["size"] = 0.0
            orders = []
            latency_value = 0.0
        else:
            t0 = time.perf_counter()
            orders = exec_engine.run(
                signals,
                risk_factors,
                size=advice.get("size", 0.1),
                route=advice.get("route", "MARKET"),
            )
            latency_value = time.perf_counter() - t0
        metrics.exec_latency.set(latency_value)

        off_active = bool(blocked or risk_off.get("active"))
        payload = {
            "route": advice.get("route", "MARKET"),
            "slippage": float(advice.get("slippage", 0.0005)),
            "volatility": float(advice.get("volatility", 0.001)),
            "size": float(advice.get("size", 0.1)),
            "backend": advice.get("backend", "disabled"),
            "neural_enabled": bool(neural_on),
            "orders": orders,
            "risk_off": {
                "enabled": bool(risk_off.get("enabled", RiskOffEngine.enabled())),
                "active": off_active,
                "reason": gate_reason
                if off_active
                else str(risk_off.get("reason") or "normal"),
                "factors": risk_factors,
            },
            "blocked": bool(blocked),
            "block_reason": gate_reason if blocked else None,
        }
        bus.publish("execution_stream", payload)


if __name__ == "__main__":
    main()
