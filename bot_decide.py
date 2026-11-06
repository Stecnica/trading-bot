"""One decision from the score. The top buy is written. An open lot is sold when its side is sell."""

from collections import defaultdict
from decimal import ROUND_DOWN, Decimal

from bot_db import connect, fetch_transactions, insert_transaction, load_preferences
from bot_i18n import tr
from bot_logic import money, open_lots, quote_sell
from bot_news import listed_symbols
from bot_score import BUY, SELL, Book, warm_rsi

QTY = Decimal("0.00000001")


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


def _amount_for(budget, price):
    price = money(price)
    budget = money(budget)
    if price is None or budget is None or price <= 0 or budget <= 0:
        return None, None
    amount = (budget / price).quantize(QTY, rounding=ROUND_DOWN)
    if amount <= 0:
        return None, None
    return amount, price


def apply_once(conn):
    """Writes at most one buy, the highest score, and sells open lots whose side is sell."""
    prefs = load_preferences(conn)
    ranked = score_book(conn)
    by_symbol = {row["symbol"]: row for row in ranked}
    lots, _unmatched = open_lots(fetch_transactions(conn))
    held = {lot.asset for lot in lots}
    sold = []
    holding = False
    for lot in lots:
        row = by_symbol.get(lot.asset)
        if row is None or row["side"] != SELL:
            holding = True
            continue
        quote = quote_sell(lot, row["price"], prefs["fee_rate"], prefs["tax_rate"])
        if quote is None:
            continue
        insert_transaction(
            conn,
            "sell",
            lot.asset,
            quote["amount"],
            quote["price"],
            quote["fees"],
            quote["taxes"],
            row["timestamp"],
        )
        sold.append(lot.asset)
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
