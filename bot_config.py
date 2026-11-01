"""Paths and database access. Credentials stay in the environment."""

import logging
import os
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent
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

def site_packages():
    chosen = os.environ.get("SITE_PACKAGES")
    if chosen:
        return chosen
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    home = Path.home() / ".local" / "lib" / version / "site-packages"
    if home.is_dir():
        return str(home)
    homes = ROOT / "home"
    if homes.is_dir():
        found = sorted(homes.glob(f"*/.local/lib/{version}/site-packages"))
        if found:
            return str(found[0])
    return str(home)


SITE_PACKAGES = site_packages()


def install_import_path():
    if os.path.isdir(SITE_PACKAGES) and SITE_PACKAGES not in sys.path:
        sys.path.insert(0, SITE_PACKAGES)


def env_first(*keys, default=None):
    for key in keys:
        value = os.environ.get(key)
        if value:
            return value
    return default


def env_db(base, default=None):
    prefixed = [value for key, value in sorted(os.environ.items()) if key.startswith(base + "_") and value]
    if prefixed:
        return prefixed[0]
    return env_first(base, default=default)


def db_config():
    return {
        "user": env_db("DB_USERNAME"),
        "password": env_db("DB_PASSWORD"),
        "host": env_db("DB_SERVER", default="localhost"),
        "database": env_db("DB_NAME"),
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
