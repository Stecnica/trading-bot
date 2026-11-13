from datetime import date
from decimal import Decimal

from bot_logic import money, one_day_floor, open_lots


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
