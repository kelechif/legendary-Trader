"""Streamlit dashboard for legendary-Trader.

Run with:
    streamlit run dashboard.py

Read-only by default: viewing signals or the paper account never places
orders. Executing trades is always a separate, explicit button click.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from trading_bot.config import load_config
from trading_bot.data.fetcher import DataFetcher
from trading_bot.execution.broker import PaperBroker
from trading_bot.execution.trader import TradingBot
from trading_bot.ml.model import DirectionModel
from trading_bot.options.backtest import SyntheticOptionsBacktester
from trading_bot.options.risk import OptionsRiskManager, OptionsRiskParams
from trading_bot.backtest.engine import BacktestEngine
from trading_bot.strategy.risk import RiskManager, RiskParams
from trading_bot.strategy.signals import SignalGenerator

st.set_page_config(page_title="legendary-Trader", layout="wide")


@st.cache_data(ttl=300)
def _fetch(symbol: str, period: str, interval: str) -> pd.DataFrame:
    return DataFetcher().fetch(symbol, period=period, interval=interval)


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


def _watchlist_symbols(config: dict) -> list[str]:
    wl = config["watchlist"]
    return list(wl.get("stocks", [])) + list(wl.get("futures", []))


config = load_config()

if "trading_bot" not in st.session_state:
    st.session_state.trading_bot = TradingBot(config)

bot: TradingBot = st.session_state.trading_bot

st.title("legendary-Trader")
broker_mode = config["broker"]["mode"]
if broker_mode == "paper":
    st.caption("Broker mode: **paper** — everything below is simulated, nothing touches a real market.")
else:
    st.warning(f"Broker mode is **{broker_mode}** — actions taken here can place real orders.")

tab_signals, tab_account, tab_backtest, tab_options_backtest = st.tabs(
    ["Signals", "Paper Account", "Equity Backtest", "Options Backtest"]
)

with tab_signals:
    st.subheader("Current signals (read-only)")
    default_symbols = ", ".join(_watchlist_symbols(config))
    symbols_input = st.text_input("Symbols (comma-separated)", value=default_symbols)
    symbols = [s.strip() for s in symbols_input.split(",") if s.strip()]

    if "evaluations" not in st.session_state:
        st.session_state.evaluations = []

    if st.button("Refresh signals"):
        rows, evaluations = [], []
        with st.spinner("Fetching data and scoring symbols..."):
            for symbol in symbols:
                try:
                    ev = bot.evaluate_symbol(symbol)
                    evaluations.append(ev)
                    rows.append({
                        "symbol": ev["symbol"],
                        "price": round(ev["price"], 2),
                        "prob_up": round(ev["prediction"]["probability_up"], 3),
                        "signal": ev["signal"].signal.value,
                        "reason": ev["signal"].reason,
                    })
                except Exception as exc:  # noqa: BLE001
                    rows.append({"symbol": symbol, "price": None, "prob_up": None,
                                 "signal": "ERROR", "reason": str(exc)})
        st.session_state.evaluations = evaluations
        st.session_state.signal_rows = rows

    if st.session_state.get("signal_rows"):
        st.dataframe(pd.DataFrame(st.session_state.signal_rows), use_container_width=True)

        st.divider()
        st.caption("Executing sends risk-managed paper orders to the account shown in the Paper Account tab.")
        if st.button("Execute paper trades on these signals", type="primary"):
            for ev in st.session_state.evaluations:
                bot.act_on_evaluation(ev)
            st.success("Paper orders submitted where signals and risk sizing allowed. See Paper Account tab.")

with tab_account:
    st.subheader("Paper account")
    broker = bot.broker if isinstance(bot.broker, PaperBroker) else None

    if broker is None:
        st.info("Configured broker is not the PaperBroker, so there's no local account file to show here.")
    else:
        equity = broker.get_equity()
        col1, col2 = st.columns(2)
        col1.metric("Cash", f"${broker.cash:,.2f}")
        col2.metric("Equity (mark at entry price)", f"${equity:,.2f}")

        st.markdown("**Equity positions**")
        if broker.positions:
            st.dataframe(pd.DataFrame([vars(p) for p in broker.positions.values()]), use_container_width=True)
        else:
            st.caption("No open equity/futures positions.")

        st.markdown("**Option positions**")
        if broker.option_positions:
            st.dataframe(pd.DataFrame([vars(p) for p in broker.option_positions.values()]), use_container_width=True)
        else:
            st.caption("No open option positions.")

        st.markdown("**Recent trades**")
        if broker.trade_log or broker.option_trade_log:
            combined = broker.trade_log[-25:] + broker.option_trade_log[-25:]
            st.dataframe(pd.DataFrame(combined), use_container_width=True)
        else:
            st.caption("No trades yet.")

with tab_backtest:
    st.subheader("Equity/futures backtest")
    c1, c2 = st.columns(2)
    symbol = c1.text_input("Symbol", value="AAPL", key="bt_symbol")
    period = c2.selectbox("Period", ["6mo", "1y", "2y", "5y"], index=2, key="bt_period")

    if st.button("Run backtest"):
        with st.spinner(f"Backtesting {symbol}..."):
            try:
                raw_df = _fetch(symbol, period, config["data"]["interval"])
                model = _build_model(config)
                signal_generator = SignalGenerator(min_probability=config["model"]["min_probability"])
                risk_manager = RiskManager(RiskParams(**config["risk"]))
                engine = BacktestEngine(
                    starting_cash=config["backtest"]["starting_cash"],
                    commission_per_share=config["backtest"]["commission_per_share"],
                    slippage_pct=config["backtest"]["slippage_pct"],
                )
                result = engine.run(raw_df, model, signal_generator, risk_manager)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Backtest failed: {exc}")
            else:
                m = result.metrics
                cols = st.columns(4)
                cols[0].metric("Total return", f"{m.total_return_pct}%")
                cols[1].metric("CAGR", f"{m.cagr_pct}%")
                cols[2].metric("Sharpe", m.sharpe_ratio)
                cols[3].metric("Max drawdown", f"{m.max_drawdown_pct}%")
                cols2 = st.columns(3)
                cols2[0].metric("Win rate", f"{m.win_rate_pct}%")
                cols2[1].metric("Trades", m.num_trades)
                cols2[2].metric("Final equity", f"${m.final_equity:,.2f}")

                st.line_chart(result.equity_curve["equity"])
                if not result.trades.empty:
                    st.dataframe(result.trades, use_container_width=True)

with tab_options_backtest:
    st.subheader("Options backtest (synthetic Black-Scholes)")
    st.info(
        "No free historical options-chain data exists, so this prices synthetic "
        "contracts off the underlying's trailing realized volatility as an IV proxy. "
        "Read it as directional signal quality, not a real options-book replay."
    )
    c1, c2 = st.columns(2)
    opt_symbol = c1.text_input("Symbol", value="AAPL", key="opt_bt_symbol")
    opt_period = c2.selectbox("Period", ["6mo", "1y", "2y", "5y"], index=2, key="opt_bt_period")

    if st.button("Run options backtest"):
        with st.spinner(f"Backtesting options on {opt_symbol}..."):
            try:
                opts_cfg = config["options"]
                raw_df = _fetch(opt_symbol, opt_period, config["data"]["interval"])
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
            except Exception as exc:  # noqa: BLE001
                st.error(f"Options backtest failed: {exc}")
            else:
                m = result.metrics
                cols = st.columns(4)
                cols[0].metric("Total return", f"{m.total_return_pct}%")
                cols[1].metric("Sharpe", m.sharpe_ratio)
                cols[2].metric("Max drawdown", f"{m.max_drawdown_pct}%")
                cols[3].metric("Win rate", f"{m.win_rate_pct}%")

                st.line_chart(result.equity_curve["equity"])
                if not result.trades.empty:
                    st.dataframe(result.trades, use_container_width=True)
