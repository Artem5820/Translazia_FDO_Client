from __future__ import annotations

from logging.handlers import RotatingFileHandler
from pathlib import Path
import logging

from ..config import DATA_DIR


LOG_DIR = DATA_DIR / "logs"
LOG_PATH = LOG_DIR / "translazia_client.log"

_LOGGER: logging.Logger | None = None


def client_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("translazia_client")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(
            LOG_PATH,
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(handler)
    _LOGGER = logger
    return logger


def log_event(message: str, level: str = "info") -> None:
    logger = client_logger()
    normalized = level.lower()
    if normalized in {"ошибка", "error"}:
        logger.error(message)
    elif normalized in {"предупреждение", "warning", "нейросеть"}:
        logger.warning(message)
    else:
        logger.info(message)


def log_path() -> Path:
    return LOG_PATH
