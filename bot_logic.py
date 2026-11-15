"""Open lots and the sale decision net of commissions and tax."""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

QTY = Decimal("0.00000001")
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


class Lot:
    def __init__(self, tx_id, asset, original, price, fees, taxes, timestamp, currency=None):
        self.tx_id = tx_id
        self.asset = asset
        self.original = money(original)
        self.remaining = self.original
        self.price = money(price)
        self.fees = money(fees)
        self.taxes = money(taxes)
        self.timestamp = timestamp
        self.currency = currency or "USD"


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
            lot = Lot(
                tx["id"],
                asset,
                amount,
                tx["price"],
                tx["fees"],
                tx["taxes"],
                tx["timestamp"],
                tx.get("currency"),
            )
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
    (only when the gain is positive).
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
    }


def fifo_transaction_views(transactions):
    """FIFO ledger for the Transactions panel: closed slices + open lots.

    Each sell is split across the buy lot(s) it closes (same order as open_lots).
    Fees and taxes on both sides are allocated by quantity share of that slice —
    a buy of 2 with a sell of 1 keeps half the buy fees on the closed slice and
    half on the remaining open lot. Margin is net after those fees and taxes.
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
            lot = Lot(
                tx["id"],
                asset,
                amount,
                tx["price"],
                tx["fees"],
                tx["taxes"],
                tx.get("timestamp"),
                tx.get("currency"),
            )
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
            closed.append(
                {
                    "kind": "closed",
                    "buy_id": lot.tx_id,
                    "sell_id": tx["id"],
                    "asset": asset,
                    "qty": money(take),
                    "bought_at": lot.timestamp,
                    "sold_at": tx.get("timestamp"),
                    "buy_price": lot.price,
                    "sell_price": sell_price,
                    "buy_fees": money(buy_fees),
                    "buy_taxes": money(buy_taxes),
                    "sell_fees": money(sell_fees),
                    "sell_taxes": money(sell_taxes),
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
        cost = lot.remaining * lot.price + buy_fees + buy_taxes
        # Open lot still ties up carrying cost: Balance contribution is negative.
        cash = money(-cost)
        opens.append(
            {
                "kind": "open",
                "buy_id": lot.tx_id,
                "asset": lot.asset,
                "qty": lot.remaining,
                "bought_at": lot.timestamp,
                "buy_price": lot.price,
                "fees": money(buy_fees),
                "taxes": money(buy_taxes),
                "cost": money(cost),
                "cash": cash,
                "currency": lot.currency,
            }
        )
    return {"closed": closed, "open": opens}


def paper_cash_balance(transactions, initial_capital):
    """Paper cash position relative to the starting budget.

    Buys spend notional + commissions + taxes. Sells return notional minus
    commissions and taxes. No broker API — ledger only.
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
