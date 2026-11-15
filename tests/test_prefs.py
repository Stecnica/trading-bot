from bot_db import preference_patch


def _patch(**form):
    clamped = []
    values, error = preference_patch(form, clamped)
    return values, error, clamped


def test_fee_rate_over_the_top_is_clamped_to_the_maximum():
    assert _patch(fee_rate="5") == ({"fee_rate": "0.1"}, None, ["fee_rate"])


def test_negative_values_are_clamped_to_the_minimum():
    assert _patch(trail="-1", tax_rate="-0.2") == ({"tax_rate": "0", "trail": "0"}, None, ["tax_rate", "trail"])


def test_investment_and_capital_never_go_under_one():
    values, error, clamped = _patch(max_investment="0", initial_capital="-5")
    assert error is None
    assert values == {"max_investment": "1", "initial_capital": "1"}


def test_integers_are_clamped_and_follow_the_step():
    values, error, clamped = _patch(names="1000", ui_scale="83", max_hold_days="0")
    assert error is None
    assert values == {"names": "500", "max_hold_days": "1", "ui_scale": "85"}
    assert sorted(clamped) == ["max_hold_days", "names", "ui_scale"]


def test_values_in_range_are_not_reported():
    assert _patch(profit_threshold="0.05", sell_delay_score="0.2") == (
        {"profit_threshold": "0.05", "sell_delay_score": "0.2"},
        None,
        [],
    )


def test_unreadable_text_is_still_an_error():
    values, error, _clamped = _patch(fee_rate="abc")
    assert values is None and error
    values, error, _clamped = _patch(fee_rate="nan")
    assert values is None and error


def test_history_drawing_defaults_to_vector():
    from bot_db import interpret

    assert interpret({})["chart_render"] == "vector"
    assert interpret({"chart_render": "bogus"})["chart_render"] == "vector"
    assert interpret({"chart_render": "image"})["chart_render"] == "image"
