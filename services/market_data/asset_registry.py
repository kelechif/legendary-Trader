"""Register expanded asset lists with runtime state and paper trader."""

from services.market_data import state
from services.shared.config import ASSETS, CANDLE_TIMEFRAMES


def register_assets(codes: list):
    """Ensure all codes exist in market state and paper trader dicts."""
    codes = list(dict.fromkeys(codes))
    with state.lock:
        for code in codes:
            if code not in state.latest_price:
                state.latest_price[code] = None
            if code not in state.price_history:
                state.price_history[code] = []
            if code not in state.candle_history:
                state.candle_history[code] = {tf: [] for tf in CANDLE_TIMEFRAMES}
                state.candle_buffers[code] = {tf: [] for tf in CANDLE_TIMEFRAMES}
                state.candle_bucket[code] = {tf: None for tf in CANDLE_TIMEFRAMES}
            if code not in state.order_books:
                state.order_books[code] = {"bids": [], "asks": []}

    from services.execution_engine import paper_trader

    with paper_trader.lock:
        for code in codes:
            if code not in paper_trader.current_equity:
                paper_trader.current_equity[code] = 0
            if code not in paper_trader.position:
                paper_trader.position[code] = 0
            if code not in paper_trader.shares:
                paper_trader.shares[code] = 0
            if code not in paper_trader.last_price:
                paper_trader.last_price[code] = None
            if code not in paper_trader.trade_history:
                paper_trader.trade_history[code] = []
            if code not in paper_trader.equity_curve:
                paper_trader.equity_curve[code] = []
            if code not in paper_trader._last_bar_date:
                paper_trader._last_bar_date[code] = None

    return codes


def active_assets():
    return list(ASSETS)
