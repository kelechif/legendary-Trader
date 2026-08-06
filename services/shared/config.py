import json

import os

from pathlib import Path



import yaml



ROOT = Path(__file__).resolve().parents[2]

CONFIG_DIR = ROOT / "config"



MARKET_DATA_CFG = {}

TRADING_CFG = {}

UNIVERSE_CFG = {}

MARKET_DATA_PROVIDER = "coinbase"

MOOMOO_HOST = "127.0.0.1"

MOOMOO_PORT = 11111

TRADING_MODE = "tick"

IS_EQUITY_MODE = False

ASSETS = []

STRATEGIES = []

DEFAULT_PORT = 8080

INITIAL_EQUITY = 10000.0

ENGINE_INTERVAL_SEC = 2

WS_RECONNECT_DELAY_SEC = 3

PRICE_HISTORY_LIMIT = 500

CANDLE_HISTORY_LIMIT = 300

TRADE_HISTORY_LIMIT = 200

EQUITY_HISTORY_LIMIT = 500

CANDLE_TIMEFRAMES = ["1m", "5m", "15m", "1h"]

ORDER_BOOK_DEPTH = 10

ALERTS_CFG = {}

LOGGING_CFG = {}

METRICS_CFG = {}

STRATEGY_DEFAULTS = {}

OPTIONS_CFG = {}

TWMN_ROOT = Path(r"C:\Users\kelec\OneDrive\Documents\TradeWithMeNow")

DATA_DIR = ROOT / "data"

_cfg = {}





def _deep_merge(base, override):

    result = dict(base)

    for key, value in override.items():

        if key in result and isinstance(result[key], dict) and isinstance(value, dict):

            result[key] = _deep_merge(result[key], value)

        else:

            result[key] = value

    return result





def _load_yaml(path):

    if not path.exists():

        return {}

    with open(path, encoding="utf-8") as f:

        return yaml.safe_load(f) or {}





def _load_json(path):

    if not path.exists():

        return {}

    with open(path, encoding="utf-8") as f:

        return json.load(f)





def load_config():

    defaults = _load_yaml(CONFIG_DIR / "default.yaml")

    local = _load_yaml(CONFIG_DIR / "local.yaml")

    cfg = _deep_merge(defaults, local)



    if os.environ.get("QUANT_CONFIG"):

        cfg = _deep_merge(cfg, _load_json(Path(os.environ["QUANT_CONFIG"])))



    return cfg





def _apply_globals(cfg):

    global _cfg, MARKET_DATA_CFG, TRADING_CFG, UNIVERSE_CFG, MARKET_DATA_PROVIDER

    global MOOMOO_HOST, MOOMOO_PORT, TRADING_MODE, IS_EQUITY_MODE, ASSETS

    global STRATEGIES, DEFAULT_PORT, INITIAL_EQUITY, ENGINE_INTERVAL_SEC

    global WS_RECONNECT_DELAY_SEC, PRICE_HISTORY_LIMIT, CANDLE_HISTORY_LIMIT

    global TRADE_HISTORY_LIMIT, EQUITY_HISTORY_LIMIT, CANDLE_TIMEFRAMES

    global ORDER_BOOK_DEPTH, ALERTS_CFG, LOGGING_CFG, METRICS_CFG

    global STRATEGY_DEFAULTS, OPTIONS_CFG, TWMN_ROOT, DATA_DIR



    _cfg = cfg

    MARKET_DATA_CFG = cfg.get("market_data", {})

    TRADING_CFG = cfg.get("trading", {})

    UNIVERSE_CFG = cfg.get("universe", {})

    MARKET_DATA_PROVIDER = MARKET_DATA_CFG.get("provider", "coinbase")

    MOOMOO_HOST = MARKET_DATA_CFG.get("opend_host", "127.0.0.1")

    MOOMOO_PORT = int(MARKET_DATA_CFG.get("opend_port", 11111))

    TRADING_MODE = TRADING_CFG.get("mode", "tick")

    IS_EQUITY_MODE = TRADING_MODE == "equity" or MARKET_DATA_PROVIDER == "moomoo"



    from services.market_data.universe import resolve_universe



    ASSETS = resolve_universe(cfg)



    STRATEGIES = list(cfg.get("strategies", {}).keys()) or [

        "Momentum",

        "Breakout",

        "MACD",

    ]

    DEFAULT_PORT = int(cfg.get("port", 8080))

    INITIAL_EQUITY = float(cfg.get("initial_equity", 10000.0))

    ENGINE_INTERVAL_SEC = float(cfg.get("engine_interval_sec", 2))

    WS_RECONNECT_DELAY_SEC = float(cfg.get("ws_reconnect_delay_sec", 3))

    PRICE_HISTORY_LIMIT = int(cfg.get("price_history_limit", 500))

    CANDLE_HISTORY_LIMIT = int(cfg.get("candle_history_limit", 300))

    TRADE_HISTORY_LIMIT = int(cfg.get("trade_history_limit", 200))

    EQUITY_HISTORY_LIMIT = int(cfg.get("equity_history_limit", 500))

    CANDLE_TIMEFRAMES = cfg.get("candle_timeframes", ["1m", "5m", "15m", "1h"])

    ORDER_BOOK_DEPTH = int(cfg.get("order_book_depth", 10))

    ALERTS_CFG = cfg.get("alerts", {})

    LOGGING_CFG = cfg.get("logging", {})

    METRICS_CFG = cfg.get("metrics", {})

    STRATEGY_DEFAULTS = cfg.get("strategies", {})

    OPTIONS_CFG = cfg.get("options", {})

    twmn = OPTIONS_CFG.get("twmn_root")
    if twmn:
        TWMN_ROOT = Path(twmn)

    DATA_DIR = ROOT / "data"





_apply_globals(load_config())





def get_strategy_params(name):

    return dict(STRATEGY_DEFAULTS.get(name, {}))





def reload_config():

    cfg = load_config()

    _apply_globals(cfg)

    from services.market_data.asset_registry import register_assets



    register_assets(ASSETS)

    return cfg


