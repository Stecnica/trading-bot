#!/usr/bin/env python3
"""Load a few invented sessions into an empty database.

The numbers are made up so the page can be opened without a Massive download.
They are not market prices and they are not bars from this project's archive.
The script does nothing when market_history already has rows.
"""

import os
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_WEB = os.path.dirname(_HERE)
os.chdir(_WEB)
if _WEB not in sys.path:
    sys.path.insert(0, _WEB)

from bot_config import install_import_path

install_import_path()

from bot_db import connect, ensure_schema, save_classifications, seed_preferences, upsert_bars

DATES = (
    datetime(2020, 1, 6),
    datetime(2020, 1, 7),
    datetime(2020, 1, 8),
    datetime(2020, 1, 9),
    datetime(2020, 1, 10),
    datetime(2020, 1, 13),
)

# Close, then a made-up path. Volume is a round number, largest first.
SERIES = (
    ("DEMOA", (10, 10.1, 10.2, 10.4, 10.3, 12.0), 8000000),
    ("DEMOB", (20, 20.2, 19.8, 19.5, 19.0, 18.0), 5000000),
    ("DEMOC", (15, 15.02, 14.98, 15.01, 15.0, 15.04), 3000000),
    ("DEMOD", (30, 30.5, 31, 30.2, 31.4, 32.0), 2000000),
    ("DEMOE", (8, 8.1, 7.9, 7.6, 7.7, 7.2), 1500000),
    ("DEMOF", (40, 40.1, 40.4, 40.2, 40.8, 41.0), 1200000),
    ("DEMOG", (12, 11.9, 12.1, 11.7, 11.8, 11.4), 900000),
    ("DEMOH", (25, 25.2, 25.1, 25.6, 25.4, 26.1), 400000),
)


def bars():
    rows = []
    for symbol, closes, volume in SERIES:
        previous = closes[0]
        for day, close in zip(DATES, closes):
            low = min(previous, close) * 0.99
            high = max(previous, close) * 1.01
            rows.append(
                {
                    "asset_name": symbol,
                    "timestamp": day,
                    "price": close,
                    "open_price": previous,
                    "high_price": round(high, 4),
                    "low_price": round(low, 4),
                    "volume": volume,
                    "vwap": round((previous + close) / 2, 4),
                    "trade_count": 100,
                    "bar_ms": None,
                    "otc": None,
                }
            )
            previous = close
    return rows


def main():
    conn = connect()
    try:
        ensure_schema(conn)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM market_history")
        (count,) = cur.fetchone()
        cur.close()
        if count:
            print("refused: market_history already has rows")
            return 1
        written = upsert_bars(conn, bars())
        linked = save_classifications(
            conn,
            ((symbol, "Sample", "Fixture") for symbol, _closes, _volume in SERIES),
        )
        seed_preferences(conn)
        cur = conn.cursor()
        cur.execute("UPDATE preferences SET value = 'DEMOA' WHERE name = 'focus_asset'")
        cur.execute("UPDATE preferences SET value = '20' WHERE name = 'names'")
        cur.execute(
            """
            INSERT INTO transactions
                (type, asset_name, amount, price, timestamp, fees, taxes)
            VALUES ('buy', 'DEMOA', 10, 10, '2020-01-06 00:00:00', 0.01, 0)
            """
        )
        conn.commit()
        cur.close()
        print(f"inserted {written} invented bars, {linked} names, 1 buy")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
