"""Paths and database access. Credentials stay in the environment."""

import fcntl
import logging
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent
PRIVATE = ROOT / "private"
LOG_PATH = PRIVATE / "trading-bot.log"
STATUS_PATH = PRIVATE / "cycle_status.json"
LOCK_PATH = PRIVATE / "cycle.lock"
# Held by a cycle for its whole run and by the history fill for each write, so the two never write together.
PRICES_LOCK = PRIVATE / "prices.lock"
BACKFILL_LOCK = PRIVATE / "backfill.lock"
BACKFILL_STATUS = PRIVATE / "backfill_status.json"
UI_PASSWORD_PATH = PRIVATE / "ui_password"
# Temporary computerUse QA user (qa_cursor). Remove with private/ui_password_qa.
UI_PASSWORD_QA_PATH = PRIVATE / "ui_password_qa"
# View-only account. The hash is the password file; the readable copy stays beside it.
UI_PASSWORD_LEONARDO_PATH = PRIVATE / "ui_password_leonardobot"
AUDIT_LOG_PATH = PRIVATE / "access.log"
FLASK_SECRET_PATH = PRIVATE / "flask_secret"
UNIVERSE_CACHE = PRIVATE / "sp500_symbols.txt"
NAMES_CACHE = PRIVATE / "sp500_names.tsv"
CLASSES_CACHE = PRIVATE / "sp500_classes.tsv"
MPLCONFIG = PRIVATE / "mplconfig"
# The client root is immutable, so matplotlib cannot create ~/.config there.
# LightGBM imports matplotlib during the cycle, before the chart module runs.
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG))
MPLCONFIG.mkdir(parents=True, exist_ok=True)

@contextmanager
def file_lock(path, timeout=None):
    """Exclusive flock on path. Waits up to timeout seconds (None: as long as it takes) and
    raises TimeoutError after that. The lock goes away with the process, so a killed job leaves none."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a", encoding="utf-8")
    started = time.monotonic()
    try:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if timeout is not None and time.monotonic() - started >= timeout:
                    raise TimeoutError(str(path)) from None
                time.sleep(0.5)
        yield
    finally:
        handle.close()


def lock_held(path):
    """True when another process holds the flock on path."""
    if not path.exists():
        return False
    with open(path, "a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


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


def apply_env_file(path, environ=None):
    """Set empty variables from a KEY=value file. Existing values stay."""
    target = os.environ if environ is None else environ
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text.startswith("export "):
            text = text[len("export "):].strip()
        key, sep, value = text.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and not target.get(key):
            target[key] = value


def load_private_env():
    """Database variables from private/database.env, else private/bot.env (the crontab file).

    These files win over the process environment: a stale DB_* left in the server environment
    (Apache envvars, SetEnv) must not shadow the credentials kept in private/.
    """
    found = {}
    apply_env_file(PRIVATE / "database.env", found)
    apply_env_file(PRIVATE / "bot.env", found)
    os.environ.update(found)


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
    load_private_env()
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
