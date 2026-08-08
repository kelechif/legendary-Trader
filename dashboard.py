"""AlphaFlow — the legendary-Trader dashboard.

Run with:
    streamlit run dashboard.py

Read-only by default: viewing signals, the scanner, or the paper account
never places an order. Every trade — bulk or one-click — is a separate,
explicit button click, and anything beyond paper trading requires both a
non-default broker config AND ticking the live-trading confirmation box
below the mode banner.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from trading_bot.config import load_config
from trading_bot.data.fetcher import DataFetcher
from trading_bot.execution.broker import PaperBroker
from trading_bot.execution.options_trader import OptionsTradingBot
from trading_bot.execution.trader import TradingBot, build_broker
from trading_bot.ml.model import DirectionModel
from trading_bot.options.backtest import SyntheticOptionsBacktester
from trading_bot.options.risk import OptionsRiskManager, OptionsRiskParams
from trading_bot.backtest.engine import BacktestEngine
from trading_bot.strategy.risk import RiskManager, RiskParams
from trading_bot.strategy.signals import Signal, SignalGenerator

st.set_page_config(page_title="AlphaFlow — legendary-Trader", layout="wide", page_icon="\U0001F4C8")

st.markdown(
    """
    <style>
    :root {
        --af-good: #2fae74; --af-bad: #d1543f; --af-accent: #c99a3e; --af-mute: #9a8f78;
    }
    .af-mono { font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
               font-variant-numeric: tabular-nums; }
    .af-badge { display:inline-block; padding:0.05rem 0.55rem; border-radius:999px;
                font-size:0.72rem; font-weight:700; letter-spacing:0.04em; vertical-align:middle; }
    .af-badge-buy, .af-badge-call { background: rgba(47,174,116,0.15); color: var(--af-good);
                                     border:1px solid rgba(47,174,116,0.4); }
    .af-badge-sell, .af-badge-put { background: rgba(209,84,63,0.15); color: var(--af-bad);
                                     border:1px solid rgba(209,84,63,0.4); }
    .af-badge-hold { background: rgba(154,143,120,0.15); color: var(--af-mute);
                      border:1px solid rgba(154,143,120,0.4); }
    .af-symbol { font-weight:700; font-size:1.05rem; }
    .af-reason { color: var(--af-mute); font-size:0.78rem; }
    .af-row { padding: 0.5rem 0 0.9rem; border-bottom: 1px solid rgba(154,143,120,0.18); }
    </style>
    """,
    unsafe_allow_html=True,
)

# A starting scan universe wider than any single handful of tickers: the
# configured watchlist plus a set of liquid, optionable large caps. Fully
# editable in the Scanner tab — this is just a sane default, not a limit.
POPULAR_SYMBOLS = [
    "NVDA", "AMD", "META", "GOOGL", "AMZN", "TSLA", "NFLX", "AVGO",
    "QQQ", "GILD", "TSM", "IONQ",
]


def _badge(label: str, kind: str) -> str:
    return f'<span class="af-badge af-badge-{kind}">{label}</span>'


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


def _default_universe(config: dict, include_futures: bool) -> list[str]:
    symbols = list(dict.fromkeys(_watchlist_symbols(config) + POPULAR_SYMBOLS))
    if not include_futures:
        symbols = [s for s in symbols if "=F" not in s]
    return symbols


def _report_order(result) -> None:
    label = getattr(result, "symbol", None) or getattr(result, "underlying", "")
    qty = getattr(result, "shares", None)
    if qty is None:
        qty = getattr(result, "contracts", "")
    if result.status == "filled":
        st.success(f"Filled: {result.side} {qty} {label} — see Paper Account tab.")
    else:
        st.error(f"Order rejected: {result.reason}")


def _render_stock_row(symbol: str, evaluation: dict, preview, engine: TradingBot, gate_ok: bool) -> None:
    signal = evaluation["signal"]
    price = evaluation["price"]
    prob_up = evaluation["prediction"]["probability_up"]
    position = engine.broker.get_position(symbol)

    badge_kind = {"BUY": "buy", "SELL": "sell", "HOLD": "hold"}[signal.signal.value]
    header = f'<span class="af-symbol">{symbol}</span> {_badge(signal.signal.value, badge_kind)}'
    if position is not None:
        header += f' {_badge("OPEN POSITION", "hold")}'
    st.markdown(header, unsafe_allow_html=True)
    st.markdown(
        f'<span class="af-mono">price \\${price:,.2f} &middot; prob_up {prob_up:.0%}</span>',
        unsafe_allow_html=True,
    )
    st.markdown(f'<span class="af-reason">{signal.reason}</span>', unsafe_allow_html=True)

    if position is not None:
        st.markdown(
            f'<span class="af-mono">{position.shares} sh @ \\${position.entry_price:,.2f} '
            f'&middot; stop \\${position.stop_loss:,.2f} &middot; target \\${position.take_profit:,.2f}</span>',
            unsafe_allow_html=True,
        )
        if st.button(f"Close {symbol} now (sell {position.shares} sh @ ${price:,.2f})", key=f"close_{symbol}", disabled=not gate_ok):
            result = engine.broker.submit_order(symbol, "SELL", position.shares, price)
            _report_order(result)
    elif signal.signal == Signal.BUY and preview is not None and preview.shares > 0:
        st.markdown(
            f'<span class="af-mono">entry \\${price:,.2f} &middot; stop \\${preview.stop_loss:,.2f} '
            f'&middot; target \\${preview.take_profit:,.2f} &middot; risking \\${preview.dollar_risk:,.2f}</span>',
            unsafe_allow_html=True,
        )
        if st.button(f"Buy {preview.shares} sh of {symbol} @ ${price:,.2f}", key=f"buy_{symbol}", disabled=not gate_ok):
            result = engine.submit_plan(symbol, price, preview)
            _report_order(result)
    else:
        st.caption("No actionable entry right now.")


def _render_options_row(symbol: str, evaluation: dict, preview, engine: OptionsTradingBot, gate_ok: bool) -> None:
    intent = evaluation["intent"]
    price = evaluation["price"]
    existing = engine.broker.find_option_position_for_underlying(symbol)

    right_label = (intent.right or "HOLD").upper()
    badge_kind = {"CALL": "call", "PUT": "put", "HOLD": "hold"}[right_label]
    header = f'<span class="af-symbol">{symbol}</span> {_badge(right_label, badge_kind)}'
    if existing is not None:
        header += f' {_badge("OPEN POSITION", "hold")}'
    st.markdown(header, unsafe_allow_html=True)
    st.markdown(f'<span class="af-mono">underlying \\${price:,.2f}</span>', unsafe_allow_html=True)
    st.markdown(f'<span class="af-reason">{intent.reason}</span>', unsafe_allow_html=True)

    if existing is not None:
        st.markdown(
            f'<span class="af-mono">{existing.contracts}x {existing.right.upper()} \\${existing.strike:g} '
            f'exp {existing.expiration} &middot; entry premium \\${existing.entry_premium:,.2f}</span>',
            unsafe_allow_html=True,
        )
        if st.button(f"Close {symbol} {existing.right} position now", key=f"close_opt_{symbol}", disabled=not gate_ok):
            engine.close_position(symbol, existing)
            st.success(f"{symbol}: close order sent. See Paper Account tab.")
    elif intent.right is not None and preview is not None and preview.plan.contracts > 0:
        c, p = preview.contract, preview.plan
        st.markdown(
            f'<span class="af-mono">{c.right.upper()} \\${c.strike:g} exp {c.expiration} ({c.dte_days}d) '
            f"&middot; premium \\${c.premium:,.2f} &middot; delta {c.delta:.2f} &middot; IV {c.implied_vol:.0%}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<span class="af-mono">stop \\${p.stop_loss_premium:,.2f} &middot; target \\${p.take_profit_premium:,.2f} '
            f"&middot; {p.contracts} contract(s) &middot; cost \\${p.total_cost:,.2f}</span>",
            unsafe_allow_html=True,
        )
        if st.button(f"Buy {p.contracts}x {c.right.upper()} {symbol} ${c.strike:g} @ ${c.premium:,.2f}",
                     key=f"buy_opt_{symbol}", disabled=not gate_ok):
            result = engine.submit_preview(symbol, preview)
            _report_order(result)
    else:
        st.caption("No actionable contract right now (HOLD signal or chain/sizing unavailable).")


config = load_config()

# One broker backs the equity bot; the options bot shares it when it's a
# PaperBroker (the common case) so both trade against the same cash/position
# state. If the equity broker is live (Alpaca/moomoo), options still needs
# its own PaperBroker, since options execution is paper-only in this project.
if "broker" not in st.session_state:
    st.session_state.broker = build_broker(config)
broker_instance = st.session_state.broker

if "trading_bot" not in st.session_state:
    st.session_state.trading_bot = TradingBot(config, broker=broker_instance)
bot: TradingBot = st.session_state.trading_bot

if "options_bot" not in st.session_state:
    options_broker = broker_instance if isinstance(broker_instance, PaperBroker) else PaperBroker(
        starting_cash=config["backtest"]["starting_cash"],
        account_file=config["broker"].get("account_file", "paper_account.json"),
    )
    st.session_state.options_bot = OptionsTradingBot(config, broker=options_broker)
options_bot: OptionsTradingBot = st.session_state.options_bot

st.title("AlphaFlow")
st.caption(
    "Scanner and one-click trading console for legendary-Trader's real signal + risk engine "
    "— live Yahoo Finance data, an ML direction model, ATR/premium-based position sizing. "
    "Not the 'alpha options' black box from the pitch deck — a transparent, inspectable engine."
)

broker_mode = config["broker"]["mode"]
is_live = broker_mode != "paper"
if is_live:
    st.warning(
        f"Broker mode is **{broker_mode}** — Trade buttons on this page can place REAL orders "
        "against a real account. Options trading always stays on its own paper account regardless "
        "of this setting (see README)."
    )
    live_confirmed = st.checkbox(
        "I understand — enable live Trade buttons for equities/futures on this page",
        key="global_live_confirm",
    )
else:
    st.caption("Broker mode: **paper** — every trade on this page is simulated. Nothing touches a real market.")
    live_confirmed = True

tab_scanner, tab_signals, tab_account, tab_backtest, tab_options_backtest = st.tabs(
    ["Scanner", "Signals", "Paper Account", "Equity Backtest", "Options Backtest"]
)

# ----------------------------------------------------------------------------
# Scanner: broad universe -> BUY/SELL/HOLD + entry/stop/target -> one-click trade
# ----------------------------------------------------------------------------
with tab_scanner:
    st.subheader("Scan a universe, get entry/stop/target, trade in one click")

    asset_type = st.radio(
        "Instrument", ["Stocks / Futures", "Options (calls & puts)"], horizontal=True, key="scan_asset_type",
    )
    is_options_scan = asset_type.startswith("Options")

    universe_default = ", ".join(_default_universe(config, include_futures=not is_options_scan))
    universe_input = st.text_area(
        "Symbols to scan (comma-separated — any tickers, not limited to the list below)",
        value=universe_default, height=68, key="scan_universe",
    )
    symbols_to_scan = [s.strip().upper() for s in universe_input.split(",") if s.strip()]

    always_paper = broker_mode == "paper" or is_options_scan  # options trading is paper-only regardless of broker_mode
    scan_gate_ok = always_paper or live_confirmed
    if not scan_gate_ok:
        st.info("Tick the live-trading confirmation box above to enable Trade buttons for this scan.")

    col_scan, col_exits = st.columns([1, 1])
    scan_clicked = col_scan.button("Scan", type="primary", key="scan_run")
    exits_clicked = col_exits.button("Check stop/target exits now", key="scan_check_exits")

    if exits_clicked:
        with st.spinner("Re-pricing open positions..."):
            closed_eq = bot.check_exits()
            closed_opt = options_bot.check_exits()
        if not closed_eq and not closed_opt:
            st.info("No open positions have hit their stop-loss or take-profit level.")
        else:
            for c in closed_eq:
                st.success(f"{c['symbol']}: closed on {c['reason']} @ \\${c['price']:.2f}")
            for c in closed_opt:
                st.success(f"{c['symbol']} {c['contract_symbol']}: closed on {c['reason']} @ \\${c['premium']:.2f}")

    if scan_clicked:
        engine = options_bot if is_options_scan else bot
        rows: list[dict[str, Any]] = []
        with st.spinner(f"Scanning {len(symbols_to_scan)} symbol(s) — first run per symbol trains a model, be patient..."):
            for symbol in symbols_to_scan:
                try:
                    evaluation = engine.evaluate_symbol(symbol)
                    preview = engine.plan_for_evaluation(evaluation)
                    rows.append({"symbol": symbol, "evaluation": evaluation, "preview": preview, "error": None})
                except Exception as exc:  # noqa: BLE001 - one bad symbol shouldn't kill the scan
                    rows.append({"symbol": symbol, "evaluation": None, "preview": None, "error": str(exc)})
        st.session_state.scan_rows = rows
        st.session_state.scan_is_options = is_options_scan

    scan_rows = st.session_state.get("scan_rows")
    if scan_rows is not None and st.session_state.get("scan_is_options") == is_options_scan:

        def _sort_key(r: dict[str, Any]) -> tuple:
            if r["error"]:
                return (2, r["symbol"])
            if is_options_scan:
                actionable = r["preview"] is not None and r["preview"].plan.contracts > 0
            else:
                actionable = r["evaluation"]["signal"].signal == Signal.BUY and r["preview"] is not None and r["preview"].shares > 0
            return (0 if actionable else 1, r["symbol"])

        for row in sorted(scan_rows, key=_sort_key):
            symbol, evaluation, preview, error = row["symbol"], row["evaluation"], row["preview"], row["error"]
            st.markdown('<div class="af-row">', unsafe_allow_html=True)

            if error:
                st.markdown(f'<span class="af-symbol">{symbol}</span> {_badge("ERROR", "hold")}', unsafe_allow_html=True)
                st.caption(error)
                st.markdown("</div>", unsafe_allow_html=True)
                continue

            if is_options_scan:
                _render_options_row(symbol, evaluation, preview, options_bot, scan_gate_ok)
            else:
                _render_stock_row(symbol, evaluation, preview, bot, scan_gate_ok)

            st.markdown("</div>", unsafe_allow_html=True)
    elif scan_rows is None:
        st.caption("Enter symbols above and click Scan.")


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
        button_label = "Execute paper trades on these signals" if broker_mode == "paper" else \
            f"Execute LIVE ({broker_mode}) trades on these signals"
        st.caption(f"Executing sends risk-managed {broker_mode} orders to the account shown in the Paper Account tab.")
        if st.button(button_label, type="primary", disabled=not live_confirmed):
            for ev in st.session_state.evaluations:
                bot.act_on_evaluation(ev)
            st.success("Orders submitted where signals and risk sizing allowed. See Paper Account tab.")

with tab_account:
    st.subheader("Paper account")
    pb = broker_instance if isinstance(broker_instance, PaperBroker) else None

    if pb is None:
        st.info("Configured equity broker is not the PaperBroker, so there's no local account file to show for it here. "
                 "Options remain on their own separate paper account regardless.")
    else:
        equity = pb.get_equity()
        col1, col2 = st.columns(2)
        col1.metric("Cash", f"${pb.cash:,.2f}")
        col2.metric("Equity (mark at entry price)", f"${equity:,.2f}")

        if st.button("Check stop/target exits now", key="account_check_exits"):
            with st.spinner("Re-pricing open positions..."):
                closed_eq = bot.check_exits()
                closed_opt = options_bot.check_exits()
            if not closed_eq and not closed_opt:
                st.info("No open positions have hit their stop-loss or take-profit level.")
            else:
                for c in closed_eq:
                    st.success(f"{c['symbol']}: closed on {c['reason']} @ \\${c['price']:.2f}")
                for c in closed_opt:
                    st.success(f"{c['symbol']} {c['contract_symbol']}: closed on {c['reason']} @ \\${c['premium']:.2f}")

        st.markdown("**Equity positions**")
        if pb.positions:
            st.dataframe(pd.DataFrame([vars(p) for p in pb.positions.values()]), use_container_width=True)
        else:
            st.caption("No open equity/futures positions.")

        st.markdown("**Option positions**")
        if pb.option_positions:
            st.dataframe(pd.DataFrame([vars(p) for p in pb.option_positions.values()]), use_container_width=True)
        else:
            st.caption("No open option positions.")

        st.markdown("**Recent trades**")
        if pb.trade_log or pb.option_trade_log:
            combined = pb.trade_log[-25:] + pb.option_trade_log[-25:]
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
