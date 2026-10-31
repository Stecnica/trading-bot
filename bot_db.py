"""Schema, preferenze, prezzi e transazioni."""

import json
import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

import mysql.connector

from bot_config import LOCK_PATH, STATUS_PATH, db_config, get_logger
from bot_logic import money, open_lots, quote_sell

log = get_logger()

FONT_CHOICES = (
    {"id": "system", "label": "Sistema", "family": ""},
    {"id": "source-sans", "label": "Source Sans 3", "family": "Source Sans 3"},
    {"id": "ibm-plex", "label": "IBM Plex Sans", "family": "IBM Plex Sans"},
    {"id": "outfit", "label": "Outfit", "family": "Outfit"},
    {"id": "literata", "label": "Literata", "family": "Literata"},
)
FONT_IDS = {item["id"] for item in FONT_CHOICES}
WEIGHT_CHOICES = (
    {"id": "200", "label": "Sottile"},
    {"id": "300", "label": "Leggero"},
    {"id": "400", "label": "Normale"},
    {"id": "500", "label": "Medio"},
    {"id": "600", "label": "Semigrassetto"},
    {"id": "700", "label": "Grassetto"},
)
WEIGHT_IDS = {item["id"] for item in WEIGHT_CHOICES}
THEME_IDS = ("light", "dark", "auto")
# Automatico: chiaro di giorno e scuro di sera, sull'ora locale.
DAY_START = 7
DAY_END = 19

DEFAULTS = {
    "profit_threshold": "0.05",
    "max_investment": "1000",
    "universe_size": "100",
    "chart_type": "line",
    "chart_render": "image",
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
    "notice_seconds": "8",
    "volume_class": "",
}

PREF_LABELS = {
    "profit_threshold": "Soglia di profitto netto (0.05 = 5%)",
    "max_investment": "Investimento massimo per acquisto",
    "universe_size": "Quanti titoli mostrare (da 10 a 500, a passi di 10)",
    "chart_type": "Grafico storico",
    "chart_render": "Disegno dello storico",
    "font_family": "Carattere",
    "ui_scale": "Dimensione e interlinea (%)",
    "ui_weight": "Peso",
    "ui_theme": "Tema",
    "fee_rate": "Commissione (0.001 = 0,1%)",
    "tax_rate": "Imposta sul guadagno (0.26 = 26%)",
    "stable_band": "Banda di stabilità (0.005 = ±0,5%)",
    "history_days": "Giorni di storico nel grafico",
    "return_days": "Sedute per misurare il rendimento",
    "focus_asset": "Titolo del grafico storico",
    "max_price_age_hours": "Età massima del prezzo per vendere (ore)",
    "notice_seconds": "Secondi del messaggio",
}


def ambient_theme(moment=None):
    """Chiaro dalle 7 alle 19, scuro nel resto, sull'ora del momento."""
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
        raise RuntimeError("Variabili d'ambiente del database assenti")
    return mysql.connector.connect(**cfg)


def ensure_schema(conn):
    cur = conn.cursor()
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


def save_classifications(conn, rows):
    """Righe (simbolo, settore, sotto-industria). Il simbolo punta alla sotto-industria, e quella al settore."""
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
        "universe_size": _step_between(raw.get("universe_size"), 10, 500, 10, 100),
        "volume_class": (raw.get("volume_class") or "").strip(),
        "chart_type": raw.get("chart_type") if raw.get("chart_type") in ("line", "candle") else "line",
        "chart_render": raw.get("chart_render") if raw.get("chart_render") in ("image", "vector") else "image",
        "font_family": raw.get("font_family") if raw.get("font_family") in FONT_IDS else "system",
        "ui_scale": str(_step_between(raw.get("ui_scale"), 80, 120, 5, 100)),
        "ui_weight": raw.get("ui_weight") if raw.get("ui_weight") in WEIGHT_IDS else "400",
        "ui_theme": raw.get("ui_theme") if raw.get("ui_theme") in THEME_IDS else "light",
        "fee_rate": _decimal(raw.get("fee_rate"), "0.001"),
        "tax_rate": _decimal(raw.get("tax_rate"), "0.26"),
        "stable_band": _decimal(raw.get("stable_band"), "0.005"),
        "history_days": _int_between(raw.get("history_days"), 30, 1825, 180),
        "return_days": _int_between(raw.get("return_days"), 1, 120, 20),
        "focus_asset": normalize_ticker(raw.get("focus_asset") or "AAPL") or "AAPL",
        "max_price_age_hours": _int_between(raw.get("max_price_age_hours"), 1, 720, 120),
        "notice_seconds": _int_between(raw.get("notice_seconds"), 3, 30, 8),
    }
    return prefs


