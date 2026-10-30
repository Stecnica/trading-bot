"""Percorsi e accesso al database. Le credenziali restano nelle variabili d'ambiente."""

import logging
import os
from pathlib import Path

ROOT = Path("/var/www/clients/client0/web5")
WEB = ROOT / "web"
PRIVATE = ROOT / "private"
LOG_PATH = PRIVATE / "trading-bot.log"
STATUS_PATH = PRIVATE / "cycle_status.json"
LOCK_PATH = PRIVATE / "cycle.lock"
UI_PASSWORD_PATH = PRIVATE / "ui_password"
FLASK_SECRET_PATH = PRIVATE / "flask_secret"
UNIVERSE_CACHE = PRIVATE / "sp500_symbols.txt"
NAMES_CACHE = PRIVATE / "sp500_names.tsv"
CLASSES_CACHE = PRIVATE / "sp500_classes.tsv"
MPLCONFIG = PRIVATE / "mplconfig"

SITE_PACKAGES = (
    "/var/www/clients/client0/web5/home/default_botmanager/.local/lib/python3.10/site-packages"
)


def env_first(*keys, default=None):
    for key in keys:
        value = os.environ.get(key)
        if value:
            return value
    return default


def db_config():
    return {
        "user": env_first("DB_USERNAME_web5", "DB_USERNAME"),
        "password": env_first("DB_PASSWORD_web5", "DB_PASSWORD"),
        "host": env_first("DB_SERVER_web5", "DB_SERVER", default="localhost"),
        "database": env_first("DB_NAME_web5", "DB_NAME"),
        "charset": "utf8mb4",
    }


def get_logger():
    logger = logging.getLogger("tradingbot")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
