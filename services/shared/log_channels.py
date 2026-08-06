"""Structured JSON logging by channel (data, signal, risk, execution, safety, system)."""

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from services.shared.config import ROOT

CHANNELS = ("data", "signal", "risk", "execution", "safety", "system")
_loggers = {}


def get_channel_logger(name: str) -> logging.Logger:
    if name not in CHANNELS:
        raise ValueError(f"Unknown log channel: {name}")
    if name in _loggers:
        return _loggers[name]

    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(f"quant.{name}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = RotatingFileHandler(
        log_dir / f"{name}.log",
        maxBytes=5_000_000,
        backupCount=10,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    _loggers[name] = logger
    return logger


def log_event(channel: str, event: str, **fields):
    payload = {"channel": channel, "event": event, **fields}
    get_channel_logger(channel).info(json.dumps(payload, default=str))
