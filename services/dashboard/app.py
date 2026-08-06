from flask import Flask, jsonify, render_template, request

from services.execution_engine import paper_trader
from services.execution_engine.performance import aggregate_metrics, compute_metrics
from services.execution_engine.portfolio import build_snapshot
from services.market_data import state
from services.market_data.candles import candles_with_forming
from services.market_data.moomoo_feed import feed_status, get_daily_candles, load_cached_candles
from services.risk_governance import alerts
from services.shared.config import ASSETS, IS_EQUITY_MODE, MARKET_DATA_PROVIDER, STRATEGIES, TRADING_CFG, get_strategy_params
from services.shared import metrics
from services.strategy_engine import registry as strategy_registry
from services.training_engine.backtest import run_backtest, run_backtest_daily
from services.training_engine.universe_backtest import run_backtest_universe
from services.training_engine.wfo import run_walk_forward

import os

_dashboard_dir = os.path.dirname(os.path.abspath(__file__))


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(_dashboard_dir, "templates"),
        static_folder=os.path.join(_dashboard_dir, "static"),
    )

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/data")
    def data():
        timeframe = request.args.get("timeframe", "1d" if IS_EQUITY_MODE else "1m")

        with state.lock:
            prices = {a: list(state.price_history[a]) for a in ASSETS}
            candles = {
                a: {
                    tf: candles_with_forming(
                        state.candle_history[a][tf],
                        state.candle_buffers[a][tf],
                    )
                    for tf in state.candle_history[a]
                }
                for a in ASSETS
            }
            order_books = {a: dict(state.order_books[a]) for a in ASSETS}
            latest_prices = dict(state.latest_price)

        with paper_trader.lock:
            trades = {a: list(paper_trader.trade_history[a]) for a in ASSETS}
            equity = {a: list(paper_trader.equity_curve[a]) for a in ASSETS}
            strategy = paper_trader.current_strategy
            positions = dict(paper_trader.position)
            equities = dict(paper_trader.current_equity)
            share_map = dict(paper_trader.shares)
            cash = paper_trader.cash
            nav = paper_trader.portfolio_nav(dict(latest_prices))

        if IS_EQUITY_MODE and paper_trader.portfolio_equity_curve:
            performance = {
                "portfolio": compute_metrics(
                    paper_trader.portfolio_equity_curve,
                    [t for ts in trades.values() for t in ts],
                    periods_per_year=252,
                ),
                "assets": {},
            }
        else:
            equity_len = max((len(equity[a]) for a in ASSETS), default=0)
            performance = aggregate_metrics(equity, trades)

        portfolio = build_snapshot(
            latest_prices, positions, equities, trades,
            shares=share_map, cash=cash, nav=nav,
        )

        return jsonify(
            {
                "prices": prices,
                "candles": candles,
                "timeframe": timeframe,
                "trades": trades,
                "equity": equity if not IS_EQUITY_MODE else {"PORTFOLIO": paper_trader.portfolio_equity_curve},
                "equity_labels": list(
                    range(
                        len(paper_trader.portfolio_equity_curve)
                        if IS_EQUITY_MODE
                        else max((len(equity[a]) for a in ASSETS), default=0)
                    )
                ),
                "strategy": strategy,
                "portfolio": portfolio,
                "performance": performance,
                "order_books": order_books,
                "alerts": alerts.get_recent(30),
                "alert_config": alerts.get_config(),
                "trading_mode": "equity" if IS_EQUITY_MODE else "tick",
                "safe_mode": TRADING_CFG.get("safe_mode", False),
                "assets": ASSETS,
                "asset_count": len(ASSETS),
                "signals": paper_trader.get_last_scan(),
                "system_metrics": metrics.snapshot(),
                "feed_status": feed_status() if IS_EQUITY_MODE else {"provider": MARKET_DATA_PROVIDER, "ready": True},
            }
        )

    @app.route("/api/signals")
    def api_signals():
        from services.strategy_engine.signal_scanner import scan_universe, summarize_scan, rank_entry_candidates

        strategy = paper_trader.current_strategy
        params = paper_trader.get_params(strategy)
        scanned = scan_universe(strategy, params)
        return jsonify(
            {
                "strategy": strategy,
                "summary": summarize_scan(scanned),
                "entries": rank_entry_candidates(scanned)[:20],
                "exits": [r for r in scanned if r["signal"] == "SELL"][:20],
                "by_regime": {
                    "bull": [r for r in scanned if r.get("regime_label") == "BULL"][:20],
                    "bear": [r for r in scanned if r.get("regime_label") == "BEAR"][:20],
                    "sideways": [r for r in scanned if r.get("regime_label") == "SIDEWAYS"][:20],
                },
            }
        )

    @app.route("/api/strategies")
    def api_strategies():
        strategy = paper_trader.current_strategy
        return jsonify(
            {
                "strategies": strategy_registry.list_strategies(),
                "strategy": strategy,
                "schemas": strategy_registry.schemas(),
                "params": paper_trader.get_params(strategy),
            }
        )

    @app.route("/api/strategy/<name>", methods=["POST"])
    def api_set_strategy(name):
        strategy = paper_trader.set_strategy(name, STRATEGIES)
        return jsonify({"strategy": strategy, "params": paper_trader.get_params(strategy)})

    @app.route("/api/strategy/<name>/params", methods=["POST", "GET"])
    def api_strategy_params(name):
        if request.method == "GET":
            return jsonify({"strategy": name, "params": paper_trader.get_params(name), "schema": strategy_registry.schemas().get(name, {})})
        params = request.get_json(silent=True) or {}
        updated = paper_trader.set_params(name, params)
        return jsonify({"strategy": name, "params": updated})

    @app.route("/api/backtest", methods=["POST"])
    def api_backtest():
        body = request.get_json(silent=True) or {}
        strategy = body.get("strategy", paper_trader.current_strategy)
        asset = body.get("asset", ASSETS[0])
        params = body.get("params") or paper_trader.get_params(strategy)
        strategy_obj = strategy_registry.get(strategy)

        use_daily = IS_EQUITY_MODE or (
            strategy_obj and getattr(strategy_obj, "requires_candles", False)
        )

        if use_daily:
            candles = get_daily_candles(asset)
            if len(candles) < 220:
                return jsonify({"error": f"Need 220+ daily bars for {asset} (have {len(candles)})"}), 400
            result = run_backtest_daily(
                candles,
                strategy,
                ticker=asset,
                params=params,
                initial_equity=float(body.get("initial_equity", 100000)),
                max_positions=int(TRADING_CFG.get("max_positions", 10)),
                slippage_bps=float(TRADING_CFG.get("slippage_bps", 5)),
                commission=float(TRADING_CFG.get("commission", 1.0)),
            )
        else:
            with state.lock:
                prices = list(state.price_history.get(asset, []))
            if not prices:
                return jsonify({"error": f"No price history for {asset}"}), 400
            result = run_backtest(prices, strategy, params)

        if "error" in result:
            return jsonify(result), 400

        metrics.increment("backtests_run")
        return jsonify(result)

    @app.route("/api/backtest/universe", methods=["POST"])
    def api_backtest_universe():
        body = request.get_json(silent=True) or {}
        strategy = body.get("strategy", paper_trader.current_strategy)
        params = body.get("params") or paper_trader.get_params(strategy)
        limit = int(body.get("limit", 0))

        tickers = ASSETS[:limit] if limit else ASSETS
        ticker_candles = {}
        for ticker in tickers:
            candles = get_daily_candles(ticker) or load_cached_candles(ticker, params)
            if len(candles) >= 220:
                ticker_candles[ticker] = candles

        if not ticker_candles:
            return jsonify({"error": "No kline data. Run run_daily.py first."}), 400

        result = run_backtest_universe(
            ticker_candles,
            strategy,
            params=params,
            initial_equity=float(body.get("initial_equity", 100000)),
            max_positions=int(TRADING_CFG.get("max_positions", 10)),
            slippage_bps=float(TRADING_CFG.get("slippage_bps", 5)),
            commission=float(TRADING_CFG.get("commission", 1.0)),
            regime_cfg=TRADING_CFG.get("regime", {}),
        )
        if "error" in result:
            return jsonify(result), 400

        metrics.increment("backtests_run")
        return jsonify(result)

    @app.route("/api/wfo", methods=["POST"])
    def api_wfo():
        body = request.get_json(silent=True) or {}
        strategy = body.get("strategy", paper_trader.current_strategy)
        params = body.get("params") or paper_trader.get_params(strategy)
        limit = int(body.get("limit", 30))
        max_folds = int(body.get("folds", 2))

        from services.market_data.moomoo_feed import load_raw_kline_cache
        from services.training_engine.wfo_grids import GRIDS

        param_grid = body.get("param_grid") or GRIDS.get(body.get("grid", "expanded"), GRIDS["expanded"])

        tickers = ASSETS[:limit] if limit else ASSETS
        raw_dfs = load_raw_kline_cache(tickers)
        if not raw_dfs:
            return jsonify({"error": "No kline data. Run run_daily.py first."}), 400

        from services.training_engine.wfo import collect_trading_dates, generate_rolling_folds, build_ticker_candles

        probe = build_ticker_candles(raw_dfs, params)
        dates = collect_trading_dates(probe)
        folds = generate_rolling_folds(dates)[:max_folds]

        result = run_walk_forward(
            raw_dfs,
            strategy,
            params,
            param_grid,
            folds=folds,
            max_combos=int(body.get("max_combos", 64)),
            initial_equity=float(body.get("initial_equity", 100000)),
            max_positions=int(TRADING_CFG.get("max_positions", 10)),
            slippage_bps=float(TRADING_CFG.get("slippage_bps", 5)),
            commission=float(TRADING_CFG.get("commission", 1.0)),
            regime_cfg=TRADING_CFG.get("regime", {}),
        )
        if "error" in result and not result.get("fold_results"):
            return jsonify(result), 400

        metrics.increment("backtests_run")
        return jsonify(result)

    @app.route("/api/trading/account")
    def api_trading_account():
        from services.execution_engine.moomoo_broker import get_account_snapshot, use_moomoo_broker

        guard = paper_trader.get_trading_guard_status()
        if not use_moomoo_broker():
            return jsonify(
                {
                    "broker": "internal",
                    "safe_mode": TRADING_CFG.get("safe_mode", True),
                    **guard,
                }
            )

        snap = get_account_snapshot()
        snap.update(
            {
                "drawdown_halt_active": guard["drawdown_halt_active"],
                "can_buy": guard["can_buy"],
                "nav": guard["nav"],
                "peak_nav": guard["peak_nav"],
                "drawdown_pct": guard["drawdown_pct"],
                "drawdown_halt_pct": guard["drawdown_halt_pct"],
            }
        )
        if guard.get("buy_block_reason"):
            snap["buy_block_reason"] = guard["buy_block_reason"]
        return jsonify(snap)

    @app.route("/api/universe/health")
    def api_universe_health():
        from services.market_data.moomoo_feed import _kline_path

        missing = [t for t in ASSETS if not _kline_path(t).exists()]
        return jsonify(
            {
                "total": len(ASSETS),
                "cached": len(ASSETS) - len(missing),
                "missing": missing,
                "ready": len(missing) == 0,
            }
        )

    @app.route("/api/universe")
    def api_universe():
        from services.market_data.universe import load_cache_meta
        from services.shared.config import UNIVERSE_CFG, load_config

        cfg = load_config()
        return jsonify(
            {
                "count": len(ASSETS),
                "tickers": ASSETS,
                "config": UNIVERSE_CFG,
                "cache": load_cache_meta(cfg),
            }
        )

    @app.route("/api/config")
    def api_config():
        from services.shared.config import load_config
        return jsonify(load_config())

    @app.route("/api/metrics")
    def api_metrics():
        return jsonify(metrics.snapshot())

    @app.route("/api/alerts")
    def api_alerts():
        return jsonify({"alerts": alerts.get_recent(50), "config": alerts.get_config()})

    return app
