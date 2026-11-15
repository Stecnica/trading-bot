from datetime import datetime, timedelta
from decimal import Decimal

from bot_decide import score_exits
from bot_logic import open_lots, quote_sell, score_exit
from bot_score import BUY, HOLD, SELL

NOW = datetime(2026, 11, 16, 15, 0)
PREFS = {
    "profit_threshold": Decimal("0.05"),
    "fee_rate": Decimal("0.001"),
    "tax_rate": Decimal("0.26"),
    "max_hold_days": 120,
}


def _lot(asset="HPQ", price="100", days=10):
    tx = {
        "id": 1,
        "type": "buy",
        "asset_name": asset,
        "amount": "10",
        "price": price,
        "fees": "1",
        "taxes": "0",
        "timestamp": NOW - timedelta(days=days),
    }
    return open_lots([tx])[0][0]


def _row(asset, side, price):
    return {"symbol": asset, "side": side, "score": -0.3, "price": Decimal(price), "timestamp": datetime(2026, 11, 12)}


def test_sell_side_at_a_loss_keeps_the_lot():
    lot = _lot()
    quote = quote_sell(lot, "95", PREFS["fee_rate"], PREFS["tax_rate"])
    assert quote["ratio"] < 0
    assert score_exit(lot, quote, True, PREFS, NOW) is None


def test_sell_side_under_the_threshold_keeps_the_lot():
    lot = _lot()
    quote = quote_sell(lot, "103", PREFS["fee_rate"], PREFS["tax_rate"])
    assert 0 < quote["ratio"] < PREFS["profit_threshold"]
    assert score_exit(lot, quote, True, PREFS, NOW) is None


def test_sell_side_at_the_threshold_sells():
    lot = _lot()
    quote = quote_sell(lot, "110", PREFS["fee_rate"], PREFS["tax_rate"])
    assert quote["ratio"] >= PREFS["profit_threshold"]
    assert score_exit(lot, quote, True, PREFS, NOW) == "score"
    assert score_exit(lot, quote, False, PREFS, NOW) is None


def test_lot_past_max_hold_days_sells_at_a_loss():
    lot = _lot(days=121)
    quote = quote_sell(lot, "80", PREFS["fee_rate"], PREFS["tax_rate"])
    assert score_exit(lot, quote, False, PREFS, NOW) == "max_hold"
    assert score_exit(_lot(days=120), quote, False, PREFS, NOW) is None


def test_score_exits_keep_losing_sell_lots_so_they_still_block_the_buy():
    lots = [_lot("HPQ", "30.20"), _lot("IDXX", "671.64")]
    ranked = [_row("HPQ", SELL, "28.88"), _row("IDXX", BUY, "698.02")]
    assert score_exits(None, PREFS, ranked, lots, NOW) == []


def test_score_exits_price_an_unscored_lot_from_the_latest_close():
    class Conn:
        pass

    import bot_decide

    lots = [_lot("OLD", "100", days=200)]
    seen = {}

    def latest(conn):
        seen["called"] = True
        return {"OLD": {"price": Decimal("90"), "timestamp": datetime(2026, 11, 12)}}

    original = bot_decide.latest_prices
    bot_decide.latest_prices = latest
    try:
        exits = score_exits(Conn(), PREFS, [_row("X", HOLD, "1")], lots, NOW)
    finally:
        bot_decide.latest_prices = original
    assert seen["called"]
    assert [(lot.asset, reason) for lot, _q, _s, reason in exits] == [("OLD", "max_hold")]
