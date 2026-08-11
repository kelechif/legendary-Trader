"""Universe resolution: Moomoo screener, cached file, or static YAML fallback."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from services.shared.config import DATA_DIR, MOOMOO_HOST, MOOMOO_PORT, ROOT
from services.shared import log_channels

# Top US large caps for snapshot-sort fallback (when screener returns thin results)
_US_FALLBACK = [
    "US.AAPL", "US.MSFT", "US.NVDA", "US.GOOG", "US.AMZN", "US.META", "US.BRK.B",
    "US.TSLA", "US.AVGO", "US.WMT", "US.JPM", "US.LLY", "US.V", "US.MA", "US.UNH",
    "US.ORCL", "US.XOM", "US.COST", "US.NFLX", "US.HD", "US.PG", "US.JNJ", "US.BAC",
    "US.ABBV", "US.CRM", "US.KO", "US.AMD", "US.MRK", "US.CSCO", "US.PEP", "US.TMO",
    "US.ADBE", "US.ACN", "US.IBM", "US.ABT", "US.QCOM", "US.GE", "US.AMAT", "US.ISRG",
    "US.INTU", "US.TXN", "US.BKNG", "US.NOW", "US.UBER", "US.GS", "US.MS", "US.CAT",
    "US.CVX", "US.RTX", "US.DIS", "US.BLK", "US.PFE", "US.AMGN", "US.VZ", "US.UNP",
    "US.SPGI", "US.DHR", "US.NEE", "US.CMCSA", "US.COP", "US.ADP", "US.PANW", "US.CB",
    "US.MDLZ", "US.SO", "US.LMT", "US.WM", "US.UPS", "US.KLAC", "US.REGN", "US.HCA",
    "US.GD", "US.MCO", "US.CME", "US.ITW", "US.NOC", "US.MAR", "US.ECL", "US.WELL",
]


def _universe_cfg(cfg: dict) -> dict:
    return cfg.get("universe", {})


def _cache_path(cfg: dict) -> Path:
    rel = _universe_cfg(cfg).get("cache_file", "data/universe.json")
    path = Path(rel)
    return path if path.is_absolute() else ROOT / path


def _fallback_path(cfg: dict) -> Path:
    rel = _universe_cfg(cfg).get(
        "fallback_file", "config/universe_us_large_cap.yaml"
    )
    path = Path(rel)
    return path if path.is_absolute() else ROOT / path


def _load_yaml_tickers(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    tickers = data.get("tickers") or data.get("assets") or []
    return [_normalize_code(c) for c in tickers if c]


def _normalize_code(code: str) -> str:
    code = str(code).strip().upper()
    if "." in code:
        return code
    return f"US.{code}"


def _cache_fresh(path: Path, max_age_days: int) -> bool:
    if not path.exists():
        return False
    try:
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
        updated = meta.get("updated_at")
        if not updated:
            return False
        ts = datetime.fromisoformat(updated)
        return datetime.now() - ts < timedelta(days=max_age_days)
    except (json.JSONDecodeError, ValueError, OSError):
        return False


def load_cache(cfg: dict) -> list | None:
    path = _cache_path(cfg)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        tickers = data.get("tickers") or []
        return [_normalize_code(t) for t in tickers if t]
    except (json.JSONDecodeError, OSError):
        return None


def load_cache_meta(cfg: dict) -> dict | None:
    path = _cache_path(cfg)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_cache(cfg: dict, tickers: list, source: str, meta: dict | None = None):
    path = _cache_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "count": len(tickers),
        "tickers": tickers,
        "meta": meta or {},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    log_channels.log_event(
        "data", "universe_cached", count=len(tickers), source=source, path=str(path)
    )


def fetch_moomoo_screener(cfg: dict) -> list:
    """Top US stocks by market cap via Moomoo get_stock_filter."""
    ucfg = _universe_cfg(cfg)
    market = ucfg.get("market", "US").upper()
    limit = int(ucfg.get("limit", 100))
    min_cap_usd = float(ucfg.get("min_market_cap_usd", 20_000_000_000))
    # API expects market cap in hundreds of millions (×1e8 internally in skill script)
    min_cap_units = min_cap_usd / 1e8

    from moomoo import Market, OpenQuoteContext, RET_OK, SimpleFilter, SortDir, StockField

    ctx = OpenQuoteContext(MOOMOO_HOST, MOOMOO_PORT)
    try:
        sf_cap = SimpleFilter()
        sf_cap.stock_field = StockField.MARKET_VAL
        sf_cap.is_no_filter = False
        sf_cap.filter_min = min_cap_usd

        sf_sort = SimpleFilter()
        sf_sort.stock_field = StockField.MARKET_VAL
        sf_sort.is_no_filter = False
        sf_sort.filter_min = 1
        sf_sort.sort = SortDir.DESCEND

        ret, data = ctx.get_stock_filter(
            market=Market.US if market == "US" else Market.HK,
            filter_list=[sf_cap, sf_sort],
            begin=0,
            num=limit,
        )
        if ret != RET_OK or data is None or len(data) == 0:
            return _fetch_snapshot_fallback(ctx, limit)

        codes = []
        for _, row in data.iterrows():
            code = row.get("code") or row.get("stock_code")
            if code:
                codes.append(_normalize_code(code))
        return codes[:limit]
    finally:
        ctx.close()


def _fetch_snapshot_fallback(ctx, limit: int) -> list:
    """Rank known large caps by snapshot market cap when screener is empty."""
    from moomoo import RET_OK

    records = []
    batch_size = 50
    for i in range(0, len(_US_FALLBACK), batch_size):
        batch = _US_FALLBACK[i : i + batch_size]
        ret, data = ctx.get_market_snapshot(batch)
        if ret != RET_OK or data is None:
            continue
        for _, row in data.iterrows():
            code = row.get("code")
            mcap = float(row.get("total_market_val") or 0)
            if code and mcap > 0:
                records.append((code, mcap))

    records.sort(key=lambda x: x[1], reverse=True)
    if records:
        return [_normalize_code(c) for c, _ in records[:limit]]
    return _US_FALLBACK[:limit]


def resolve_universe(cfg: dict, force_refresh: bool = False) -> list:
    """Resolve ticker list from config, cache, Moomoo screener, or fallback YAML."""
    ucfg = _universe_cfg(cfg)
    source = ucfg.get("source", "static")
    max_age = int(ucfg.get("max_age_days", 7))

    static_assets = cfg.get("assets") or []
    if source == "static" and static_assets:
        return [_normalize_code(a) for a in static_assets]

    if source == "file":
        tickers = _load_yaml_tickers(_fallback_path(cfg))
        if tickers:
            return tickers[: int(ucfg.get("limit", 100))]

    cache_path = _cache_path(cfg)
    if not force_refresh and _cache_fresh(cache_path, max_age):
        cached = load_cache(cfg)
        if cached:
            return cached[: int(ucfg.get("limit", 100))]

    if source in ("moomoo_screener", "screener", "moomoo"):
        try:
            tickers = fetch_moomoo_screener(cfg)
            if tickers:
                save_cache(cfg, tickers, source="moomoo_screener")
                return tickers
        except Exception as exc:
            log_channels.log_event("data", "universe_screener_failed", error=str(exc))

    cached = load_cache(cfg)
    if cached:
        return cached

    fallback = _load_yaml_tickers(_fallback_path(cfg))
    if fallback:
        log_channels.log_event("data", "universe_fallback_yaml", count=len(fallback))
        return fallback[: int(ucfg.get("limit", 100))]

    return [_normalize_code(a) for a in static_assets] if static_assets else list(_US_FALLBACK[:100])


def refresh_universe(cfg: dict | None = None, force: bool = False) -> list:
    if cfg is None:
        from services.shared.config import load_config
        cfg = load_config()
    ucfg = _universe_cfg(cfg)
    source = ucfg.get("source", "static")
    if source in ("moomoo_screener", "screener", "moomoo") or force:
        tickers = resolve_universe(cfg, force_refresh=True)
    else:
        tickers = resolve_universe(cfg, force_refresh=False)
    return tickers
