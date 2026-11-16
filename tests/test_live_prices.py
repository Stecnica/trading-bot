import logging
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from massive.exceptions import BadResponse

import bot_massive
import bot_plan
from bot_db import interpret, preference_patch, price_moment
from bot_decide import decision_prices, plan_buy
from bot_score import BUY

SILENT = logging.getLogger("tests.silent")
SILENT.addHandler(logging.NullHandler())
SILENT.propagate = False
bot_plan.log = bot_massive.log = SILENT

NY = ZoneInfo("America/New_York")
MONDAY = datetime(2026, 11, 16, tzinfo=NY)
FIFTEEN = timedelta(minutes=15)


def _ns(moment):
    return int(moment.timestamp() * 1e9)


def _snap(ticker, close, updated, day=True):
    bar = SimpleNamespace(open=1.0, high=2.0, low=0.5, close=close, volume=10, vwap=1.5) if day else None
    return SimpleNamespace(ticker=ticker, day=bar, updated=updated)


def _at(hour, minute=0):
    return MONDAY.replace(hour=hour, minute=minute)


def test_session_window_follows_the_delay_of_the_plan():
    assert not bot_massive.in_session(FIFTEEN, _at(9, 29))
    assert bot_massive.in_session(FIFTEEN, _at(9, 30))
    assert bot_massive.in_session(FIFTEEN, _at(16, 14))
    assert not bot_massive.in_session(FIFTEEN, _at(16, 15))
    assert not bot_massive.in_session(timedelta(0), _at(16, 0))
    assert not bot_massive.in_session(FIFTEEN, _at(12) + timedelta(days=5))


def test_live_rows_keep_only_todays_regular_session():
    now = _at(12, 15)
    snaps = [
        _snap("CLX", 110.19, _ns(_at(12, 0))),
        _snap("CLX", 999.0, _ns(_at(12, 0))),
        _snap("BRK.B", 500.0, _ns(_at(11, 59))),
        _snap("PRE", 10.0, _ns(_at(9, 10))),
        _snap("LATE", 10.0, _ns(_at(16, 30))),
        _snap("OLD", 10.0, _ns(_at(12) - timedelta(days=3))),
        _snap("ZERO", 0, _ns(_at(12))),
        _snap("NODAY", 10.0, _ns(_at(12)), day=False),
        _snap("OTHER", 10.0, _ns(_at(12))),
    ]
    wanted = {"CLX", "BRK-B", "PRE", "LATE", "OLD", "ZERO", "NODAY"}
    rows = bot_massive.live_rows(snaps, wanted, now)
    assert [row["asset_name"] for row in rows] == ["CLX", "BRK-B"]
    clx = rows[0]
    assert clx["timestamp"] == datetime(2026, 11, 16)
    assert clx["price"] == Decimal("110.19")
    assert clx["live"] == 1
    assert clx["bar_ms"] == int(_at(12, 0).timestamp() * 1000)


def test_a_provisional_bar_is_priced_at_its_snapshot_moment():
    moment = datetime(2026, 11, 16, 18, 21, 36)
    market = {"live": 1, "bar_ms": int(moment.timestamp() * 1000), "timestamp": datetime(2026, 11, 16)}
    assert price_moment(market) == moment
    assert price_moment(dict(market, live=0)) is None
    assert price_moment(None) is None


def test_fill_and_decision_carry_the_price_source_and_moment():
    moment = datetime(2026, 11, 16, 18, 21, 36)
    ranked = [
        {"symbol": "CLX", "price": Decimal("110.19"), "score": 0.4, "side": BUY, "timestamp": moment, "source": "live"},
        {"symbol": "HPQ", "price": Decimal("29.36"), "score": 0.3, "side": BUY, "timestamp": datetime(2026, 11, 13), "source": "close"},
    ]
    prefs = {"max_investment": Decimal("1000"), "fee_rate": Decimal("0.001"), "lot_sizing": "fractional", "max_buys_per_day": 0}
    choice, _candidates, reason = plan_buy(ranked, set(), Decimal("5000"), prefs, 0)
    assert reason == "bought"
    assert choice["timestamp"] == moment and choice["source"] == "live"
    assert decision_prices(ranked, choice) == ("live", moment)
    assert decision_prices(ranked) == ("live", moment)
    assert decision_prices(ranked[1:]) == ("close", datetime(2026, 11, 13))
    assert decision_prices([]) == (None, None)


def test_plan_pref_defaults_to_auto_and_refuses_unknown_plans():
    assert interpret({})["massive_plan"] == "auto"
    assert interpret({"massive_plan": "gold"})["massive_plan"] == "auto"
    assert preference_patch({"massive_plan": "starter"}, [])[0] == {"massive_plan": "starter"}
    assert preference_patch({"massive_plan": "gold"}, [])[1]


def test_refusals_are_told_apart():
    assert bot_plan.refusal_kind('NOT_AUTHORIZED: You are not entitled to this data. Please upgrade your plan') == "plan"
    assert bot_plan.refusal_kind("HTTP 429 too many requests") == "rate"
    assert bot_plan.refusal_kind("Unknown API Key") == "auth"
    assert bot_plan.refusal_kind("connection reset") == "other"


class _Client:
    def __init__(self, snapshot=None, error=None, deep=False):
        self.snapshot = snapshot
        self.error = error
        self.deep = deep
        self.calls = 0

    def get_snapshot_ticker(self, _market, _ticker):
        self.calls += 1
        if self.error:
            raise BadResponse(self.error)
        return self.snapshot

    def get_aggs(self, *_args):
        self.calls += 1
        if not self.deep:
            raise BadResponse("Your plan doesn't include this data timeframe. historical entitlement")
        return [object()]


