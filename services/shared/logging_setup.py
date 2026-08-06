import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from services.shared.config import LOGGING_CFG, ROOT


def setup_logging():
    level_name = LOGGING_CFG.get("level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    log_file = LOGGING_CFG.get("file", "logs/platform.log")
    log_path = Path(log_file)
    if not log_path.is_absolute():
        log_path = ROOT / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=int(LOGGING_CFG.get("max_bytes", 1048576)),
        backupCount=int(LOGGING_CFG.get("backup_count", 3)),
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    return logging.getLogger("quant-platform")
