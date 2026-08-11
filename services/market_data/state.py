import threading

from services.shared.config import ASSETS, CANDLE_TIMEFRAMES

lock = threading.Lock()

latest_price = {a: None for a in ASSETS}
price_history = {a: [] for a in ASSETS}

# Multi-timeframe candles: {asset: {timeframe: [candles]}}
candle_history = {a: {tf: [] for tf in CANDLE_TIMEFRAMES} for a in ASSETS}
candle_buffers = {a: {tf: [] for tf in CANDLE_TIMEFRAMES} for a in ASSETS}
candle_bucket = {a: {tf: None for tf in CANDLE_TIMEFRAMES} for a in ASSETS}

# Order book: {asset: {"bids": [[price, size], ...], "asks": [...]}}
order_books = {a: {"bids": [], "asks": []} for a in ASSETS}
