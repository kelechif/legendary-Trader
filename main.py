#!/usr/bin/env python3
"""legendary-Trader CLI.

Examples:
    python main.py backtest --symbol AAPL
    python main.py backtest --symbol ES=F --period 1y
    python main.py train --symbol MSFT
    python main.py trade --symbol AAPL MSFT ES=F --once
    python main.py trade --watchlist
    python main.py options-chain --symbol AAPL
    python main.py options-backtest --symbol AAPL --period 2y
    python main.py options-trade --symbol AAPL --once
"""
from __future__ import annotations

import argparse
import sys

from trading_bot.backtest.engine import BacktestEngine
from trading_bot.config import load_config
from trading_bot.data.fetcher import DataFetcher
from trading_bot.execution.options_trader import OptionsTradingBot
from trading_bot.execution.trader import TradingBot
from trading_bot.logger import get_logger
from trading_bot.ml.model import DirectionModel
from trading_bot.options.backtest import SyntheticOptionsBacktester
from trading_bot.options.chain import OptionsChainFetcher
from trading_bot.options.risk import OptionsRiskManager, OptionsRiskParams
from trading_bot.strategy.risk import RiskManager, RiskParams
from trading_bot.strategy.signals import SignalGenerator

logger = get_logger("main")


def _watchlist_symbols(config: dict) -> list[str]:
    wl = config["watchlist"]
    return list(wl.get("stocks", [])) + list(wl.get("futures", []))


def _build_model(config: dict) -> DirectionModel:
    model_cfg = config["model"]
    return DirectionModel(
        model_type=model_cfg["type"],
        n_estimators=model_cfg["n_estimators"],
        max_depth=model_cfg["max_depth"],
        lookahead_bars=model_cfg["lookahead_bars"],
        up_threshold_pct=model_cfg["up_threshold_pct"],
        train_test_split=model_cfg["train_test_split"],
    )


def cmd_backtest(args: argparse.Namespace, config: dict) -> None:
    fetcher = DataFetcher()
    raw_df = fetcher.fetch(args.symbol, period=args.period, interval=config["data"]["interval"])

    model = _build_model(config)
    signal_generator = SignalGenerator(min_probability=config["model"]["min_probability"])
    risk_manager = RiskManager(RiskParams(**config["risk"]))

    engine = BacktestEngine(
        starting_cash=config["backtest"]["starting_cash"],
        commission_per_share=config["backtest"]["commission_per_share"],
        slippage_pct=config["backtest"]["slippage_pct"],
    )
    result = engine.run(raw_df, model, signal_generator, risk_manager)

    print(f"\n===== Backtest: {args.symbol} ({args.period}) =====")
    for field_name, value in vars(result.metrics).items():
        print(f"  {field_name:28s}: {value}")
    print(f"  trades executed             : {len(result.trades)}")

    if args.plot:
        out_path = f"{args.symbol.replace('=', '_')}_equity_curve.png"
        engine.plot_equity_curve(result, out_path)
        print(f"\nSaved equity curve to {out_path}")


def cmd_train(args: argparse.Namespace, config: dict) -> None:
    fetcher = DataFetcher()
    raw_df = fetcher.fetch(args.symbol, period=config["data"]["history_period"], interval=config["data"]["interval"])

    model = _build_model(config)
    result = model.train(raw_df)
    model.save(args.symbol)

    print(f"\n===== Trained model: {args.symbol} =====")
    print(f"  train accuracy : {result.train_accuracy:.3f} (n={result.n_train})")
    print(f"  test accuracy  : {result.test_accuracy:.3f} (n={result.n_test})")
    print(f"  test precision : {result.test_precision:.3f}")


def cmd_options_chain(args: argparse.Namespace, config: dict) -> None:
    opts_cfg = config["options"]
    chain_fetcher = OptionsChainFetcher()
    expiration = args.expiration or chain_fetcher.nearest_expiration(args.symbol, opts_cfg["target_dte_days"])
    calls, puts = chain_fetcher.fetch_chain(args.symbol, expiration)

    fetcher = DataFetcher()
    spot = float(fetcher.fetch(args.symbol, period="5d", interval="1d")["close"].iloc[-1])

    cols = ["contractSymbol", "strike", "bid", "ask", "lastPrice", "impliedVolatility", "volume", "openInterest"]
    print(f"\n===== {args.symbol} options chain @ {expiration} (spot={spot:.2f}) =====")
    for label, df in (("CALLS", calls), ("PUTS", puts)):
        near = df.iloc[(df["strike"] - spot).abs().argsort()[:10]].sort_values("strike")
        print(f"\n{label}:")
        print(near[cols].to_string(index=False))


