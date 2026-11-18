"""Open lots and the sale decision net of commissions and tax."""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

QTY = Decimal("0.00000001")
CURRENCY = "$"
DUST = Decimal("0.00000001")


def one_day_floor(today):
    """Earliest date of the newest bar on a one-day chart.

    Saturday and Sunday have no floor: the chart keeps the last two sessions.
    Monday accepts Friday. Any other weekday accepts yesterday.
    """
    if today.weekday() >= 5:
        return None
    if today.weekday() == 0:
        return today - timedelta(days=3)
    return today - timedelta(days=1)


def money(value):
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None
    if not number.is_finite():
        return None
    return number.quantize(QTY, rounding=ROUND_HALF_UP)


def rate(value):
    """A stored rate as Decimal, or None when the row has none."""
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None
    return number if number.is_finite() else None


class Lot:
    def __init__(self, tx_id, asset, original, price, fees, taxes, timestamp, currency=None, fee_rate=None, estimated=False):
        self.tx_id = tx_id
        self.asset = asset
        self.original = money(original)
        self.remaining = self.original
        self.price = money(price)
        self.fees = money(fees)
        self.taxes = money(taxes)
        self.timestamp = timestamp
        self.currency = currency or CURRENCY
        self.fee_rate = rate(fee_rate)
        self.estimated = estimated


def _lot_from(tx):
    return Lot(
        tx["id"],
        tx["asset_name"],
        money(tx["amount"]),
        tx["price"],
        tx["fees"],
        tx["taxes"],
        tx.get("timestamp"),
        tx.get("currency"),
        tx.get("fee_rate"),
        tx.get("rates_source") == "estimated",
    )


def open_lots(transactions):
    """Rebuilds the lots still open with FIFO. Ignores sales that have no buy."""
    buckets = {}
    order = []
    unmatched = Decimal("0")
    for tx in transactions:
        kind = (tx.get("type") or "").lower()
        asset = tx["asset_name"]
        amount = money(tx["amount"])
        if kind == "buy":
            lot = _lot_from(tx)
            buckets.setdefault(asset, []).append(lot)
            order.append(lot)
        elif kind == "sell":
            left = amount
            for lot in buckets.get(asset, []):
                if left <= 0:
                    break
                if lot.remaining <= 0:
                    continue
                take = lot.remaining if lot.remaining <= left else left
                lot.remaining = money(lot.remaining - take)
                left = money(left - take)
            if left > DUST:
                unmatched += left
    still_open = [lot for lot in order if lot.remaining > DUST]
    return still_open, unmatched


def quote_sell(lot, market_price, fee_rate, tax_rate):
    """Net proceeds against the cost of the lot still open.

    Cost is the entry price plus commissions and taxes already paid, in proportion
    to the quantity left. A sale subtracts the commission and the tax on the gain
    (only when the gain is positive). The rates used and the taxable gain are
    returned so the sale row can store them.
    """
    qty = lot.remaining
    price = money(market_price)
    if qty <= 0 or price is None or price <= 0 or lot.original <= 0:
        return None
    share = qty / lot.original
    buy_notional = qty * lot.price
    buy_fees = lot.fees * share
    buy_taxes = lot.taxes * share
    cost = buy_notional + buy_fees + buy_taxes
    sell_notional = qty * price
    sell_fees = sell_notional * Decimal(str(fee_rate))
    gain = sell_notional - sell_fees - buy_notional - buy_fees
    sell_taxes = gain * Decimal(str(tax_rate)) if gain > 0 else Decimal("0")
    proceeds = sell_notional - sell_fees - sell_taxes
    ratio = None if cost <= 0 else (proceeds - cost) / cost
    return {
        "fees": money(sell_fees),
        "taxes": money(sell_taxes),
        "cost": money(cost),
        "proceeds": money(proceeds),
        "ratio": ratio,
        "price": price,
        "amount": qty,
        "notional": money(sell_notional),
        "fee_rate": Decimal(str(fee_rate)),
        "tax_rate": Decimal(str(tax_rate)),
        "taxable_gain": money(gain) if gain > 0 else Decimal("0"),
    }


