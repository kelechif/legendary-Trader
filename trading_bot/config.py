from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load YAML config and layer in environment-variable overrides for secrets."""
    with open(path, "r") as f:
        config = yaml.safe_load(f)

    config.setdefault("broker", {})
    config["broker"]["alpaca_api_key"] = os.environ.get("ALPACA_API_KEY")
    config["broker"]["alpaca_secret_key"] = os.environ.get("ALPACA_SECRET_KEY")
    config["broker"]["alpaca_base_url"] = os.environ.get(
        "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
    )
    return config
