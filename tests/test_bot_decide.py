from datetime import datetime, timedelta
from decimal import Decimal

from bot_decide import score_exits
from bot_logic import armed_peak, open_lots, quote_sell, score_exit, threshold_exit, trail_exit
from bot_score import BUY, HOLD, SELL

NOW = datetime(2026, 11, 16, 15, 0)
PREFS = {
    "profit_threshold": Decimal("0.05"),
    "fee_rate": Decimal("0.001"),
    "tax_rate": Decimal("0.26"),
    "max_hold_days": 120,
    "trail": Decimal("0.03"),
    "sell_delay_score": Decimal("0.2"),
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


def _closes(*prices):
    return [(NOW - timedelta(days=len(prices) - i), Decimal(p)) for i, p in enumerate(prices)]


def _trail(prices, score):
    lot = _lot(price="100")
    closes = _closes(*prices)
    peak = armed_peak(lot, closes, PREFS["fee_rate"], PREFS["tax_rate"], PREFS["profit_threshold"])
    quote = quote_sell(lot, closes[-1][1], PREFS["fee_rate"], PREFS["tax_rate"])
    return peak, trail_exit(quote, peak, score, PREFS)


def test_lot_under_the_threshold_is_not_armed():
    assert _trail(["100", "103", "104"], 0.5) == (None, None)


def test_armed_lot_with_a_good_score_and_a_small_drop_is_kept():
    peak, reason = _trail(["100", "110", "112", "111"], 0.5)
    assert peak == Decimal("112")
    assert reason is None


def test_armed_lot_sells_when_the_score_falls_under_the_delay():
    assert _trail(["100", "110", "112", "111"], 0.1)[1] == "score"
    assert _trail(["100", "110", "112", "111"], None)[1] == "score"


def test_armed_lot_sells_on_a_drop_from_the_peak():
    peak, reason = _trail(["100", "110", "120", "116"], 0.9)
    assert peak == Decimal("120")
    assert reason == "trail"


def test_armed_lot_sells_at_the_floor_when_the_ratio_falls_back():
    peak, reason = _trail(["100", "110", "104"], 0.9)
    assert peak == Decimal("110")
    assert reason == "floor"


def test_zero_trail_sells_at_the_first_close_over_the_threshold():
    lot = _lot(price="100")
    closes = _closes("100", "110")
    prefs = dict(PREFS, trail=Decimal("0"))
    peak = armed_peak(lot, closes, prefs["fee_rate"], prefs["tax_rate"], prefs["profit_threshold"])
    quote = quote_sell(lot, "110", prefs["fee_rate"], prefs["tax_rate"])
    assert trail_exit(quote, peak, 0.9, prefs) == "trail"


def test_at_threshold_sells_at_once_and_keeps_what_is_under_it():
    prefs = dict(PREFS, sell_at_threshold="on")
    lot = _lot()
    above = quote_sell(lot, "110", prefs["fee_rate"], prefs["tax_rate"])
    under = quote_sell(lot, "103", prefs["fee_rate"], prefs["tax_rate"])
    loss = quote_sell(lot, "80", prefs["fee_rate"], prefs["tax_rate"])
    assert threshold_exit(above, None, None, prefs) == "threshold"
    assert threshold_exit(under, None, 0.1, prefs) is None
    assert threshold_exit(loss, None, None, prefs) is None
    assert score_exit(lot, above, True, prefs, NOW) is None
    assert score_exit(_lot(days=200), loss, False, prefs, NOW) is None


def test_armed_lot_under_zero_is_kept():
    peak, reason = _trail(["100", "110", "95"], 0.1)
    assert peak == Decimal("110")
    assert reason is None


def test_buy_board_keeps_buy_rows_in_ranking_order():
    from bot_decide import buy_board

    ranked = [
        {"symbol": "A", "side": BUY, "score": 0.6, "price": Decimal("10"), "timestamp": datetime(2026, 11, 12)},
        {"symbol": "B", "side": HOLD, "score": 0.5, "price": Decimal("11"), "timestamp": datetime(2026, 11, 12)},
        {"symbol": "C", "side": BUY, "score": 0.4, "price": Decimal("12"), "timestamp": None},
    ]
    board = buy_board(ranked, size=5)
    assert [row["symbol"] for row in board] == ["A", "C"]
    assert board[0] == {"symbol": "A", "score": 0.6, "price": "10", "timestamp": "2026-11-12T00:00:00"}


def test_top_buys_skip_owned_names_and_stop_at_the_count():
    from bot_decide import top_buys

    board = [{"symbol": s} for s in ("AMD", "AVGO", "CLX", "ANET", "CEG", "SWKS", "X")]
    assert [row["symbol"] for row in top_buys(board, {"AMD"}, count=5)] == ["AVGO", "CLX", "ANET", "CEG", "SWKS"]
    assert top_buys(None, set()) == []