def armed_peak(lot, closes, fee_rate, tax_rate, threshold):
    """Highest close since the first close whose net ratio reached the threshold.

    closes are (timestamp, price) pairs in time order, from the buy date on.
    None while no close has reached the threshold: the lot is not armed.
    """
    peak = None
    for _stamp, price in closes:
        price = money(price)
        if price is None or price <= 0:
            continue
        if peak is None:
            quote = quote_sell(lot, price, fee_rate, tax_rate)
            if quote is not None and quote["ratio"] is not None and quote["ratio"] >= threshold:
                peak = price
        elif price > peak:
            peak = price
    return peak


def peak_drop(peak, price):
    if peak is None or peak <= 0:
        return None
    return (peak - money(price)) / peak


def sells_at_threshold(prefs):
    """True when a lot is sold the moment its net profit reaches the threshold."""
    return prefs.get("sell_at_threshold") == "on"


def threshold_exit(quote, peak, score, prefs):
    """Why this quote sells the lot, or None to keep it.

    With the flag on, the only sale is a net ratio already at the threshold.
    The price age, the peak, the score and the trail are not consulted, and a
    ratio under the threshold sells nothing.
    """
    if sells_at_threshold(prefs):
        if quote is None or quote.get("ratio") is None:
            return None
        if quote["ratio"] >= prefs["profit_threshold"]:
            return "threshold"
        return None
    return trail_exit(quote, peak, score, prefs)


def trail_exit(quote, peak, score, prefs):
    """Why an armed lot is sold now, or None to keep it.

    floor: the net ratio is back at or under the threshold, still above zero.
    trail: the close is trail or more under the peak since arming.
    score: the score is under sell_delay_score, or there is none.
    Under zero the lot is kept: these exits never sell at a loss.
    """
    if peak is None or quote is None or quote["ratio"] is None:
        return None
    if quote["ratio"] <= 0:
        return None
    if quote["ratio"] <= prefs["profit_threshold"]:
        return "floor"
    if peak_drop(peak, quote["price"]) >= prefs["trail"]:
        return "trail"
    if score is None or score < prefs["sell_delay_score"]:
        return "score"
    return None


def held_too_long(lot, now, max_hold_days):
    """True when the lot was bought more than max_hold_days before now."""
    if lot.timestamp is None:
        return False
    return now - lot.timestamp > timedelta(days=max_hold_days)


def score_exit(lot, quote, score_says_sell, prefs, now):
    """Why the score step closes a lot, or None to keep it.

    A sell signal closes the lot only in profit, at or above the threshold.
    Past max_hold_days the lot closes at any result.
    With the threshold flag on, this step sells nothing: the other step already
    sold every lot whose net profit is at the threshold.
    """
    if sells_at_threshold(prefs):
        return None
    if held_too_long(lot, now, prefs["max_hold_days"]):
        return "max_hold"
    if not score_says_sell or quote is None or quote["ratio"] is None:
        return None
    if quote["ratio"] >= prefs["profit_threshold"]:
        return "score"
    return None


