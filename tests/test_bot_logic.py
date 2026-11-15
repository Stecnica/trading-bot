from datetime import date
from decimal import Decimal

from bot_logic import Lot, money, one_day_floor, open_lots, quote_sell, paper_cash_balance, fifo_transaction_views, taxable_gains_by_sale


def test_money_rejects_garbage():
    assert money("abc") is None
    assert money("12.345") == Decimal("12.345")


def test_one_day_keeps_friday_across_the_weekend():
    friday = date(2026, 11, 13)
    assert one_day_floor(date(2026, 11, 14)) is None
    assert one_day_floor(date(2026, 11, 15)) is None
    assert one_day_floor(date(2026, 11, 16)) == friday
    assert one_day_floor(date(2026, 11, 17)) == date(2026, 11, 16)
    assert one_day_floor(friday) == date(2026, 11, 12)


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


def test_paper_cash_balance_tracks_buys_and_sells():
    txs = [
        {"type": "buy", "amount": "1", "price": "100", "fees": "1", "taxes": "0"},
        {"type": "sell", "amount": "1", "price": "120", "fees": "1", "taxes": "5"},
    ]
    assert paper_cash_balance(txs, "1000") == Decimal("1013")


def test_fifo_views_expose_net_money_on_closed_slices():
    txs = [
        {"id": 1, "type": "buy", "asset_name": "TSLA", "amount": "1", "price": "100", "fees": "0", "taxes": "0", "timestamp": 1},
        {"id": 2, "type": "sell", "asset_name": "TSLA", "amount": "1", "price": "110", "fees": "0", "taxes": "0", "timestamp": 2},
    ]
    views = fifo_transaction_views(txs)
    assert len(views["closed"]) == 1
    assert views["closed"][0]["net"] == Decimal("10")
    assert views["closed"][0]["cash"] == Decimal("10")
    assert views["open"] == []


def test_fifo_views_open_cash_is_negative_carrying_cost():
    txs = [
        {"id": 1, "type": "buy", "asset_name": "AMD", "amount": "2", "price": "50", "fees": "2", "taxes": "0", "timestamp": 1},
        {"id": 2, "type": "sell", "asset_name": "AMD", "amount": "1", "price": "60", "fees": "1", "taxes": "0", "timestamp": 2},
    ]
    views = fifo_transaction_views(txs)
    assert len(views["closed"]) == 1
    assert views["closed"][0]["cash"] == views["closed"][0]["net"]
    assert len(views["open"]) == 1
    assert views["open"][0]["cash"] == -views["open"][0]["cost"]
    assert views["open"][0]["cash"] == Decimal("-51")
    assert paper_cash_balance(txs, "1000") == Decimal("1000") + views["closed"][0]["cash"] + views["open"][0]["cash"]


def test_quote_sell_returns_rates_and_taxable_gain():
    lot = Lot(1, "TSLA", "1", "354.6", "0.3546", "0", 1)
    quote = quote_sell(lot, "374.8", "0.001", "0.26")
    assert quote["fee_rate"] == Decimal("0.001")
    assert quote["tax_rate"] == Decimal("0.26")
    assert quote["taxable_gain"] == Decimal("19.4706")
    assert quote["taxes"] == money(quote["taxable_gain"] * Decimal("0.26"))


def test_open_lot_estimate_matches_the_sale_quote_sell_would_record():
    buy = {"id": 1, "type": "buy", "asset_name": "IDXX", "amount": "1.48889285", "price": "671.64",
           "fees": "0.99999999", "taxes": "0", "timestamp": 1, "fee_rate": "0.001"}
    views = fifo_transaction_views([buy], {"IDXX": {"price": "698.02", "timestamp": 2}}, "0.001", "0.26")
    row = views["open"][0]
    quote = quote_sell(Lot(1, "IDXX", "1.48889285", "671.64", "0.99999999", "0", 1), "698.02", "0.001", "0.26")
    assert row["est"]["taxes"] == quote["taxes"]
    assert row["est"]["sell_fees"] == quote["fees"]
    assert row["est"]["net"] == money(quote["proceeds"] - quote["cost"])
    assert row["notional"] == money(Decimal("1.48889285") * Decimal("671.64"))
    assert row["buy_fee_rate"] == Decimal("0.001")
    assert views["totals"]["est_taxes"] == quote["taxes"]
    assert row["est"]["fees"] == money(row["fees"] + quote["fees"])
    assert views["totals"]["est_fees"] == quote["fees"]
    assert views["totals"]["fees"] == row["fees"]
    assert paper_cash_balance([buy], "10000") == Decimal("10000") + row["cash"]


def test_open_lot_without_price_has_no_estimate():
    buy = {"id": 1, "type": "buy", "asset_name": "SPCX", "amount": "2", "price": "162.57", "fees": "0.32514", "taxes": "0", "timestamp": 1}
    views = fifo_transaction_views([buy], {}, "0.001", "0.26")
    assert views["open"][0]["est"] is None
    assert views["totals"]["est_count"] == 0


def test_partial_sale_splits_taxable_gain_and_totals_cover_both_sides():
    txs = [
        {"id": 1, "type": "buy", "asset_name": "AMD", "amount": "2", "price": "50", "fees": "0.1", "taxes": "0", "timestamp": 1},
        {"id": 2, "type": "buy", "asset_name": "AMD", "amount": "2", "price": "55", "fees": "0.11", "taxes": "0", "timestamp": 2},
        {"id": 3, "type": "sell", "asset_name": "AMD", "amount": "3", "price": "60", "fees": "0.18", "taxes": "3", "timestamp": 3,
         "fee_rate": "0.001", "tax_rate": "0.26", "rates_source": "estimated"},
    ]
    views = fifo_transaction_views(txs)
    first, second = views["closed"]
    assert first["taxable_gain"] == Decimal("19.78")
    assert second["taxable_gain"] == Decimal("4.885")
    assert first["tax_rate"] == Decimal("0.26") and first["estimated"]
    assert taxable_gains_by_sale(txs) == {3: Decimal("24.665")}
    assert views["totals"]["fees"] == Decimal("0.39")
    assert views["totals"]["taxes"] == Decimal("3")


def test_lot_without_currency_uses_the_stored_symbol():
    lot = open_lots([_tx(1, "buy", "1")])[0][0]
    assert lot.currency == "$"