def _isolated(test):
    def run():
        original = bot_plan.PLAN_PATH
        key = bot_massive._api_key
        with tempfile.TemporaryDirectory() as folder:
            bot_plan.PLAN_PATH = Path(folder) / "massive_plan.json"
            bot_massive._api_key = lambda: "test-key"
            try:
                test()
            finally:
                bot_plan.PLAN_PATH = original
                bot_massive._api_key = key

    run.__name__ = test.__name__
    return run


@_isolated
def test_basic_key_is_detected_from_the_refused_snapshot_and_cached_for_the_day():
    client = _Client(error='{"status":"NOT_AUTHORIZED","message":"You are not entitled to this data."}')
    plan = bot_plan.current_plan({"massive_plan": "auto"}, _at(11), client)
    assert (plan["name"], plan["intraday"], plan["throttle"]) == ("basic", False, True)
    bot_plan.current_plan({"massive_plan": "auto"}, _at(13), client)
    assert client.calls == 1


@_isolated
def test_rate_limit_means_basic():
    plan = bot_plan.current_plan({"massive_plan": "auto"}, _at(11), _Client(error="429 Too Many Requests"))
    assert plan["name"] == "basic"


@_isolated
def test_delayed_and_real_time_keys():
    late = SimpleNamespace(updated=_ns(_at(10, 45)))
    starter = bot_plan.detect(_at(11), _Client(late))
    assert (starter["plan"], starter["delay_seconds"]) == ("starter", 900)
    assert bot_plan.detect(_at(11), _Client(late, deep=True))["plan"] == "developer"
    fresh = SimpleNamespace(updated=_ns(_at(10, 59)))
    assert bot_plan.detect(_at(11), _Client(fresh))["plan"] == "advanced"


@_isolated
def test_a_closed_market_detection_is_measured_again_in_the_session():
    late = SimpleNamespace(updated=_ns(_at(16) - timedelta(minutes=15)))
    client = _Client(late)
    first = bot_plan.current_plan({"massive_plan": "auto"}, _at(20), client)
    assert first["name"] == "starter"
    calls = client.calls
    bot_plan.current_plan({"massive_plan": "auto"}, _at(20, 30), client)
    assert client.calls == calls
    client.snapshot = SimpleNamespace(updated=_ns(_at(10, 45)))
    bot_plan.current_plan({"massive_plan": "auto"}, _at(11) + timedelta(days=1), client)
    assert client.calls > calls


@_isolated
def test_manual_plan_overrides_detection_until_the_snapshot_is_refused():
    client = _Client(error="NOT_AUTHORIZED")
    plan = bot_plan.current_plan({"massive_plan": "starter"}, _at(11), client)
    assert (plan["name"], plan["source"], plan["detected"], plan["intraday"], plan["throttle"]) == (
        "starter", "manual", "basic", True, False,
    )
    bot_plan.mark_refused(_at(11))
    refused = bot_plan.current_plan({"massive_plan": "starter"}, _at(11, 30), client)
    assert refused["intraday"] is False and refused["refused"]
    again = bot_plan.current_plan({"massive_plan": "starter"}, _at(12), client)
    assert again["intraday"] is False
    tomorrow = bot_plan.current_plan({"massive_plan": "starter"}, _at(11) + timedelta(days=1), client)
    assert tomorrow["intraday"] is True


@_isolated
def test_unreachable_massive_is_retried_after_an_hour_and_never_raises():
    client = _Client(error="connection reset by peer")
    plan = bot_plan.current_plan({"massive_plan": "auto"}, _at(11), client)
    assert plan["name"] == "basic"
    bot_plan.current_plan({"massive_plan": "auto"}, _at(11, 30), client)
    assert client.calls == 1
    bot_plan.current_plan({"massive_plan": "auto"}, _at(12, 1), client)
    assert client.calls == 2


def test_throttle_waits_only_for_basic():
    waits = []
    saved = {name: getattr(bot_massive, name) for name in ("_api_key", "candidate_symbols", "_pending", "RESTClient", "upsert_bars", "drop_live_bars", "_remember", "last_completed_session")}
    sleep = bot_massive.clock.sleep
    days = [datetime(2026, 11, 13).date(), datetime(2026, 11, 12).date()]
    bars = [SimpleNamespace(ticker=f"S{index}", close=10, open=10, high=10, low=10, volume=1, vwap=10, transactions=1, timestamp=1, otc=False) for index in range(450)]

    class Client:
        def __init__(self, **_kwargs):
            pass

        def get_grouped_daily_aggs(self, *_args, **_kwargs):
            return bars

    try:
        bot_massive._api_key = lambda: "test-key"
        bot_massive.candidate_symbols = lambda _limit: [bar.ticker for bar in bars]
        bot_massive._pending = lambda *_args: list(days)
        bot_massive.RESTClient = Client
        bot_massive.upsert_bars = lambda _conn, rows: len(rows)
        bot_massive.drop_live_bars = lambda _conn, _day: 0
        bot_massive._remember = lambda *_args: None
        bot_massive.last_completed_session = lambda: days[0]
        bot_massive.clock.sleep = waits.append
        bot_massive.update_from_massive(None, lambda _message: None, throttle=False)
        assert waits == []
        bot_massive.update_from_massive(None, lambda _message: None, throttle=True)
        assert waits == [bot_massive.PAUSE_SECONDS]
    finally:
        bot_massive.clock.sleep = sleep
        for name, value in saved.items():
            setattr(bot_massive, name, value)
