"""Refresh the tradable universe from Moomoo or fallback YAML."""

import argparse
import json
import sys

from services.market_data.asset_registry import register_assets
from services.market_data.universe import (
    _fallback_path,
    _load_yaml_tickers,
    load_cache,
    refresh_universe,
    save_cache,
)
from services.shared.config import UNIVERSE_CFG, load_config, reload_config
from services.shared.logging_setup import setup_logging


def main():
    parser = argparse.ArgumentParser(description="Refresh Quant Platform universe")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force refresh from Moomoo screener even if cache is fresh",
    )
    parser.add_argument(
        "--source",
        choices=["moomoo_screener", "file"],
        help="Override universe.source for this run",
    )
    parser.add_argument("--print", action="store_true", help="Print tickers to stdout")
    args = parser.parse_args()

    log = setup_logging()
    cfg = load_config()
    ucfg = dict(cfg.get("universe", {}))
    if args.source:
        ucfg["source"] = args.source
        cfg = {**cfg, "universe": ucfg}

    if ucfg.get("source") == "file":
        limit = int(ucfg.get("limit", 100))
        tickers = _load_yaml_tickers(_fallback_path(cfg))[:limit]
        save_cache(cfg, tickers, source="file")
    else:
        tickers = refresh_universe(cfg, force=args.force)

    register_assets(tickers)
    reload_config()

    log.info(
        "Universe refreshed: %d tickers (source=%s)",
        len(tickers),
        UNIVERSE_CFG.get("source"),
    )
    log.info("Cache: %s", UNIVERSE_CFG.get("cache_file", "data/universe.json"))

    if args.print:
        meta = load_cache(cfg) or tickers
        if isinstance(meta, list):
            print(json.dumps({"count": len(meta), "tickers": meta}, indent=2))
        else:
            print(json.dumps({"count": len(tickers), "tickers": tickers}, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
