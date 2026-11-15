"""One decision from the score. At most one lot is bought per cycle while the cash covers it. An open lot is sold on a sell side only in profit."""

import json
from collections import defaultdict
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

from bot_chart_cache import get_bytes as cache_get, put_bytes as cache_put
from bot_db import (
    bot_buys_on,
    connect,
    fetch_transactions,
    insert_transaction,
    latest_prices,
    load_preferences,
    paper_balance,
    record_decision,
)
from bot_i18n import tr
from bot_logic import money, open_lots, quote_sell, score_exit
from bot_news import listed_symbols
from bot_score import BUY, SELL, Book, warm_rsi

QTY = Decimal("0.00000001")
BOARD_SIZE = 20
BOARD_KEY = ("latest",)
# Candidates kept in one decision row; the rest are only counted.
LOGGED = 30


def score_label(row):
    """Short line for the tile, and the same line plus sensor weights for the title."""
    if not row:
        return "", ""
    score = row["score"]
    sign = "+" if score > 0 else ""
    short = f"{sign}{score:.3f} {tr('score.' + row['side'])}"
    weights = " ".join(
        f"{name} {value:.3f}" for name, value in (row.get("weights") or {}).items()
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


def lot_size(prefs, price):
    """Quantity one lot buys at price: max_investment / price, down to 8 decimals,
    or down to whole shares when lot_sizing is whole. None when that is zero."""
    price = money(price)
    budget = money(prefs["max_investment"])
    if price is None or budget is None or price <= 0 or budget <= 0:
        return None
    step = Decimal("1") if prefs.get("lot_sizing") == "whole" else QTY
    amount = (budget / price).quantize(step, rounding=ROUND_DOWN)
    return amount if amount > 0 else None


def lot_cost(amount, price, fee_rate):
    """Estimated commission of a buy and the cash it takes: notional plus that commission."""
    notional = money(amount) * money(price)
    fees = money(notional * fee_rate) or Decimal("0")
    return fees, money(notional + fees)


def top_buys(board, held, prefs=None, count=5):
    """The next names the bot would buy: BUY side, highest score first, not already owned,
    and, with prefs, only names a lot can buy (whole shares skip names priced above the lot)."""
    rows = []
    for row in board or []:
        if row["symbol"] in held:
            continue
        if prefs is not None and lot_size(prefs, row["price"]) is None:
            continue
        rows.append(row)
        if len(rows) >= count:
            break
    return rows


def plan_buy(ranked, held, cash, prefs, buys_today, sold=()):
    """The one buy of a cycle and why the names ranked before it were passed over. Nothing is written.

    Returns (choice, candidates, reason). reason is bought, daily_cap, no_cash or
    no_candidate. Each candidate carries symbol, score, side, price and the reason it
    was skipped: not_buy, held, sold (sold in this cycle), too_expensive (no whole
    share fits the lot) or no_cash; the chosen one has reason buy. The walk stops at
    the first score at or under zero: no BUY can follow it.
    """
    cap = prefs.get("max_buys_per_day") or 0
    if cap and buys_today >= cap:
        return None, [], "daily_cap"
    candidates = []
    more = 0
    short = False

    def note(row, reason, **extra):
        nonlocal more
        if len(candidates) >= LOGGED:
            more += 1
            return
        entry = {
            "symbol": row["symbol"],
            "score": round(float(row["score"]), 3),
            "side": row["side"],
            "price": str(money(row["price"])),
            "reason": reason,
        }
        entry.update(extra)
        candidates.append(entry)

    for row in ranked:
        if row["score"] <= 0:
            break
        symbol = row["symbol"]
        if row["side"] != BUY:
            note(row, "not_buy")
            continue
        if symbol in held:
            note(row, "held")
            continue
        if symbol in sold:
            note(row, "sold")
            continue
        amount = lot_size(prefs, row["price"])
        if amount is None:
            note(row, "too_expensive")
            continue
        price = money(row["price"])
        fees, total = lot_cost(amount, price, prefs["fee_rate"])
        if total > cash:
            short = True
            note(row, "no_cash", cost=str(total))
            continue
        note(row, "buy", amount=str(amount), cost=str(total))
        choice = {
            "symbol": symbol,
            "amount": amount,
            "price": price,
            "fees": fees,
            "cost": total,
            "score": row["score"],
            "timestamp": row["timestamp"],
        }
        return choice, _counted(candidates, more), "bought"
    return None, _counted(candidates, more), "no_cash" if short else "no_candidate"


def _counted(candidates, more):
    if more:
        candidates.append({"more": more})
    return candidates


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


def apply_once(conn, sold_before=(), now=None):
    """Closes the lots the score step lets go, then buys at most one lot.

    A lot whose side is sell is sold only at or above the profit threshold. A lot
    held longer than max_hold_days is sold at the latest close at any result.
    After the sales, plan_buy picks the first BUY name not held and not sold in this
    cycle (sold_before lists the trailing sales cycle.py made just before) whose lot,
    commission included, the paper cash covers, unless max_buys_per_day bot buys
    are already written today. Both rows carry the session date of the bar they
    priced (midnight) and the rates used; insert_transaction adds the moment of the
    write. Every call records one row in bot_decisions.
    """
    now = now or datetime.now()
    prefs = load_preferences(conn)
    ranked = score_book(conn)
    store_buy_board(ranked)
    lots, _unmatched = open_lots(fetch_transactions(conn))
    sold = []
    exits = score_exits(conn, prefs, ranked, lots, now)
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
    closed = {id(lot) for lot, _quote, _stamp, _reason in exits}
    held = {lot.asset for lot in lots if id(lot) not in closed}
    sold_all = list(sold_before) + sold
    cash = paper_balance(conn, prefs)
    choice, candidates, reason = plan_buy(
        ranked, held, cash, prefs, bot_buys_on(conn, now.date()), set(sold_all)
    )
    if choice:
        insert_transaction(
            conn,
            "buy",
            choice["symbol"],
            choice["amount"],
            choice["price"],
            choice["fees"],
            Decimal("0"),
            choice["timestamp"],
            fee_rate=prefs["fee_rate"],
        )
    record_decision(conn, now, cash, choice, reason, sold_all, candidates)
    return {"bought": choice, "sold": sold, "cash": cash, "reason": reason, "candidates": candidates}


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
    print("cash", result["cash"], "reason", result["reason"])
