from __future__ import annotations

import logging
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    try:
        LOG_DIR.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(LOG_DIR / "trading_bot.log")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        pass  # read-only filesystem, etc. — console logging still works

    return logger
