"""One decision from the score. The top buy is written. An open lot is sold on a sell side only in profit."""

import json
from collections import defaultdict
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

from bot_chart_cache import get_bytes as cache_get, put_bytes as cache_put
from bot_db import connect, fetch_transactions, insert_transaction, latest_prices, load_preferences
from bot_i18n import tr
from bot_logic import money, open_lots, quote_sell, score_exit
from bot_news import listed_symbols
from bot_score import BUY, SELL, Book, warm_rsi

QTY = Decimal("0.00000001")
BOARD_SIZE = 20
BOARD_KEY = ("latest",)


def score_label(row):
    """Short line for the tile, and the same line plus sensor weights for the title."""
    if not row:
        return "", ""
    score = row["score"]
    sign = "+" if score > 0 else ""
    short = f"{sign}{score:.2f} {tr('score.' + row['side'])}"
    weights = " ".join(
        f"{name} {value:.2f}" for name, value in (row.get("weights") or {}).items()
    )
    detail = f"{short} · {weights}" if weights else short
    return short, detail


def scores_for(conn, symbols):
    """Score of the last sixteen closes for the names on the page."""
    wanted = []
    seen = set()
    for symbol in symbols:
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        wanted.append(symbol)
    if not wanted:
        return {}
    marks = ",".join(["%s"] * len(wanted))
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT asset_name, price
        FROM (
            SELECT asset_name, price,
                   ROW_NUMBER() OVER (PARTITION BY asset_name ORDER BY timestamp DESC) AS n
            FROM market_history
            WHERE asset_name IN ({marks})
        ) ranked
        WHERE n <= 40
        ORDER BY asset_name, n DESC
        """,
        tuple(wanted),
    )
    series = defaultdict(list)
    for asset, price in cur:
        series[asset].append(price)
    cur.close()
    try:
        from bot_slow import warm
        warm(series.values())
    except ImportError:
        pass
    warm_rsi(series.values())
    book = Book()
    found = {}
    for asset, prices in series.items():
        row = None
        for price in prices:
            row = book.update(asset, price)
        if row is not None:
            found[asset] = row
    return found


def score_book(conn):
    """Last sixteen closes for each listed name. The reading is the close."""
    universe = listed_symbols()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT asset_name, timestamp, price
        FROM (
            SELECT asset_name, timestamp, price,
                   ROW_NUMBER() OVER (PARTITION BY asset_name ORDER BY timestamp DESC) AS n
            FROM market_history
        ) t
        WHERE n <= 40
        ORDER BY asset_name, n DESC
        """
    )
    series = defaultdict(list)
    for asset, stamp, price in cur:
        if universe and asset not in universe:
            continue
        series[asset].append((stamp, price))
    cur.close()
    book = Book()
    rows = []
    for asset, bars in series.items():
        row = None
        for _stamp, price in bars:
            row = book.update(asset, price)
        if row is None:
            continue
        row["timestamp"] = bars[-1][0]
        row["price"] = bars[-1][1]
        rows.append(row)
    rows.sort(key=lambda item: item["score"], reverse=True)
    return rows


def buy_board(ranked, size=BOARD_SIZE):
    """The first BUY rows of a ranking, as plain values for the cache."""
    board = []
    for row in ranked:
        if row["side"] != BUY:
            continue
        board.append(
            {
                "symbol": row["symbol"],
                "score": float(row["score"]),
                "price": str(row["price"]),
                "timestamp": row["timestamp"].isoformat() if row.get("timestamp") else None,
            }
        )
        if len(board) >= size:
            break
    return board


def store_buy_board(ranked):
    cache_put("buy_board", BOARD_KEY, json.dumps(buy_board(ranked), separators=(",", ":")).encode("utf-8"))


def load_buy_board():
    """The board the last decision stored, or None. Scoring 500 names is too slow for a request."""
    raw = cache_get("buy_board", BOARD_KEY)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


def top_buys(board, held, count=5):
    """The next names the bot would buy: BUY side, highest score first, not already owned."""
    return [row for row in board or [] if row["symbol"] not in held][:count]


def _amount_for(budget, price):
    price = money(price)
    budget = money(budget)
    if price is None or budget is None or price <= 0 or budget <= 0:
        return None, None
    amount = (budget / price).quantize(QTY, rounding=ROUND_DOWN)
    if amount <= 0:
        return None, None
    return amount, price


def score_exits(conn, prefs, ranked, lots, now=None):
    """The lots the score step closes, with the bar that prices each sale. Nothing is written."""
    now = now or datetime.now()
    by_symbol = {row["symbol"]: row for row in ranked}
    latest = None
    exits = []
    for lot in lots:
        row = by_symbol.get(lot.asset)
        if row is not None:
            price, stamp = row["price"], row["timestamp"]
        else:
            if latest is None:
                latest = latest_prices(conn)
            market = latest.get(lot.asset)
            if not market:
                continue
            price, stamp = market["price"], market["timestamp"]
        quote = quote_sell(lot, price, prefs["fee_rate"], prefs["tax_rate"])
        if quote is None:
            continue
        reason = score_exit(lot, quote, row is not None and row["side"] == SELL, prefs, now)
        if reason:
            exits.append((lot, quote, stamp, reason))
    return exits


def apply_once(conn):
    """Writes at most one buy, the highest score, and closes the lots the score step lets go.

    A lot whose side is sell is sold only at or above the profit threshold. A lot
    held longer than max_hold_days is sold at the latest close at any result.
    While any lot stays open, nothing is bought. Both rows carry the session
    date of the bar they priced (midnight) and the rates used;
    insert_transaction adds the moment of the write.
    """
    prefs = load_preferences(conn)
    ranked = score_book(conn)
    store_buy_board(ranked)
    lots, _unmatched = open_lots(fetch_transactions(conn))
    held = {lot.asset for lot in lots}
    sold = []
    exits = score_exits(conn, prefs, ranked, lots)
    for lot, quote, stamp, reason in exits:
        insert_transaction(
            conn,
            "sell",
            lot.asset,
            quote["amount"],
            quote["price"],
            quote["fees"],
            quote["taxes"],
            stamp,
            lot.currency,
            quote["fee_rate"],
            quote["tax_rate"],
            quote["taxable_gain"],
        )
        sold.append(lot.asset)
    holding = len(exits) < len(lots)
    bought = None
    if holding:
        return {"bought": bought, "sold": sold}
    for row in ranked:
        if row["side"] != BUY or row["symbol"] in held:
            continue
        amount, price = _amount_for(prefs["max_investment"], row["price"])
        if amount is None:
            continue
        notional = amount * price
        fees = money(notional * prefs["fee_rate"]) or Decimal("0")
        insert_transaction(
            conn,
            "buy",
            row["symbol"],
            amount,
            price,
            fees,
            Decimal("0"),
            row["timestamp"],
            fee_rate=prefs["fee_rate"],
        )
        bought = {
            "symbol": row["symbol"],
            "amount": amount,
            "price": price,
            "fees": fees,
            "score": row["score"],
            "timestamp": row["timestamp"],
        }
        break
    return {"bought": bought, "sold": sold}


def main():
    conn = connect()
    try:
        return apply_once(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    result = main()
    bought = result["bought"]
    if bought:
        print(
            "buy",
            bought["symbol"],
            bought["amount"],
            bought["price"],
            bought["fees"],
            round(bought["score"], 3),
            bought["timestamp"],
        )
    else:
        print("buy none")
    print("sold", ",".join(result["sold"]) or "none")