def cmd_options_backtest(args: argparse.Namespace, config: dict) -> None:
    fetcher = DataFetcher()
    raw_df = fetcher.fetch(args.symbol, period=args.period, interval=config["data"]["interval"])
    opts_cfg = config["options"]

    model = _build_model(config)
    signal_generator = SignalGenerator(min_probability=config["model"]["min_probability"])
    risk_manager = OptionsRiskManager(OptionsRiskParams(**opts_cfg["risk"]))

    engine = SyntheticOptionsBacktester(
        starting_cash=config["backtest"]["starting_cash"],
        dte_days=opts_cfg["target_dte_days"],
        otm_pct=opts_cfg["otm_pct"],
        risk_free_rate=opts_cfg["risk_free_rate"],
        iv_lookback=opts_cfg["iv_lookback"],
    )
    result = engine.run(raw_df, model, signal_generator, risk_manager)

    print(f"\n===== Options backtest (synthetic, Black-Scholes): {args.symbol} ({args.period}) =====")
    print("NOTE: no free historical options-chain data exists, so contracts are priced")
    print("theoretically off realized volatility. Read this as signal quality, not a")
    print("faithful replay of a real options book.\n")
    for field_name, value in vars(result.metrics).items():
        print(f"  {field_name:28s}: {value}")
    print(f"  trades executed             : {len(result.trades)}")


def cmd_options_trade(args: argparse.Namespace, config: dict) -> None:
    symbols = args.symbol if args.symbol else _watchlist_symbols(config)
    bot = OptionsTradingBot(config)

    print("Broker mode: paper (options trading is paper-only)")
    print(f"Symbols: {symbols}")

    if args.once:
        results = bot.run_once(symbols)
        for r in results:
            print(f"{r['symbol']:8s} price={r['price']:.2f} "
                  f"prob_up={r['prediction']['probability_up']:.2f} "
                  f"intent={r['intent'].right or 'HOLD'} ({r['intent'].reason})")
    else:
        bot.run_loop(symbols, poll_interval_seconds=args.interval)


def cmd_trade(args: argparse.Namespace, config: dict) -> None:
    symbols = args.symbol if args.symbol else _watchlist_symbols(config)
    bot = TradingBot(config)

    print(f"Broker mode: {config['broker']['mode']} (paper trading unless explicitly set to 'alpaca')")
    print(f"Symbols: {symbols}")

    if args.once:
        results = bot.run_once(symbols)
        for r in results:
            print(f"{r['symbol']:8s} price={r['price']:.2f} "
                  f"prob_up={r['prediction']['probability_up']:.2f} "
                  f"signal={r['signal'].signal.value} ({r['signal'].reason})")
    else:
        bot.run_loop(symbols, poll_interval_seconds=args.interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="legendary-Trader: ML-assisted trading bot")
    parser.add_argument("--config", default=None, help="Path to config.yaml (default: repo config.yaml)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_backtest = sub.add_parser("backtest", help="Backtest the ML strategy on historical data")
    p_backtest.add_argument("--symbol", required=True, help="Ticker, e.g. AAPL or ES=F")
    p_backtest.add_argument("--period", default="2y", help="History window, e.g. 1y, 2y, 5y")
    p_backtest.add_argument("--plot", action="store_true", help="Save an equity curve PNG")
    p_backtest.set_defaults(func=cmd_backtest)

    p_train = sub.add_parser("train", help="Train and persist the direction model for a symbol")
    p_train.add_argument("--symbol", required=True)
    p_train.set_defaults(func=cmd_train)

    p_trade = sub.add_parser("trade", help="Run the automated (paper by default) trading loop")
    p_trade.add_argument("--symbol", nargs="*", help="Symbols to trade (default: config watchlist)")
    p_trade.add_argument("--watchlist", action="store_true", help="Trade the configured watchlist")
    p_trade.add_argument("--once", action="store_true", help="Run a single evaluation cycle and exit")
    p_trade.add_argument("--interval", type=int, default=None, help="Seconds between cycles in loop mode")
    p_trade.set_defaults(func=cmd_trade)

    p_opt_chain = sub.add_parser("options-chain", help="Show the live option chain for a symbol")
    p_opt_chain.add_argument("--symbol", required=True)
    p_opt_chain.add_argument("--expiration", default=None, help="YYYY-MM-DD (default: nearest to config target DTE)")
    p_opt_chain.set_defaults(func=cmd_options_chain)

    p_opt_bt = sub.add_parser("options-backtest", help="Synthetic Black-Scholes options-strategy backtest")
    p_opt_bt.add_argument("--symbol", required=True)
    p_opt_bt.add_argument("--period", default="2y")
    p_opt_bt.set_defaults(func=cmd_options_backtest)

    p_opt_trade = sub.add_parser("options-trade", help="Run the automated (paper) options trading loop")
    p_opt_trade.add_argument("--symbol", nargs="*", help="Symbols to trade (default: config watchlist)")
    p_opt_trade.add_argument("--once", action="store_true", help="Run a single evaluation cycle and exit")
    p_opt_trade.add_argument("--interval", type=int, default=None, help="Seconds between cycles in loop mode")
    p_opt_trade.set_defaults(func=cmd_options_trade)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(args.config) if args.config else load_config()

    try:
        args.func(args, config)
    except Exception as exc:  # noqa: BLE001
        logger.error("Command failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
