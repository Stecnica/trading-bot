from datetime import datetime
from decimal import Decimal

from bot_db import interpret, preference_patch
from bot_decide import LOGGED, lot_cost, lot_size, plan_buy, top_buys
from bot_score import BUY, HOLD, SELL

SESSION = datetime(2026, 11, 13)


def _prefs(sizing="fractional", cap=0, lot="1000"):
    return {
        "max_investment": Decimal(lot),
        "fee_rate": Decimal("0.001"),
        "lot_sizing": sizing,
        "max_buys_per_day": cap,
    }


def _row(symbol, price, score=0.5, side=BUY):
    return {"symbol": symbol, "price": Decimal(price), "score": score, "side": side, "timestamp": SESSION}


def test_defaults_are_fractional_lots_and_no_daily_cap():
    prefs = interpret({})
    assert prefs["lot_sizing"] == "fractional"
    assert prefs["max_buys_per_day"] == 0
    assert interpret({"lot_sizing": "half", "max_buys_per_day": "-3"})["lot_sizing"] == "fractional"


def test_new_prefs_are_clamped_or_refused_like_the_others():
    clamped = []
    values, error = preference_patch({"max_buys_per_day": "500", "lot_sizing": "whole"}, clamped)
    assert error is None
    assert values == {"max_buys_per_day": "100", "lot_sizing": "whole"}
    assert clamped == ["max_buys_per_day"]
    assert preference_patch({"max_buys_per_day": "-1"}, [])[0] == {"max_buys_per_day": "0"}
    assert preference_patch({"lot_sizing": "half"}, [])[1]


def test_fractional_lot_spends_the_whole_investment_to_eight_decimals():
    amount = lot_size(_prefs(), "109.46")
    assert amount == Decimal("9.13575735")
    fees, cost = lot_cost(amount, Decimal("109.46"), Decimal("0.001"))
    assert fees == Decimal("1.00000000")
    assert Decimal("1000.99") < cost <= Decimal("1001")


def test_whole_lot_rounds_down_and_skips_names_above_the_lot():
    assert lot_size(_prefs("whole"), "364.36") == Decimal("2")
    assert lot_size(_prefs("whole"), "1447.40") is None
    assert lot_size(_prefs(), "1447.40") == Decimal("0.69089401")


def test_first_buy_not_held_is_chosen_even_with_lots_open():
    ranked = [_row("AVGO", "364.36", 0.54), _row("CLX", "108.20", 0.51)]
    choice, candidates, reason = plan_buy(ranked, {"AVGO", "HPQ"}, Decimal("8172.22"), _prefs(), 0)
    assert reason == "bought"
    assert choice["symbol"] == "CLX"
    assert [(c["symbol"], c["reason"]) for c in candidates] == [("AVGO", "held"), ("CLX", "buy")]


def test_every_skip_reason_is_recorded():
    ranked = [
        _row("APP", "393.68", 0.60, HOLD),
        _row("AMD", "585.30", 0.55),
        _row("MPWR", "1447.40", 0.52),
        _row("TSLA", "400", 0.50),
        _row("CLX", "108.20", 0.45),
    ]
    choice, candidates, _reason = plan_buy(ranked, {"AMD"}, Decimal("5000"), _prefs("whole"), 0, sold={"TSLA"})
    assert choice["symbol"] == "CLX" and choice["amount"] == Decimal("9")
    assert [c["reason"] for c in candidates] == ["not_buy", "held", "too_expensive", "sold", "buy"]


def test_no_buy_when_the_cash_does_not_cover_lot_and_commission():
    ranked = [_row("CLX", "108.20")]
    choice, candidates, reason = plan_buy(ranked, set(), Decimal("1000.50"), _prefs(), 0)
    assert choice is None and reason == "no_cash"
    assert candidates[0]["reason"] == "no_cash"
    assert plan_buy(ranked, set(), Decimal("1001"), _prefs(), 0)[0]["symbol"] == "CLX"


def test_whole_shares_can_still_fit_a_cheaper_name_when_cash_is_short():
    ranked = [_row("TWO", "499", 0.6), _row("ONE", "600", 0.5)]
    choice, candidates, _reason = plan_buy(ranked, set(), Decimal("700"), _prefs("whole"), 0)
    assert candidates[0]["reason"] == "no_cash"
    assert choice["symbol"] == "ONE" and choice["amount"] == Decimal("1")
    assert plan_buy(ranked, set(), Decimal("1000"), _prefs("whole"), 0)[0]["symbol"] == "TWO"


def test_daily_cap_stops_the_buy_and_zero_means_unlimited():
    ranked = [_row("CLX", "108.20")]
    assert plan_buy(ranked, set(), Decimal("9000"), _prefs(cap=2), 2) == (None, [], "daily_cap")
    assert plan_buy(ranked, set(), Decimal("9000"), _prefs(cap=2), 1)[2] == "bought"
    assert plan_buy(ranked, set(), Decimal("9000"), _prefs(cap=0), 40)[2] == "bought"


def test_walk_stops_at_a_score_at_or_under_zero():
    ranked = [_row("A", "10", 0.3, HOLD), _row("B", "10", 0.0, BUY), _row("C", "10", -0.4, SELL)]
    choice, candidates, reason = plan_buy(ranked, set(), Decimal("9000"), _prefs(), 0)
    assert choice is None and reason == "no_candidate"
    assert [c["symbol"] for c in candidates] == ["A"]


def test_long_candidate_lists_are_cut_and_counted():
    ranked = [_row(f"N{i}", "100", 0.9 - i / 1000) for i in range(LOGGED + 7)]
    _choice, candidates, reason = plan_buy(ranked, set(), Decimal("10"), _prefs(), 0)
    assert reason == "no_cash"
    assert len(candidates) == LOGGED + 1
    assert candidates[-1] == {"more": 7}


def test_next_bot_buys_follow_the_sizing():
    board = [{"symbol": "MPWR", "price": "1447.40"}, {"symbol": "CLX", "price": "108.20"}]
    assert [r["symbol"] for r in top_buys(board, set(), _prefs())] == ["MPWR", "CLX"]
    assert [r["symbol"] for r in top_buys(board, set(), _prefs("whole"))] == ["CLX"]
    assert [r["symbol"] for r in top_buys(board, {"CLX"})] == ["MPWR"]
