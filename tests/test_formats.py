from decimal import Decimal

from bot_charts import _factor, treemap_layout
from bot_db import drop_text
from bot_decide import score_label
from index import format_signed_pct, glue_parts, history_stats


def test_chart_stats_use_three_decimals():
    series = [
        {"price": "100", "low_price": "99.5", "high_price": "101"},
        {"price": "114.47", "low_price": None, "high_price": "115.2"},
    ]
    stats = history_stats(series)
    assert stats["change"] == "+14.470 %"
    assert (stats["last"], stats["low"], stats["high"]) == ("114.470", "99.500", "115.200")


def test_volume_labels_use_three_decimals():
    tile = treemap_layout([{"asset": "AAPL", "volume": 1, "daily": "0.0125", "state": "crescita"}])[0]
    assert "+1.250%" in tile["title"]
    assert _factor(1.6) == "(x1.600)"
    short, detail = score_label({"score": 0.5, "side": "buy", "weights": {"trend": 0.25}})
    assert short.startswith("+0.500 ") and "trend 0.250" in detail


def test_session_amount_shows_the_currency_symbol_per_locale():
    from bot_charts import _money
    from bot_i18n import activate

    try:
        activate("it")
        assert _money(11_357_000_000) == "$ 11.357 miliardi"
        activate("en")
        assert _money(11_357_000_000) == "$11.357 billion"
        activate("de")
        assert _money(950) == "950.000 $"
    finally:
        activate("en")


def test_no_negative_zero_in_percentages():
    assert drop_text(Decimal("0")) == "0.000 %"
    assert drop_text(Decimal("0.0000004")) == "0.000 %"
    assert drop_text(Decimal("0.08754")) == "−8.754 %"
    assert format_signed_pct(Decimal("-0.0000004")) == "0.000 %"
    assert format_signed_pct(Decimal("-0.04562")) == "−4.562 %"


def test_glued_outcome_wraps_only_after_a_separator():
    html = str(glue_parts("armed · peak 585.300 · 0.000 %"))
    assert html.count('class="text-nowrap"') == 3
    assert "&nbsp;·</span> <span" in html
    assert not html.split("</span> ")[-1].lstrip().startswith("·")
    assert str(glue_parts("under the threshold")) == '<span class="text-nowrap">under the threshold</span>'
