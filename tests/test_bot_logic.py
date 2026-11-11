from decimal import Decimal

from bot_logic import Lot, money, open_lots, quote_sell


def test_money_rejects_garbage():
    assert money("abc") is None
    assert money("12.345") == Decimal("12.345")


def test_fifo_closes_the_oldest_lot_first():
    txs = [
        {"id": 1, "type": "buy", "asset_name": "TSLA", "amount": "10", "price": "100", "fees": "0", "taxes": "0", "timestamp": 1},
        {"id": 2, "type": "buy", "asset_name": "TSLA", "amount": "10", "price": "200", "fees": "0", "taxes": "0", "timestamp": 2},
        {"id": 3, "type": "sell", "asset_name": "TSLA", "amount": "10", "price": "150", "fees": "0", "taxes": "0", "timestamp": 3},
    ]
    still_open, unmatched = open_lots(txs)
    assert unmatched == 0
    assert len(still_open) == 1 and still_open[0].price == 200


def test_money_handles_none_and_non_finite():
    assert money(None) is None
    assert money("Infinity") is None
    assert money("NaN") is None


def test_money_quantizes_to_eight_places_half_up():
    assert money("0.123456789") == Decimal("0.12345679")
    assert money(2) == Decimal("2")


def _tx(tx_id, kind, amount, price="100", fees="0", taxes="0", ts=0, asset="TSLA"):
    return {
        "id": tx_id,
        "type": kind,
        "asset_name": asset,
        "amount": amount,
        "price": price,
        "fees": fees,
        "taxes": taxes,
        "timestamp": ts,
    }


def test_open_lots_reports_unmatched_sales():
    txs = [
        _tx(1, "buy", "10", ts=1),
        _tx(2, "sell", "14", price="150", ts=2),
    ]
    still_open, unmatched = open_lots(txs)
    assert still_open == []
    assert unmatched == Decimal("4")


def test_open_lots_sell_without_any_buy_is_all_unmatched():
    still_open, unmatched = open_lots([_tx(1, "sell", "5", price="150", ts=1)])
    assert still_open == []
    assert unmatched == Decimal("5")


def test_open_lots_partial_sell_spans_lots_in_fifo_order():
    txs = [
        _tx(1, "buy", "10", price="100", ts=1),
        _tx(2, "buy", "10", price="200", ts=2),
        _tx(3, "sell", "15", price="150", ts=3),
    ]
    still_open, unmatched = open_lots(txs)
    assert unmatched == 0
    assert len(still_open) == 1
    assert still_open[0].tx_id == 2
    assert still_open[0].remaining == Decimal("5")


def test_quote_sell_net_profit_with_commission_and_tax():
    lot = open_lots([_tx(1, "buy", "10", price="100", fees="10", ts=1)])[0][0]
    quote = quote_sell(lot, "120", "0.01", "0.25")
    assert quote["fees"] == Decimal("12")
    assert quote["taxes"] == Decimal("44.5")
    assert quote["cost"] == Decimal("1010")
    assert quote["proceeds"] == Decimal("1143.5")
    assert quote["amount"] == Decimal("10")
    assert quote["ratio"] == (Decimal("1143.5") - Decimal("1010")) / Decimal("1010")


def test_quote_sell_loss_pays_no_tax():
    lot = open_lots([_tx(1, "buy", "10", price="100", fees="10", ts=1)])[0][0]
    quote = quote_sell(lot, "90", "0.01", "0.25")
    assert quote["fees"] == Decimal("9")
    assert quote["taxes"] == Decimal("0")
    assert quote["proceeds"] == Decimal("891")
    assert quote["ratio"] < 0


def test_quote_sell_partial_lot_scales_buy_fees_by_remaining_share():
    txs = [
        _tx(1, "buy", "10", price="100", fees="10", ts=1),
        _tx(2, "sell", "5", price="110", ts=2),
    ]
    lot = open_lots(txs)[0][0]
    quote = quote_sell(lot, "120", "0.01", "0.25")
    assert quote["cost"] == Decimal("505")
    assert quote["fees"] == Decimal("6")
    assert quote["taxes"] == Decimal("22.25")
    assert quote["proceeds"] == Decimal("571.75")


def test_quote_sell_rejects_empty_lot_and_bad_price():
    lot = open_lots([_tx(1, "buy", "10", ts=1)])[0][0]
    assert quote_sell(lot, "0", "0.01", "0.25") is None
    assert quote_sell(lot, None, "0.01", "0.25") is None
    empty = Lot(9, "TSLA", "10", "100", "0", "0", 1)
    empty.remaining = money("0")
    assert quote_sell(empty, "120", "0.01", "0.25") is None
