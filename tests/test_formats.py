from bot_charts import _factor, treemap_layout
from bot_decide import score_label
from index import history_stats


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
