"""Schema, preferences, prices, and transactions."""

import json
import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

import mysql.connector

from bot_config import LOCK_PATH, STATUS_PATH, db_config, get_logger
from bot_i18n import tr
from bot_logic import CURRENCY, armed_peak, money, peak_drop, trail_exit, one_day_floor, open_lots, quote_sell, fifo_transaction_views, paper_cash_balance, taxable_gains_by_sale

NEW_YORK = ZoneInfo("America/New_York")

log = get_logger()

FONT_CHOICES = (
    {"id": "system", "label": "System", "family": ""},
    {"id": "source-sans", "label": "Source Sans 3", "family": "Source Sans 3"},
    {"id": "ibm-plex", "label": "IBM Plex Sans", "family": "IBM Plex Sans"},
    {"id": "outfit", "label": "Outfit", "family": "Outfit"},
    {"id": "literata", "label": "Literata", "family": "Literata"},
)
FONT_IDS = {item["id"] for item in FONT_CHOICES}
WEIGHT_CHOICES = (
    {"id": "200", "label": "Thin"},
    {"id": "300", "label": "Light"},
    {"id": "400", "label": "Regular"},
    {"id": "500", "label": "Medium"},
    {"id": "600", "label": "Semibold"},
    {"id": "700", "label": "Bold"},
)
WEIGHT_IDS = {item["id"] for item in WEIGHT_CHOICES}
THEME_IDS = ("light", "dark", "auto")
HISTORY_PERIODS = ("1", "7", "30", "90", "180", "ytd", "365", "730")
PAGE_VIEWS = ("volume", "history")
VOLUME_ORDERS = ("rank", "volume")
VOLUME_SCOPES = ("all", "sector")
# Automatic: light by day and dark in the evening, on the local clock.
DAY_START = 7
DAY_END = 19

DEFAULTS = {
    "profit_threshold": "0.05",
    "max_investment": "1000",
    "initial_capital": "10000",
    "names": "100",
    "chart_type": "line",
    "chart_render": "vector",
    "font_family": "system",
    "ui_scale": "100",
    "ui_weight": "400",
    "ui_theme": "light",
    "fee_rate": "0.001",
    "tax_rate": "0.26",
    "stable_band": "0.005",
    "history_days": "180",
    "return_days": "20",
    "focus_asset": "AAPL",
    "max_price_age_hours": "120",
    "max_hold_days": "120",
    "trail": "0.03",
    "sell_delay_score": "0.2",
    "notice_seconds": "8",
    "volume_class": "",
    "volume_order": "rank",
    "volume_scope": "sector",
    "history_period": "180",
    "page_view": "volume",
    "min_side": "0.36",
    "volume_divide": "off",
    "volume_scale": "off",
}

PREF_LABELS = {
    "profit_threshold": "Net profit threshold (0.05 = 5%)",
    "max_investment": "Maximum investment per buy",
    "initial_capital": "Starting paper capital",
    "names": "How many names to show (10 to 500, step 10)",
    "chart_type": "History chart",
    "chart_render": "History drawing: vector (SVG) by default, image (PNG) as the fallback for older machines",
    "font_family": "Typeface",
    "ui_scale": "Size and line spacing (%)",
    "ui_weight": "Weight",
    "ui_theme": "Theme",
    "fee_rate": "Commission (0.001 = 0.1%)",
    "tax_rate": "Tax on the gain (0.26 = 26%)",
    "stable_band": "Flat band (0.005 = ±0.5%)",
    "history_days": "History days on the chart",
    "return_days": "Sessions used to measure the return",
    "focus_asset": "History chart symbol",
    "max_price_age_hours": "Maximum price age for a sale (hours)",
    "max_hold_days": "Days after which a lot is sold at any result",
    "trail": "Drop from the peak that sells an armed lot (0.03 = 3%)",
    "sell_delay_score": "Score that keeps an armed lot",
    "notice_seconds": "Message seconds",
    "min_side": "Shorter side of a block, in the 16×9 frame. Below this the block is left out. A lower value keeps more blocks.",
    "volume_divide": "On keeps the shorter ratio when two contiguous blocks have two arrangements. Off keeps the first arrangement.",
    "volume_scale": "On uses the 1.618 ratio and the shifted colors. Off draws the earlier Volume All",
}


def ambient_theme(moment=None):
    """Light from 7 to 19, dark otherwise, on the clock of the moment."""
    moment = moment or datetime.now()
    return "light" if DAY_START <= moment.hour < DAY_END else "dark"


def resolved_theme(choice, moment=None):
    if choice == "auto":
        return ambient_theme(moment)
    if choice == "dark":
        return "dark"
    return "light"


def connect():
    cfg = db_config()
    if not cfg["user"] or not cfg["password"] or not cfg["database"]:
        raise RuntimeError("Database environment variables are missing")
    return mysql.connector.connect(**cfg)