def fifo_transaction_views(transactions, prices=None, fee_rate=None, tax_rate=None):
    """FIFO ledger for the Transactions panel: closed slices, open lots, totals.

    Each sell is split across the buy lot(s) it closes (same order as open_lots).
    Fees and taxes on both sides are allocated by quantity share of that slice —
    a buy of 2 with a sell of 1 keeps half the buy fees on the closed slice and
    half on the remaining open lot. Margin is net after those fees and taxes.
    Each slice carries the rates stored on its buy and sell rows and the gain the
    tax was charged on (same formula as quote_sell).

    With prices ({asset: {"price", "timestamp"}}) and the current fee and tax
    rates, an open lot also carries what quote_sell would record if it were sold
    now: the sale commission, the buy plus that sale commission, the tax on the
    unrealized gain, and the net result. Totals fees and taxes are what the stored
    rows charged; est_fees and est_taxes add up those estimates. They are not cash
    and never enter paper_cash_balance. columns sums the figure each column shows
    on these rows.
    """
    buckets = {}
    order = []
    closed = []
    for tx in transactions:
        kind = (tx.get("type") or "").lower()
        asset = tx["asset_name"]
        amount = money(tx["amount"])
        if amount is None or amount <= 0:
            continue
        if kind == "buy":
            lot = _lot_from(tx)
            if lot.price is None or lot.original <= 0:
                continue
            if lot.fees is None:
                lot.fees = Decimal("0")
            if lot.taxes is None:
                lot.taxes = Decimal("0")
            buckets.setdefault(asset, []).append(lot)
            order.append(lot)
            continue
        if kind != "sell":
            continue
        sell_price = money(tx["price"])
        sell_fees_row = money(tx.get("fees")) or Decimal("0")
        sell_taxes_row = money(tx.get("taxes")) or Decimal("0")
        if sell_price is None or sell_price <= 0:
            continue
        left = amount
        for lot in buckets.get(asset, []):
            if left <= 0:
                break
            if lot.remaining <= 0:
                continue
            take = lot.remaining if lot.remaining <= left else left
            buy_share = take / lot.original
            sell_share = take / amount
            buy_fees = lot.fees * buy_share
            buy_taxes = lot.taxes * buy_share
            sell_fees = sell_fees_row * sell_share
            sell_taxes = sell_taxes_row * sell_share
            buy_notional = take * lot.price
            sell_notional = take * sell_price
            cost = buy_notional + buy_fees + buy_taxes
            proceeds = sell_notional - sell_fees - sell_taxes
            net = proceeds - cost
            ratio = None if cost <= 0 else net / cost
            gain = sell_notional - sell_fees - buy_notional - buy_fees
            closed.append(
                {
                    "kind": "closed",
                    "buy_id": lot.tx_id,
                    "sell_id": tx["id"],
                    "asset": asset,
                    "qty": money(take),
                    "bought_at": lot.timestamp,
                    "sold_at": tx.get("timestamp"),
                    "recorded_at": tx.get("recorded_at"),
                    "buy_price": lot.price,
                    "sell_price": sell_price,
                    "buy_fees": money(buy_fees),
                    "buy_taxes": money(buy_taxes),
                    "sell_fees": money(sell_fees),
                    "sell_taxes": money(sell_taxes),
                    "buy_fee_rate": lot.fee_rate,
                    "sell_fee_rate": rate(tx.get("fee_rate")),
                    "tax_rate": rate(tx.get("tax_rate")),
                    "taxable_gain": money(gain) if gain > 0 else Decimal("0"),
                    "estimated": lot.estimated or tx.get("rates_source") == "estimated",
                    "fees": money(buy_fees + sell_fees),
                    "taxes": money(buy_taxes + sell_taxes),
                    "cost": money(cost),
                    "proceeds": money(proceeds),
                    "net": money(net),
                    # Closed slice cash effect on Balance equals net P&L.
                    "cash": money(net),
                    "ratio": ratio,
                    "currency": tx.get("currency") or lot.currency,
                }
            )
            lot.remaining = money(lot.remaining - take)
            left = money(left - take)
    opens = []
    for lot in order:
        if lot.remaining <= DUST:
            continue
        share = lot.remaining / lot.original
        buy_fees = lot.fees * share
        buy_taxes = lot.taxes * share
        notional = lot.remaining * lot.price
        cost = notional + buy_fees + buy_taxes
        row = {
            "kind": "open",
            "buy_id": lot.tx_id,
            "asset": lot.asset,
            "qty": lot.remaining,
            "bought_at": lot.timestamp,
            "buy_price": lot.price,
            "notional": money(notional),
            "fees": money(buy_fees),
            "taxes": money(buy_taxes),
            "buy_fee_rate": lot.fee_rate,
            "estimated": lot.estimated,
            "cost": money(cost),
            # Cash tied up by the lot; Balance subtracts it until the lot is sold.
            "cash": money(-cost),
            "currency": lot.currency,
            "market_price": None,
            "market_time": None,
            "est": None,
        }
        market = (prices or {}).get(lot.asset)
        if market and fee_rate is not None and tax_rate is not None:
            quote = quote_sell(lot, market["price"], fee_rate, tax_rate)
            if quote is not None:
                row["market_price"] = quote["price"]
                row["market_time"] = market.get("timestamp")
                row["est"] = {
                    "sell_fees": quote["fees"],
                    "fees": money(buy_fees + quote["fees"]),
                    "fee_rate": quote["fee_rate"],
                    "taxes": quote["taxes"],
                    "tax_rate": quote["tax_rate"],
                    "taxable_gain": quote["taxable_gain"],
                    "net": money(quote["proceeds"] - quote["cost"]),
                    "ratio": quote["ratio"],
                }
        opens.append(row)
    zero = Decimal("0")
    totals = {
        "fees": money(sum((r["fees"] for r in closed), zero) + sum((r["fees"] for r in opens), zero)),
        "taxes": money(sum((r["taxes"] for r in closed), zero) + sum((r["taxes"] for r in opens), zero)),
        "est_fees": money(sum((r["est"]["sell_fees"] for r in opens if r["est"]), zero)),
        "est_taxes": money(sum((r["est"]["taxes"] for r in opens if r["est"]), zero)),
        "est_count": sum(1 for r in opens if r["est"]),
        "columns": transaction_column_sums(closed, opens),
    }
    return {"closed": closed, "open": opens, "totals": totals}


