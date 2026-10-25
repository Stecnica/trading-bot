"""Lotti aperti e decisione di vendita al netto di commissioni e tasse."""

from decimal import Decimal, ROUND_HALF_UP

QTY = Decimal("0.00000001")
DUST = Decimal("0.00000001")


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
    def __init__(self, tx_id, asset, original, price, fees, taxes, timestamp):
        self.tx_id = tx_id
        self.asset = asset
        self.original = money(original)
        self.remaining = self.original
        self.price = money(price)
        self.fees = money(fees)
        self.taxes = money(taxes)
        self.timestamp = timestamp


def open_lots(transactions):
    """Ricostruisce i lotti ancora aperti con FIFO. Ignora le vendite senza acquisto."""
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
    """Ricavo netto rispetto al costo del lotto ancora aperto.

    Il costo è prezzo di carico più commissioni e tasse già pagate, in proporzione
    alla quantità rimasta. In vendita si tolgono la commissione e l'imposta
    sul guadagno (solo se il guadagno è positivo).
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
