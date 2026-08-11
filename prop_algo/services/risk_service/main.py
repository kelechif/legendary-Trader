import sys
from pathlib import Path

_PROP_ALGO = Path(__file__).resolve().parents[2]
_ROOT = _PROP_ALGO.parent
for _p in (_ROOT, _PROP_ALGO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.adapters.mock_adapter import MockAdapter
from core.registry.registry import Registry
from infra.metrics import Metrics
from infra.stream import Stream
from risk.anomaly_detector.anomaly_engine import AnomalyDetector
from risk.cluster_detector.cluster_engine import ClusterDetector
from risk.liquidity_simulator.liquidity_engine import LiquidityEngine
from risk.risk_budget.risk_budget_engine import RiskBudgetEngine


def main():
    registry = Registry()
    registry.register_account("ACC1", MockAdapter("ACC1"))
    registry.register_account("ACC2", MockAdapter("ACC2"))
    risk_budget = RiskBudgetEngine(registry)
    cluster = ClusterDetector(registry)
    liquidity = LiquidityEngine(registry)
    anomaly = AnomalyDetector()

    bus = Stream()
    metrics = Metrics(8001)

    while True:
        signals = bus.consume("strategy_signal_stream", "risk_group", "risk_consumer")
        if not signals:
            continue

        budgets = risk_budget.compute()
        clusters = cluster.detect()
        liquidity_state = liquidity.simulate_global()
        anomalies = anomaly.run()

        risk = {
            "budgets": budgets,
            "clusters": clusters,
            "liquidity": liquidity_state,
            "anomalies": anomalies
        }

        metrics.liquidity.set(risk["liquidity"]["global_liquidity"])
        metrics.anomaly_count.set(len(risk["anomalies"]))

        bus.publish("risk_stream", risk)


if __name__ == "__main__":
    main()