def _sum_money(values):
    total = Decimal("0")
    for value in values:
        if value is not None:
            total += value
    return money(total)


def transaction_column_sums(closed, opens):
    """Sum of the number each column shows, for the rows passed in.

    Closed: quantity, buy price, sell price, commissions, taxes, net result.
    Open: quantity, buy price, cost, and the commissions, taxes and net the row
    prints (the estimate when the lot has one, otherwise the paid buy commission
    and no tax or result). A sum of prices is the sum of those unit prices.
    """
    closed = list(closed or [])
    opens = list(opens or [])
    priced = [row for row in opens if row.get("est")]
    return {
        "closed": {
            "qty": _sum_money(row["qty"] for row in closed),
            "buy": _sum_money(row["buy_price"] for row in closed),
            "sell": _sum_money(row["sell_price"] for row in closed),
            "fees": _sum_money(row["fees"] for row in closed),
            "taxes": _sum_money(row["taxes"] for row in closed),
            "cash": _sum_money(row["cash"] for row in closed),
        },
        "open": {
            "qty": _sum_money(row["qty"] for row in opens),
            "price": _sum_money(row["buy_price"] for row in opens),
            "cost": _sum_money(row["cost"] for row in opens),
            "fees": _sum_money(row["est"]["fees"] if row.get("est") else row["fees"] for row in opens),
            "taxes": _sum_money(row["est"]["taxes"] for row in priced) if priced else None,
            "cash": _sum_money(row["est"]["net"] for row in priced) if priced else None,
            "rows": len(opens),
            "est_rows": len(priced),
        },
    }


def taxable_gains_by_sale(transactions):
    """Gain each sell row was taxed on, summed over the FIFO slices it closed."""
    gains = {}
    for row in fifo_transaction_views(transactions)["closed"]:
        gains[row["sell_id"]] = gains.get(row["sell_id"], Decimal("0")) + row["taxable_gain"]
    return gains


def paper_cash_balance(transactions, initial_capital):
    """Paper cash position relative to the starting budget.

    Buys spend notional + commissions + taxes. Sells return notional minus
    commissions and taxes. No broker API — ledger only. Open lots count at
    their cost: the estimates of fifo_transaction_views never enter here.
    """
    cash = money(initial_capital)
    if cash is None:
        cash = Decimal("0")
    for tx in transactions:
        kind = (tx.get("type") or "").lower()
        amount = money(tx.get("amount"))
        price = money(tx.get("price"))
        fees = money(tx.get("fees"))
        taxes = money(tx.get("taxes"))
        if amount is None or price is None or amount <= 0 or price <= 0:
            continue
        if fees is None:
            fees = Decimal("0")
        if taxes is None:
            taxes = Decimal("0")
        notional = amount * price
        if kind == "buy":
            cash = money(cash - notional - fees - taxes)
        elif kind == "sell":
            cash = money(cash + notional - fees - taxes)
    return cash