def validate_preferences(form):
    """Ritorna (valori_da_salvare, errore)."""
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
        universe = int(form["universe_size"])
    except (KeyError, ValueError, ArithmeticError):
        return None, "Uno dei valori numerici non è leggibile."
    focus = normalize_ticker(form.get("focus_asset", ""))
    chart = form.get("chart_type")
    render = form.get("chart_render")
    font = form.get("font_family")
    weight = form.get("ui_weight")
    theme = form.get("ui_theme")
    try:
        scale = int(form.get("ui_scale", ""))
    except (TypeError, ValueError):
        return None, "La dimensione del carattere non è leggibile."
    if not (Decimal("0") <= profit <= Decimal("5")):
        return None, "La soglia di profitto deve stare tra 0 e 5."
    if investment <= 0:
        return None, "L'investimento massimo deve essere maggiore di zero."
    if not (Decimal("0") <= fee <= Decimal("0.1")):
        return None, "La commissione deve stare tra 0 e 0,1."
    if not (Decimal("0") <= tax <= Decimal("0.5")):
        return None, "L'imposta deve stare tra 0 e 0,5."
    if not (Decimal("0") <= band <= Decimal("0.2")):
        return None, "La banda di stabilità deve stare tra 0 e 0,2."
    if not 10 <= universe <= 500 or universe % 10 != 0:
        return None, "I titoli nel grafico del volume vanno da 10 a 500, a passi di 10."
    if chart not in ("line", "candle"):
        return None, "Il grafico storico può essere lineare o a candele."
    if render not in ("image", "vector"):
        return None, "Il disegno dello storico può essere un'immagine o un vettore."
    if font not in FONT_IDS:
        return None, "Il carattere non è tra quelli disponibili."
    if not 80 <= scale <= 120 or scale % 5 != 0:
        return None, "Dimensione e interlinea vanno da 80 a 120, a passi di 5."
    if weight not in WEIGHT_IDS:
        return None, "Il peso non è tra quelli disponibili."
    if theme not in THEME_IDS:
        return None, "Il tema può essere chiaro, scuro o automatico."
    if not focus:
        return None, "Il titolo del grafico non è valido."
    if not (30 <= history_days <= 1825 and 1 <= return_days <= 120 and 1 <= age <= 720):
        return None, "Giorni di storico, sedute o età del prezzo fuori dai limiti."
    if not 3 <= notice <= 30:
        return None, "I secondi del messaggio devono stare tra 3 e 30."
    values = {
        "profit_threshold": format(profit.normalize(), "f"),
        "max_investment": format(investment.normalize(), "f"),
        "universe_size": str(universe),
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
    """Quante barre e quanto è recente ciascun titolo, per decidere lo scarico."""
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


def load_asset_history(conn, asset, days):
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
        SELECT id, type, asset_name, amount, price, timestamp, fees, taxes
        FROM transactions
        ORDER BY timestamp, id
        """
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def recent_transactions(conn, limit=20):
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT id, type, asset_name, amount, price, timestamp, fees, taxes
        FROM transactions
        ORDER BY timestamp DESC, id DESC
        LIMIT %s
        """,
        (int(limit),),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def insert_transaction(conn, kind, asset, amount, price, fees, taxes, when=None):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO transactions (type, asset_name, amount, price, timestamp, fees, taxes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            kind,
            asset,
            money(amount),
            money(price),
            when or datetime.now().replace(microsecond=0),
            money(fees),
            money(taxes),
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    cur.close()
    log.info(
        "transazione %s id=%s %s qty=%s price=%s fees=%s taxes=%s",
        kind,
        new_id,
        asset,
        amount,
        price,
        fees,
        taxes,
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
    """Stringa vuota: tutti i titoli. s:settore oppure u:settore|sotto-industria."""
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
    """None significa tutti i simboli. Un insieme vuoto non disegna nulla."""
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


def build_blocks(rows, prefs, allowed=None):
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
    return blocks[: prefs["universe_size"]]


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
            outcome = "nessun prezzo"
        elif stale:
            outcome = "prezzo troppo vecchio per vendere"
        elif ready:
            outcome = "pronta alla vendita"
        else:
            outcome = "sotto la soglia"
        rows.append(
            {
                "asset": lot.asset,
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


def sell_ready_lots(conn, prefs):
    """Vende i lotti il cui profitto netto raggiunge la soglia. Ritorna il numero di vendite."""
    lots, unmatched = open_lots(fetch_transactions(conn))
    if unmatched > 0:
        log.warning("vendite senza acquisto corrispondente, quantità residua %s", unmatched)
    prices = latest_prices(conn)
    now = datetime.now()
    max_age = prefs["max_price_age_hours"] * 3600
    sold = 0
    for lot in lots:
        market = prices.get(lot.asset)
        if not market:
            continue
        if (now - market["timestamp"]).total_seconds() > max_age:
            log.info("tengo %s: prezzo del %s troppo vecchio", lot.asset, market["timestamp"])
            continue
        quote = quote_sell(lot, market["price"], prefs["fee_rate"], prefs["tax_rate"])
        if quote is None or quote["ratio"] is None:
            continue
        if quote["ratio"] < prefs["profit_threshold"]:
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
        )
        sold += 1
        log.info(
            "vendita %s qty=%s prezzo=%s profitto_netto=%s soglia=%s",
            lot.asset,
            quote["amount"],
            quote["price"],
            quote["ratio"],
            prefs["profit_threshold"],
        )
    return sold


def read_status():
    if not STATUS_PATH.exists():
        return {"state": "idle", "message": "Nessun aggiornamento eseguito.", "updated": ""}
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "idle", "message": "Stato non leggibile.", "updated": ""}


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


def _decimal(value, fallback):
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return Decimal(fallback)


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