def ensure_schema(conn):
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS market_history (
            id INT NOT NULL AUTO_INCREMENT,
            asset_name VARCHAR(255) NOT NULL,
            timestamp DATETIME NOT NULL,
            price DECIMAL(18,8) NOT NULL,
            open_price DECIMAL(18,8) NULL,
            high_price DECIMAL(18,8) NULL,
            low_price DECIMAL(18,8) NULL,
            volume DECIMAL(20,4) NULL,
            vwap DECIMAL(18,8) NULL,
            trade_count INT NULL,
            bar_ms BIGINT NULL,
            otc TINYINT(1) NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uniq_asset_ts (asset_name, timestamp),
            KEY idx_history_timestamp (timestamp)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS preferences (
            id INT NOT NULL AUTO_INCREMENT,
            name VARCHAR(255) NOT NULL,
            value VARCHAR(255) NOT NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uniq_pref_name (name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INT NOT NULL AUTO_INCREMENT,
            type VARCHAR(10) NOT NULL,
            asset_name VARCHAR(255) NOT NULL,
            amount DECIMAL(18,8) NOT NULL,
            price DECIMAL(18,8) NOT NULL,
            timestamp DATETIME NOT NULL,
            fees DECIMAL(18,8) NOT NULL,
            taxes DECIMAL(18,8) NOT NULL,
            currency VARCHAR(3) DEFAULT '$',
            fee_rate DECIMAL(10,6) NULL,
            tax_rate DECIMAL(10,6) NULL,
            taxable_gain DECIMAL(18,8) NULL,
            rates_source VARCHAR(10) NULL,
            recorded_at DATETIME NULL,
            PRIMARY KEY (id),
            KEY idx_tx_timestamp (timestamp),
            KEY idx_tx_type (type),
            KEY idx_tx_asset (asset_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute("SHOW COLUMNS FROM transactions")
    tx_columns = {row[0] for row in cur.fetchall()}
    if "currency" not in tx_columns:
        cur.execute("ALTER TABLE transactions ADD COLUMN currency VARCHAR(3) DEFAULT '$'")
    tx_additions = [
        f"ADD COLUMN {name} {kind}"
        for name, kind in (
            ("fee_rate", "DECIMAL(10,6) NULL"),
            ("tax_rate", "DECIMAL(10,6) NULL"),
            ("taxable_gain", "DECIMAL(18,8) NULL"),
            ("rates_source", "VARCHAR(10) NULL"),
            ("recorded_at", "DATETIME NULL"),
        )
        if name not in tx_columns
    ]
    if tx_additions:
        cur.execute("ALTER TABLE transactions " + ", ".join(tx_additions))
    cur.execute("SHOW COLUMNS FROM market_history")
    columns = {row[0] for row in cur.fetchall()}
    additions = []
    if "open_price" not in columns:
        additions.append("ADD COLUMN open_price DECIMAL(18,8) NULL")
    if "high_price" not in columns:
        additions.append("ADD COLUMN high_price DECIMAL(18,8) NULL")
    if "low_price" not in columns:
        additions.append("ADD COLUMN low_price DECIMAL(18,8) NULL")
    if "volume" not in columns:
        additions.append("ADD COLUMN volume DECIMAL(20,4) NULL")
    if "vwap" not in columns:
        additions.append("ADD COLUMN vwap DECIMAL(18,8) NULL")
    if "trade_count" not in columns:
        additions.append("ADD COLUMN trade_count INT NULL")
    if "bar_ms" not in columns:
        additions.append("ADD COLUMN bar_ms BIGINT NULL")
    if "otc" not in columns:
        additions.append("ADD COLUMN otc TINYINT(1) NULL")
    if additions:
        cur.execute("ALTER TABLE market_history " + ", ".join(additions))
    cur.execute("SHOW INDEX FROM market_history WHERE Key_name = 'uniq_asset_ts'")
    if not cur.fetchall():
        cur.execute(
            "ALTER TABLE market_history ADD UNIQUE KEY uniq_asset_ts (asset_name, timestamp)"
        )
    cur.execute("SHOW INDEX FROM preferences WHERE Key_name = 'uniq_pref_name'")
    if not cur.fetchall():
        cur.execute("ALTER TABLE preferences ADD UNIQUE KEY uniq_pref_name (name)")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS classification (
            code VARCHAR(220) NOT NULL,
            parent_code VARCHAR(220) NULL,
            name VARCHAR(160) NOT NULL,
            PRIMARY KEY (code),
            KEY idx_class_parent (parent_code),
            CONSTRAINT fk_class_parent FOREIGN KEY (parent_code) REFERENCES classification (code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_class (
            asset_name VARCHAR(16) NOT NULL,
            classification_code VARCHAR(220) NOT NULL,
            PRIMARY KEY (asset_name),
            KEY idx_asset_class (classification_code),
            CONSTRAINT fk_asset_class FOREIGN KEY (classification_code) REFERENCES classification (code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.close()
    conn.commit()
    backfill_transaction_rates(conn)


def backfill_transaction_rates(conn):
    """Rows written before rates were stored get the current preference rates.

    Only rows whose rates_source is NULL are touched, so a second run changes
    nothing. They are marked 'estimated': the true rate of that day is unknown.
    A sell also gets the gain it was taxed on, rebuilt with FIFO.
    """
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM transactions WHERE rates_source IS NULL")
    pending = cur.fetchone()[0]
    cur.close()
    if not pending:
        return 0
    prefs = load_preferences(conn)
    rows = fetch_transactions(conn)
    gains = taxable_gains_by_sale(rows)
    cur = conn.cursor()
    done = 0
    for tx in rows:
        if tx.get("rates_source") is not None:
            continue
        sell = (tx.get("type") or "").lower() == "sell"
        cur.execute(
            """
            UPDATE transactions
            SET fee_rate = %s, tax_rate = %s, taxable_gain = %s, rates_source = 'estimated'
            WHERE id = %s AND rates_source IS NULL
            """,
            (
                prefs["fee_rate"],
                prefs["tax_rate"] if sell else None,
                money(gains.get(tx["id"], Decimal("0"))) if sell else None,
                tx["id"],
            ),
        )
        done += cur.rowcount
    conn.commit()
    cur.close()
    log.info("transaction rates backfilled as estimated: %s rows", done)
    return done


def save_classifications(conn, rows):
    """Rows of (symbol, sector, sub-industry). The symbol points at the sub-industry, and that points at the sector."""
    usable = []
    for symbol, sector, sub in rows:
        symbol = normalize_ticker(symbol)
        sector = (sector or "").strip()
        sub = (sub or "").strip()
        if symbol and sector and sub and "\t" not in sector and "\t" not in sub:
            usable.append((symbol, sector, sub))
    if not usable:
        return 0
    cur = conn.cursor()
    for sector in sorted({sector for _symbol, sector, _sub in usable}):
        cur.execute(
            """
            INSERT INTO classification (code, parent_code, name) VALUES (%s, NULL, %s)
            ON DUPLICATE KEY UPDATE name = VALUES(name)
            """,
            (sector, sector),
        )
    for _symbol, sector, sub in usable:
        cur.execute(
            """
            INSERT INTO classification (code, parent_code, name) VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE parent_code = VALUES(parent_code), name = VALUES(name)
            """,
            (sector + "\t" + sub, sector, sub),
        )
    for symbol, sector, sub in usable:
        cur.execute(
            """
            INSERT INTO asset_class (asset_name, classification_code) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE classification_code = VALUES(classification_code)
            """,
            (symbol, sector + "\t" + sub),
        )
    conn.commit()
    cur.close()
    return len(usable)


def seed_preferences(conn):
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE preferences AS old
        LEFT JOIN preferences AS neu ON neu.name = 'names'
        SET old.name = 'names'
        WHERE old.name = 'universe_size' AND neu.name IS NULL
        """
    )
    cur.execute("DELETE FROM preferences WHERE name = 'universe_size'")
    for name, value in DEFAULTS.items():
        cur.execute(
            """
            INSERT INTO preferences (name, value) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE name = name
            """,
            (name, value),
        )
    conn.commit()
    cur.close()


def load_preferences(conn):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT name, value FROM preferences")
    raw = dict(DEFAULTS)
    for row in cur.fetchall():
        raw[row["name"]] = row["value"]
    cur.close()
    return interpret(raw)


def interpret(raw):
    prefs = {
        "profit_threshold": _decimal(raw.get("profit_threshold"), "0.05"),
        "max_investment": _decimal(raw.get("max_investment"), "1000"),
        "initial_capital": _decimal(raw.get("initial_capital"), "10000"),
        "names": _step_between(raw.get("names"), 10, 500, 10, 100),
        "volume_class": (raw.get("volume_class") or "").strip(),
        "chart_type": raw.get("chart_type") if raw.get("chart_type") in ("line", "candle") else "line",
        "chart_render": raw.get("chart_render") if raw.get("chart_render") in ("image", "vector") else "vector",
        "font_family": raw.get("font_family") if raw.get("font_family") in FONT_IDS else "system",
        "ui_scale": str(_step_between(raw.get("ui_scale"), 80, 120, 5, 100)),
        "ui_weight": raw.get("ui_weight") if raw.get("ui_weight") in WEIGHT_IDS else "400",
        "ui_theme": raw.get("ui_theme") if raw.get("ui_theme") in THEME_IDS else "light",
        "fee_rate": _decimal(raw.get("fee_rate"), "0.001"),
        "tax_rate": _decimal(raw.get("tax_rate"), "0.26"),
        "stable_band": _decimal(raw.get("stable_band"), "0.005"),
        "history_days": _int_between(raw.get("history_days"), 30, 1825, 180),
        "return_days": _int_between(raw.get("return_days"), 1, 240, 20),
        "focus_asset": normalize_ticker(raw.get("focus_asset") or "AAPL") or "AAPL",
        "max_price_age_hours": _int_between(raw.get("max_price_age_hours"), 1, 720, 120),
        "max_hold_days": _int_between(raw.get("max_hold_days"), 1, 3650, 120),
        "trail": _decimal_between(raw.get("trail"), Decimal("0"), Decimal("0.5"), "0.03"),
        "sell_delay_score": _decimal_between(raw.get("sell_delay_score"), Decimal("-1"), Decimal("1"), "0.2"),
        "notice_seconds": _int_between(raw.get("notice_seconds"), 3, 30, 8),
        "volume_order": raw.get("volume_order") if raw.get("volume_order") in VOLUME_ORDERS else "rank",
        "volume_scope": raw.get("volume_scope") if raw.get("volume_scope") in VOLUME_SCOPES else "sector",
        "history_period": raw.get("history_period") if raw.get("history_period") in HISTORY_PERIODS else "180",
        "page_view": raw.get("page_view") if raw.get("page_view") in PAGE_VIEWS else "volume",
        "min_side": _side(raw.get("min_side")),
        "volume_divide": raw.get("volume_divide") if raw.get("volume_divide") in ("off", "on") else "off",
        "volume_scale": raw.get("volume_scale") if raw.get("volume_scale") in ("off", "on") else "off",
    }
    return prefs


def validate_preferences(form):
    """Returns (values_to_save, error)."""
    try:
        profit = Decimal(str(form["profit_threshold"]).replace(",", "."))
        investment = Decimal(str(form["max_investment"]).replace(",", "."))
        fee = Decimal(str(form["fee_rate"]).replace(",", "."))
        tax = Decimal(str(form["tax_rate"]).replace(",", "."))
        band = Decimal(str(form["stable_band"]).replace(",", "."))
        history_days = int(form["history_days"])
        return_days = int(form["return_days"])
        age = int(form["max_price_age_hours"])
        notice = int(form["notice_seconds"])
        count = int(form["names"])
    except (KeyError, ValueError, ArithmeticError):
        return None, tr("prefs.err.numbers")
    focus = normalize_ticker(form.get("focus_asset", ""))
    chart = form.get("chart_type")
    render = form.get("chart_render")
    font = form.get("font_family")
    weight = form.get("ui_weight")
    theme = form.get("ui_theme")
    try:
        scale = int(form.get("ui_scale", ""))
    except (TypeError, ValueError):
        return None, tr("prefs.err.scale_read")
    if not (Decimal("0") <= profit <= Decimal("5")):
        return None, tr("prefs.err.profit")
    if investment <= 0:
        return None, tr("prefs.err.invest")
    if not (Decimal("0") <= fee <= Decimal("0.1")):
        return None, tr("prefs.err.fee")
    if not (Decimal("0") <= tax <= Decimal("0.5")):
        return None, tr("prefs.err.tax")
    if not (Decimal("0") <= band <= Decimal("0.2")):
        return None, tr("prefs.err.band")
    if not 10 <= count <= 500 or count % 10 != 0:
        return None, tr("prefs.err.names")
    if chart not in ("line", "candle"):
        return None, tr("prefs.err.chart")
    if render not in ("image", "vector"):
        return None, tr("prefs.err.draw")
    if font not in FONT_IDS:
        return None, tr("prefs.err.font")
    if not 80 <= scale <= 120 or scale % 5 != 0:
        return None, tr("prefs.err.scale")
    if weight not in WEIGHT_IDS:
        return None, tr("prefs.err.weight")
    if theme not in THEME_IDS:
        return None, tr("prefs.err.theme")
    if not focus:
        return None, tr("prefs.err.symbol")
    if not (30 <= history_days <= 1825 and 1 <= return_days <= 240 and 1 <= age <= 720):
        return None, tr("prefs.err.limits")
    if not 3 <= notice <= 30:
        return None, tr("prefs.err.notice")
    values = {
        "profit_threshold": format(profit.normalize(), "f"),
        "max_investment": format(investment.normalize(), "f"),
        "names": str(count),
        "chart_type": chart,
        "chart_render": render,
        "font_family": font,
        "ui_scale": str(scale),
        "ui_weight": weight,
        "ui_theme": theme,
        "fee_rate": format(fee.normalize(), "f"),
        "tax_rate": format(tax.normalize(), "f"),
        "stable_band": format(band.normalize(), "f"),
        "history_days": str(history_days),
        "return_days": str(return_days),
        "focus_asset": focus,
        "max_price_age_hours": str(age),
        "notice_seconds": str(notice),
    }
    return values, None


def preference_patch(form, clamped=None):
    """Validate the posted keys only. Returns (values, error).

    A number outside its range is clamped to the nearest bound (and to the step);
    the names clamped are appended to clamped when a list is given. Unreadable
    text is an error.
    """
    values = {}

    if clamped is None:
        clamped = []

    def decimal_value(name, low, high, error):
        try:
            number = Decimal(str(form[name]).strip().replace(",", "."))
        except (ArithmeticError, ValueError):
            return None, tr("prefs.err.numbers")
        if not number.is_finite():
            return None, tr("prefs.err.numbers")
        if number < low or number > high:
            number = min(max(number, low), high)
            clamped.append(name)
        return format(number.normalize(), "f"), None

    def int_value(name, low, high, error, step=None):
        try:
            number = int(str(form[name]).strip())
        except (TypeError, ValueError):
            return None, tr("prefs.err.numbers")
        fixed = min(max(number, low), high)
        if step:
            fixed = min(max(int(round(fixed / step)) * step, low), high)
        if fixed != number:
            clamped.append(name)
        return str(fixed), None

    checks = (
        ("profit_threshold", lambda: decimal_value("profit_threshold", Decimal("0"), Decimal("5"), "prefs.err.profit")),
        ("max_investment", lambda: decimal_value("max_investment", Decimal("1"), Decimal("1E24"), "prefs.err.invest")),
        ("initial_capital", lambda: decimal_value("initial_capital", Decimal("1"), Decimal("1E24"), "prefs.err.capital")),
        ("fee_rate", lambda: decimal_value("fee_rate", Decimal("0"), Decimal("0.1"), "prefs.err.fee")),
        ("tax_rate", lambda: decimal_value("tax_rate", Decimal("0"), Decimal("0.5"), "prefs.err.tax")),
        ("stable_band", lambda: decimal_value("stable_band", Decimal("0"), Decimal("0.2"), "prefs.err.band")),
        ("min_side", lambda: decimal_value("min_side", Decimal("0"), Decimal("2"), "prefs.err.side")),
        ("return_days", lambda: int_value("return_days", 1, 240, "prefs.err.limits")),
        ("names", lambda: int_value("names", 10, 500, "prefs.err.names", 10)),
        ("max_price_age_hours", lambda: int_value("max_price_age_hours", 1, 720, "prefs.err.limits")),
        ("max_hold_days", lambda: int_value("max_hold_days", 1, 3650, "prefs.err.hold")),
        ("trail", lambda: decimal_value("trail", Decimal("0"), Decimal("0.5"), "prefs.err.trail")),
        ("sell_delay_score", lambda: decimal_value("sell_delay_score", Decimal("-1"), Decimal("1"), "prefs.err.delay")),
        ("notice_seconds", lambda: int_value("notice_seconds", 3, 30, "prefs.err.notice")),
        ("ui_scale", lambda: int_value("ui_scale", 80, 120, "prefs.err.scale", 5)),
    )
    for name, read in checks:
        if name not in form:
            continue
        stored, error = read()
        if error:
            return None, error
        values[name] = stored
    if "focus_asset" in form:
        focus = normalize_ticker(form.get("focus_asset", ""))
        if not focus:
            return None, tr("prefs.err.symbol")
        values["focus_asset"] = focus
    enums = (
        ("chart_type", ("line", "candle"), "prefs.err.chart"),
        ("chart_render", ("image", "vector"), "prefs.err.draw"),
        ("font_family", FONT_IDS, "prefs.err.font"),
        ("ui_weight", WEIGHT_IDS, "prefs.err.weight"),
        ("ui_theme", THEME_IDS, "prefs.err.theme"),
        ("history_period", HISTORY_PERIODS, "prefs.err.limits"),
        ("page_view", PAGE_VIEWS, "prefs.err.limits"),
        ("volume_order", VOLUME_ORDERS, "prefs.err.limits"),
        ("volume_scope", VOLUME_SCOPES, "prefs.err.limits"),
        ("volume_divide", ("off", "on"), "prefs.err.limits"),
        ("volume_scale", ("off", "on"), "prefs.err.limits"),
    )
    for name, allowed, error in enums:
        if name not in form:
            continue
        value = form.get(name)
        if value not in allowed:
            return None, tr(error)
        values[name] = value
    if not values:
        return None, tr("prefs.err.numbers")
    return values, None


def save_preferences(conn, values):
    cur = conn.cursor()
    for name, value in values.items():
        cur.execute(
            """
            INSERT INTO preferences (name, value) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE value = VALUES(value)
            """,
            (name, value),
        )
    conn.commit()
    cur.close()


def upsert_bars(conn, rows):
    if not rows:
        return 0
    sql = """
        INSERT INTO market_history
            (asset_name, timestamp, price, open_price, high_price, low_price, volume,
             vwap, trade_count, bar_ms, otc)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            price = VALUES(price),
            open_price = VALUES(open_price),
            high_price = VALUES(high_price),
            low_price = VALUES(low_price),
            volume = VALUES(volume),
            vwap = COALESCE(VALUES(vwap), vwap),
            trade_count = COALESCE(VALUES(trade_count), trade_count),
            bar_ms = COALESCE(VALUES(bar_ms), bar_ms),
            otc = COALESCE(VALUES(otc), otc)
    """
    payload = [
        (
            row["asset_name"],
            row["timestamp"],
            row["price"],
            row["open_price"],
            row["high_price"],
            row["low_price"],
            row["volume"],
            row.get("vwap"),
            row.get("trade_count"),
            row.get("bar_ms"),
            row.get("otc"),
        )
        for row in rows
    ]
    cur = conn.cursor()
    for start in range(0, len(payload), 400):
        cur.executemany(sql, payload[start : start + 400])
    conn.commit()
    cur.close()
    return len(payload)


def history_coverage(conn, symbols):
    """How many bars each name has, and how recent they are, to decide the download."""
    if not symbols:
        return {}
    cur = conn.cursor()
    placeholders = ", ".join(["%s"] * len(symbols))
    cur.execute(
        f"""
        SELECT asset_name, COUNT(*), MAX(timestamp)
        FROM market_history
        WHERE asset_name IN ({placeholders})
        GROUP BY asset_name
        """,
        tuple(symbols),
    )
    found = {name: (count, latest) for name, count, latest in cur.fetchall()}
    cur.close()
    return found


def load_bars_since(conn, days):
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT asset_name, timestamp, price, volume
        FROM market_history
        WHERE asset_name <> 'test'
          AND timestamp >= (NOW() - INTERVAL %s DAY)
        ORDER BY asset_name, timestamp
        """,
        (int(days),),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def market_window_fingerprint(conn, days):
    """Cheap identity of the volume-board bar window (count + newest stamp)."""
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT COUNT(*) AS n, MAX(timestamp) AS last_ts
        FROM market_history
        WHERE asset_name <> 'test'
          AND timestamp >= (NOW() - INTERVAL %s DAY)
        """,
        (int(days),),
    )
    row = cur.fetchone() or {}
    cur.close()
    n = int(row.get("n") or 0)
    stamp = row.get("last_ts")
    if not n or not stamp:
        return "empty"
    if hasattr(stamp, "isoformat"):
        stamp = stamp.isoformat(sep=" ", timespec="seconds")
    return f"{n}|{stamp}"


def load_asset_history(conn, asset, days):
    if int(days) == 1:
        return _load_one_day(conn, asset)
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT timestamp, price, open_price, high_price, low_price, volume, vwap
        FROM market_history
        WHERE asset_name = %s
          AND timestamp >= (NOW() - INTERVAL %s DAY)
        ORDER BY timestamp
        """,
        (asset, int(days)),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def _bar_fingerprint(count, last):
    if not count or not last:
        return "empty"
    stamp = last["timestamp"]
    if hasattr(stamp, "isoformat"):
        stamp = stamp.isoformat(sep=" ", timespec="seconds")
    return f"{count}|{stamp}|{last.get('price')}|{last.get('volume')}"


def asset_history_fingerprint(conn, asset, days):
    """Row count + last bar identity. Cheap enough to check the chart cache first."""
    if int(days) == 1:
        series = _load_one_day(conn, asset)
        return _bar_fingerprint(len(series), series[-1] if series else None)
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT COUNT(*) AS n
        FROM market_history
        WHERE asset_name = %s
          AND timestamp >= (NOW() - INTERVAL %s DAY)
        """,
        (asset, int(days)),
    )
    count_row = cur.fetchone() or {}
    n = int(count_row.get("n") or 0)
    if n <= 0:
        cur.close()
        return "empty"
    cur.execute(
        """
        SELECT timestamp, price, volume
        FROM market_history
        WHERE asset_name = %s
          AND timestamp >= (NOW() - INTERVAL %s DAY)
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (asset, int(days)),
    )
    last = cur.fetchone()
    cur.close()
    return _bar_fingerprint(n, last)


def _load_one_day(conn, asset):
    """The newest stored session and the one before it, when that pair is still current."""
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT timestamp, price, open_price, high_price, low_price, volume, vwap
        FROM market_history
        WHERE asset_name = %s
        ORDER BY timestamp DESC
        LIMIT 2
        """,
        (asset,),
    )
    rows = cur.fetchall()
    cur.close()
    if len(rows) < 2:
        return []
    newest = rows[0]["timestamp"]
    newest_day = newest.date() if hasattr(newest, "date") else newest
    floor = one_day_floor(datetime.now(NEW_YORK).date())
    if floor is not None and newest_day < floor:
        return []
    rows.reverse()
    return rows


def list_assets(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT asset_name
        FROM market_history
        WHERE asset_name <> 'test'
        GROUP BY asset_name
        ORDER BY asset_name
        """
    )
    names = [row[0] for row in cur.fetchall()]
    cur.close()
    return names


def latest_prices(conn):
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT h.asset_name, h.timestamp, h.price
        FROM market_history h
        INNER JOIN (
            SELECT asset_name, MAX(timestamp) AS ts
            FROM market_history
            GROUP BY asset_name
        ) last_row ON last_row.asset_name = h.asset_name AND last_row.ts = h.timestamp
        """
    )
    prices = {row["asset_name"]: row for row in cur.fetchall()}
    cur.close()
    return prices


def fetch_transactions(conn):
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT id, type, asset_name, amount, price, timestamp, fees, taxes, currency,
            fee_rate, tax_rate, taxable_gain, rates_source, recorded_at
        FROM transactions
        ORDER BY timestamp, id
        """
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def recent_transactions(conn, prefs, limit=20):
    """Transactions panel: newest closed FIFO slices, open lots, totals.

    limit applies to closed slices (newest first). Open lots are all returned,
    each valued at the latest stored price with the current fee and tax rates.
    Totals cover every transaction, not only the slices shown.
    """
    views = fifo_transaction_views(
        fetch_transactions(conn),
        latest_prices(conn),
        prefs["fee_rate"],
        prefs["tax_rate"],
    )
    closed = list(reversed(views["closed"]))[: int(limit)]
    return {"closed": closed, "open": views["open"], "totals": views["totals"]}


def paper_balance(conn, prefs):
    """Current paper cash (Balance) from initial capital and all transactions."""
    return paper_cash_balance(fetch_transactions(conn), prefs["initial_capital"])


def insert_transaction(
    conn,
    kind,
    asset,
    amount,
    price,
    fees,
    taxes,
    when=None,
    currency=CURRENCY,
    fee_rate=None,
    tax_rate=None,
    taxable_gain=None,
):
    """Writes one buy or sell with the rates it was computed with.

    when is the session the price belongs to (a bar date is midnight);
    recorded_at is the moment of the write.
    """
    now = datetime.now().replace(microsecond=0)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO transactions
            (type, asset_name, amount, price, timestamp, fees, taxes, currency,
             fee_rate, tax_rate, taxable_gain, rates_source, recorded_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'recorded', %s)
        """,
        (
            kind,
            asset,
            money(amount),
            money(price),
            when or now,
            money(fees),
            money(taxes),
            currency,
            fee_rate,
            tax_rate,
            money(taxable_gain),
            now,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    cur.close()
    log.info(
        "transazione %s id=%s %s qty=%s price=%s fees=%s taxes=%s fee_rate=%s tax_rate=%s",
        kind,
        new_id,
        asset,
        amount,
        price,
        fees,
        taxes,
        fee_rate,
        tax_rate,
    )
    return new_id


def classification_tree(conn):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT code, parent_code, name FROM classification")
    rows = cur.fetchall()
    cur.close()
    subs = {}
    sectors = []
    for row in rows:
        if row["parent_code"]:
            subs.setdefault(row["parent_code"], []).append(row)
        else:
            sectors.append(row)
    tree = []
    for sector in sorted(sectors, key=lambda item: item["name"]):
        children = sorted(subs.get(sector["code"], []), key=lambda item: item["name"])
        tree.append({"name": sector["name"], "code": sector["code"], "subs": children})
    return tree


def accepted_volume_class(conn, raw):
    """Empty string: every name. s:sector or u:sector|sub-industry."""
    text = (raw or "").strip()
    if not text:
        return ""
    cur = conn.cursor()
    if text.startswith("s:") and "|" not in text and "\t" not in text:
        cur.execute(
            "SELECT 1 FROM classification WHERE parent_code IS NULL AND code = %s",
            (text[2:],),
        )
        found = cur.fetchone() is not None
        cur.close()
        return text if found else ""
    if text.startswith("u:") and text.count("|") == 1:
        sector, sub = text[2:].split("|", 1)
        if sector and sub and "\t" not in sector and "\t" not in sub:
            cur.execute(
                "SELECT 1 FROM classification WHERE code = %s AND parent_code = %s",
                (sector + "\t" + sub, sector),
            )
            found = cur.fetchone() is not None
            cur.close()
            return text if found else ""
    cur.close()
    return ""


def class_symbols(conn, volume_class):
    """None means every symbol. An empty set draws nothing."""
    if not volume_class:
        return None
    cur = conn.cursor()
    if volume_class.startswith("s:"):
        cur.execute(
            """
            SELECT ac.asset_name
            FROM asset_class ac
            JOIN classification sub ON sub.code = ac.classification_code
            WHERE sub.parent_code = %s
            """,
            (volume_class[2:],),
        )
    else:
        sector, sub = volume_class[2:].split("|", 1)
        cur.execute(
            "SELECT asset_name FROM asset_class WHERE classification_code = %s",
            (sector + "\t" + sub,),
        )
    names = {row[0] for row in cur.fetchall()}
    cur.close()
    return names


def symbol_places(conn):
    """Symbol to its sector name and group name."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ac.asset_name, sector.name, sub.name
        FROM asset_class ac
        JOIN classification sub ON sub.code = ac.classification_code
        JOIN classification sector ON sector.code = sub.parent_code
        """
    )
    places = {asset: (sector, group) for asset, sector, group in cur.fetchall()}
    cur.close()
    return places


def build_blocks(rows, prefs, allowed=None, limit=True):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["asset_name"], []).append(row)
    blocks = []
    band = prefs["stable_band"]
    window = prefs["return_days"]
    for asset, bars in grouped.items():
        if allowed is not None and asset not in allowed:
            continue
        last = bars[-1]
        volume = last.get("volume")
        if volume is None or Decimal(str(volume)) <= 0:
            continue
        previous = bars[-2] if len(bars) > 1 else last
        anchor = bars[max(0, len(bars) - 1 - window)]
        last_price = Decimal(str(last["price"]))
        prev_price = Decimal(str(previous["price"]))
        anchor_price = Decimal(str(anchor["price"]))
        if prev_price == 0 or anchor_price == 0 or last_price <= 0:
            continue
        daily = (last_price - prev_price) / prev_price
        trail = (last_price - anchor_price) / anchor_price
        if abs(daily) < band:
            state = "stabile"
        elif daily > 0:
            state = "crescita"
        else:
            state = "perdita"
        blocks.append(
            {
                "asset": asset,
                "price": last_price,
                "volume": Decimal(str(volume)),
                "daily": daily,
                "trail": trail,
                "state": state,
                "timestamp": last["timestamp"],
            }
        )
    blocks.sort(key=lambda item: item["trail"], reverse=True)
    if limit:
        return blocks[: prefs["names"]]
    return blocks


def position_rows(conn, prefs):
    lots, _unmatched = open_lots(fetch_transactions(conn))
    prices = latest_prices(conn)
    rows = []
    now = datetime.now()
    max_age = prefs["max_price_age_hours"] * 3600
    for lot in lots:
        market = prices.get(lot.asset)
        quote = None
        stale = True
        if market:
            age = (now - market["timestamp"]).total_seconds()
            stale = age > max_age
            quote = quote_sell(lot, market["price"], prefs["fee_rate"], prefs["tax_rate"])
        ratio = None if quote is None else quote["ratio"]
        ready = (
            quote is not None
            and ratio is not None
            and ratio >= prefs["profit_threshold"]
            and not stale
        )
        if market is None:
            outcome = tr("positions.no_price")
        elif stale:
            outcome = tr("positions.stale")
        elif ready:
            outcome = tr("positions.ready")
            peak = None
            if lot.timestamp is not None:
                peak = armed_peak(
                    lot,
                    closes_since(conn, lot.asset, lot.timestamp),
                    prefs["fee_rate"],
                    prefs["tax_rate"],
                    prefs["profit_threshold"],
                )
            if peak is not None:
                outcome = tr(
                    "positions.armed",
                    peak=f"{peak:.3f}",
                    drop=f"{peak_drop(peak, quote['price']) * 100:.3f}",
                )
        else:
            outcome = tr("positions.below")
        rows.append(
            {
                "lot_id": lot.tx_id,
                "asset": lot.asset,
                "currency": lot.currency,
                "amount": lot.remaining,
                "buy_price": lot.price,
                "bought_at": lot.timestamp,
                "market_price": None if market is None else Decimal(str(market["price"])),
                "market_time": None if market is None else market["timestamp"],
                "ratio": ratio,
                "ready": ready,
                "outcome": outcome,
            }
        )
    return rows


def sell_open_lot(conn, prefs, lot_id):
    """Paper-sell one open lot by buy transaction id.

    Same quote_sell + insert_transaction path as automatic sales. Refuses a
    missing or stale market price. Returns (asset, None) on success, or
    (None, catalog key) on refusal.
    """
    try:
        lot_id = int(lot_id)
    except (TypeError, ValueError):
        return None, "sell.bad_lot"
    lots, _unmatched = open_lots(fetch_transactions(conn))
    lot = next((item for item in lots if item.tx_id == lot_id), None)
    if lot is None:
        return None, "sell.missing"
    market = latest_prices(conn).get(lot.asset)
    if not market:
        return None, "sell.no_price"
    now = datetime.now()
    max_age = prefs["max_price_age_hours"] * 3600
    if (now - market["timestamp"]).total_seconds() > max_age:
        return None, "sell.stale"
    quote = quote_sell(lot, market["price"], prefs["fee_rate"], prefs["tax_rate"])
    if quote is None:
        return None, "sell.no_price"
    insert_transaction(
        conn,
        "sell",
        lot.asset,
        quote["amount"],
        quote["price"],
        quote["fees"],
        quote["taxes"],
        now.replace(microsecond=0),
        lot.currency,
        quote["fee_rate"],
        quote["tax_rate"],
        quote["taxable_gain"],
    )
    log.info(
        "manual sale %s qty=%s price=%s net_profit=%s",
        lot.asset,
        quote["amount"],
        quote["price"],
        quote["ratio"],
    )
    return lot.asset, None


def closes_since(conn, asset, since):
    """(timestamp, close) of one name from the session of since on, oldest first."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT timestamp, price
        FROM market_history
        WHERE asset_name = %s AND timestamp >= %s
        ORDER BY timestamp
        """,
        (asset, datetime.combine(since.date(), datetime.min.time())),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def lot_scores(conn, lots):
    """Score number per held name, from the same reading as the decision."""
    from bot_decide import scores_for

    found = scores_for(conn, [lot.asset for lot in lots])
    return {asset: row["score"] for asset, row in found.items()}


def threshold_review(conn, prefs, lots=None, scores=None, now=None):
    """One entry per open lot with a fresh price: quote, peak since arming, drop, score, and the
    reason to sell now (floor, trail, score) or None to keep. Nothing is written."""
    if lots is None:
        lots, _unmatched = open_lots(fetch_transactions(conn))
    prices = latest_prices(conn)
    now = now or datetime.now()
    max_age = prefs["max_price_age_hours"] * 3600
    review = []
    for lot in lots:
        market = prices.get(lot.asset)
        if not market:
            continue
        if (now - market["timestamp"]).total_seconds() > max_age:
            log.info("keeping %s: price from %s is too old", lot.asset, market["timestamp"])
            continue
        quote = quote_sell(lot, market["price"], prefs["fee_rate"], prefs["tax_rate"])
        if quote is None or quote["ratio"] is None:
            continue
        peak = None
        if lot.timestamp is not None:
            peak = armed_peak(
                lot,
                closes_since(conn, lot.asset, lot.timestamp),
                prefs["fee_rate"],
                prefs["tax_rate"],
                prefs["profit_threshold"],
            )
        score = None
        if peak is not None:
            if scores is None:
                scores = lot_scores(conn, lots)
            score = scores.get(lot.asset)
        review.append(
            {
                "lot": lot,
                "quote": quote,
                "peak": peak,
                "drop": peak_drop(peak, quote["price"]),
                "score": score,
                "reason": trail_exit(quote, peak, score, prefs),
            }
        )
    return review


def sell_ready_lots(conn, prefs, scores=None):
    """Sells the armed lots the trailing rule lets go. Returns the number of sales.

    A lot is armed once a close since the buy brought its net ratio to the
    threshold. It is kept while the score stays at or above sell_delay_score
    and the close is less than trail under the peak since arming; it is sold
    when either fails or when the ratio falls back to the threshold.
    """
    lots, unmatched = open_lots(fetch_transactions(conn))
    if unmatched > 0:
        log.warning("sales without a matching buy, residual quantity %s", unmatched)
    now = datetime.now()
    sold = 0
    for item in threshold_review(conn, prefs, lots, scores, now):
        lot, quote = item["lot"], item["quote"]
        if item["reason"] is None:
            if item["peak"] is not None:
                log.info(
                    "keeping %s: armed, net_profit=%s peak=%s drop=%s score=%s",
                    lot.asset,
                    quote["ratio"],
                    item["peak"],
                    item["drop"],
                    item["score"],
                )
            continue
        insert_transaction(
            conn,
            "sell",
            lot.asset,
            quote["amount"],
            quote["price"],
            quote["fees"],
            quote["taxes"],
            now.replace(microsecond=0),
            lot.currency,
            quote["fee_rate"],
            quote["tax_rate"],
            quote["taxable_gain"],
        )
        sold += 1
        log.info(
            "sale %s qty=%s price=%s net_profit=%s threshold=%s reason=%s peak=%s score=%s",
            lot.asset,
            quote["amount"],
            quote["price"],
            quote["ratio"],
            prefs["profit_threshold"],
            item["reason"],
            item["peak"],
            item["score"],
        )
    return sold


def read_status():
    if not STATUS_PATH.exists():
        return {"state": "idle", "message": "prices.idle", "updated": ""}
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "idle", "message": "prices.unreadable", "updated": ""}


def write_status(state, message):
    payload = {
        "state": state,
        "message": message,
        "updated": datetime.now().replace(microsecond=0).isoformat(sep=" "),
    }
    temporary = STATUS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(temporary, STATUS_PATH)


def cycle_running():
    if not LOCK_PATH.exists():
        return False
    try:
        pid = int(LOCK_PATH.read_text(encoding="utf-8").strip())
        command = open(f"/proc/{pid}/cmdline", "rb").read()
    except (OSError, ValueError):
        return False
    return b"cycle.py" in command or b"cycle_reread.py" in command


def _side(value):
    number = _decimal(value, "0.36")
    if not (Decimal("0") <= number <= Decimal("2")):
        return Decimal("0.36")
    return number


def _decimal(value, fallback):
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return Decimal(fallback)


def _decimal_between(value, low, high, fallback):
    number = _decimal(value, fallback)
    if not number.is_finite() or number < low or number > high:
        return Decimal(fallback)
    return number


def _int_between(value, low, high, fallback):
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return fallback
    if number < low or number > high:
        return fallback
    return number


def _step_between(value, low, high, step, fallback):
    number = _int_between(value, low, high, fallback)
    snapped = int(round(number / step) * step)
    if snapped < low:
        snapped = low
    if snapped > high:
        snapped = high
    return snapped


def _choice_int(value, choices, fallback):
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return fallback
    return number if number in choices else fallback


def normalize_ticker(value):
    text = (value or "").strip().upper().replace(".", "-")
    if not text or len(text) > 12:
        return None
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")
    if text[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        return None
    if any(char not in allowed for char in text):
        return None
    return text


def quantize_volume(value):
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return number.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
