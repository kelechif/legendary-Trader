import sys
import time
from pathlib import Path

# Minimal bootstrap so core.*/trading.*/risk.*/learning.* resolve from prop_algo/
_PROP_ALGO = Path(__file__).resolve().parent
_ROOT = _PROP_ALGO.parent
for _p in (_ROOT, _PROP_ALGO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.registry.registry import Registry
from core.adapters.factory import register_broker_accounts
from core.logging.logger import get_logger

# Phase 1
from trading.strategies.engine import StrategyEngine
from trading.risk_off.risk_off_engine import RiskOffEngine
from trading.execution.execution_optimizer import ExecutionOptimizer
from trading.multi_account.manager import MultiAccountManager
from trading.autopilot.autopilot_engine import AutopilotEngine

# Phase 2
from risk.risk_budget.risk_budget_engine import RiskBudgetEngine
from risk.cluster_detector.cluster_engine import ClusterDetector
from risk.liquidity_simulator.liquidity_engine import LiquidityEngine
from risk.anomaly_detector.anomaly_engine import AnomalyDetector
from risk.governance.governance_engine import GovernanceEngine
from risk.unified_core.unified_core_engine import UnifiedCoreEngine

# Phase 3
from learning.strategy_incubator.incubator_engine import StrategyIncubator
from learning.research_lab.lab_engine import ResearchLab
from learning.hyper_optimizer.hyper_engine import HyperOptimizer
from learning.meta_learning.meta_engine import MetaLearningEngine
from learning.synthetic_market.synthetic_engine import SyntheticMarketEngine

log = get_logger()


def should_learn(cycle):
    # Example: learn every 20 cycles
    return cycle % 20 == 0


def main():
    Path("state").mkdir(exist_ok=True)

    # Registry + accounts (BROKER_ADAPTER=mock|mt5|ctrader)
    registry = Registry()
    kind = register_broker_accounts(registry)
    multi = MultiAccountManager(registry)
    log.info(f"Broker adapter={kind}")
    log.info(
        f"Multi-account={'on' if multi.enabled() else 'off'} "
        f"accounts={multi.account_count()}"
    )

    # Phase 1 modules
    strategy_engine = StrategyEngine(registry)
    risk_off = RiskOffEngine()
    execution = ExecutionOptimizer(registry, multi_account=multi)
    autopilot = AutopilotEngine()

    # Phase 2 modules
    risk_budget = RiskBudgetEngine(registry)
    cluster_detector = ClusterDetector(registry)
    liquidity = LiquidityEngine(registry)
    anomaly = AnomalyDetector()
    governance = GovernanceEngine()
    unified = UnifiedCoreEngine()

    # Phase 3 modules
    incubator = StrategyIncubator(registry)
    lab = ResearchLab(registry)
    hyper = HyperOptimizer(registry)
    meta = MetaLearningEngine()
    synthetic = SyntheticMarketEngine(["EURUSD", "GBPUSD"])

    fitness_history = []
    cycle = 0

    while True:
        cycle += 1
        log.info(f"Cycle {cycle}")

        # -------------------------
        # PHASE 1 — TRADING
        # -------------------------
        market_data = registry.get_all_history()
        signals = strategy_engine.run(market_data)

        risk_factors = {
            acc: risk_off.compute(
                registry.accounts[acc]["adapter"].get_account_info(),
                market_data[(acc, "EURUSD")]
            )[0]
            for acc in registry.accounts
        }

        if autopilot.should_trade():
            exec_results = execution.run(signals, risk_factors)
            log.info(f"Executed trades: {exec_results}")

        # -------------------------
        # PHASE 2 — RISK & INTELLIGENCE
        # -------------------------
        budgets = risk_budget.compute()
        clusters = cluster_detector.detect()
        liquidity_state = liquidity.simulate_global()
        anomalies = anomaly.run(
            df=market_data[("ACC1", "EURUSD")],
            execution=execution.snapshot(),
            liquidity=liquidity_state
        )
        gov_state = governance.run(budgets, anomalies, clusters, liquidity_state)
        unified_state = unified.run(budgets, anomalies, clusters, liquidity_state, gov_state)

        # -------------------------
        # PHASE 3 — LEARNING & EVOLUTION
        # -------------------------
        if should_learn(cycle):
            log.info("Learning cycle triggered")

            # 1. Generate new candidate strategies
            incubator_state = incubator.run(num_new=3)
            candidates = incubator_state["candidates"]

            # 2. Evaluate candidates with real backtests
            fitness = lab.run(candidates)

            # 3. Hyper‑optimize parameters
            new_params = hyper.run(fitness, candidates)

            # 4. Track fitness history for meta‑learning
            for cid, f in fitness.items():
                fitness_history.append({"id": cid, "fitness": f["final"]})

            # 5. Meta‑learning: detect patterns
            meta_state = meta.run(fitness_history, anomalies, gov_state)

            # 6. Synthetic market generation (offline training)
            synthetic_env, corr = synthetic.generate()
            log.info(f"Synthetic market generated, corr={corr}")

            log.info(f"Learning results: best_params={hyper.state.state['best_params']}, meta_mode={meta_state['meta_mode']}")

        # -------------------------
        # LOGGING + SLEEP
        # -------------------------
        log.info(f"Unified mode: {unified_state['mode']}")
        log.info(f"Governance exec mode: {gov_state['rules']['execution_mode']}")
        log.info(f"Anomalies: {anomalies}")

        time.sleep(1)


if __name__ == "__main__":
    main()
