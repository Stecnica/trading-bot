import logging
import tempfile
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from massive.exceptions import BadResponse

import bot_config
import bot_massive
from bot_plan import PLANS

SILENT = logging.getLogger("tests.silent")
SILENT.addHandler(logging.NullHandler())
SILENT.propagate = False
bot_massive.log = SILENT

END = date(2026, 11, 13)


def test_depth_follows_the_plan():
    assert bot_massive.history_start("basic", END) == date(2024, 11, 20)
    assert bot_massive.history_start("starter", END) == date(2021, 11, 20)
    assert bot_massive.history_start("developer", END) == date(2016, 11, 20)
    assert bot_massive.history_start("advanced", END) == date(2003, 9, 10)
    assert bot_massive.history_start("starter", date(2028, 2, 29)) == date(2023, 3, 7)


def _bars(count):
    return [SimpleNamespace(ticker=f"S{index}", close=10, open=10, high=10, low=10, volume=1, vwap=10,
                            transactions=1, timestamp=1, otc=False) for index in range(count)]


class _Client:
    """Grouped days by date: a list of bars, an exception text, or missing for a holiday."""

    def __init__(self, days):
        self.days = days
        self.asked = []

    def get_grouped_daily_aggs(self, day, **_kwargs):
        self.asked.append(day)
        found = self.days.get(day, [])
        if isinstance(found, str):
            raise BadResponse(found)
        return found


def _harness(test):
    def run():
        names = ("_api_key", "candidate_symbols", "RESTClient", "upsert_bars", "_counts", "last_completed_session",
                 "SESSIONS_PATH", "CLOSED_PATH", "BACKFILL_STATUS", "PRICES_LOCK", "_free_bytes")
        saved = {name: getattr(bot_massive, name) for name in names}
        sleep = bot_massive.clock.sleep
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            waits = []
            written = []
            bot_massive._api_key = lambda: "test-key"
            bot_massive.candidate_symbols = lambda _limit: [f"S{index}" for index in range(500)]
            bot_massive.upsert_bars = lambda _conn, rows: written.append(rows) or len(rows)
            bot_massive._counts = lambda _conn: {}
            bot_massive.last_completed_session = lambda: END
            bot_massive.SESSIONS_PATH = folder / "sessions.txt"
            bot_massive.CLOSED_PATH = folder / "closed.txt"
            bot_massive.BACKFILL_STATUS = folder / "status.json"
            bot_massive.PRICES_LOCK = folder / "prices.lock"
            bot_massive._free_bytes = lambda: 10 * 1024 ** 3
            bot_massive.clock.sleep = waits.append
            try:
                test(SimpleNamespace(folder=folder, waits=waits, written=written))
            finally:
                bot_massive.clock.sleep = sleep
                for name, value in saved.items():
                    setattr(bot_massive, name, value)

    run.__name__ = test.__name__
    return run


def _use(client):
    bot_massive.RESTClient = lambda **_kwargs: client


@_harness
def test_fill_skips_stored_days_and_resumes(env):
    bot_massive.SESSIONS_PATH.write_text("2026-11-13\n2026-11-12\n", encoding="utf-8")
    client = _Client({"2026-11-11": _bars(1500), "2026-11-10": _bars(1500), "2026-11-09": "unreachable"})
    _use(client)
    status = bot_massive.backfill(None, dict(PLANS["starter"], name="starter"), limit=3)
    assert client.asked == ["2026-11-11", "2026-11-10", "2026-11-09"]
    assert status["state"] == "stopped" and status["done"] == 2 and status["rows"] == 1000
    client.days["2026-11-09"] = _bars(1500)
    client.asked.clear()
    status = bot_massive.backfill(None, dict(PLANS["starter"], name="starter"), limit=1)
    assert client.asked == ["2026-11-09"] and status["state"] == "done"
    assert bot_massive.read_backfill_status()["done"] == 1


@_harness
def test_holiday_is_remembered_and_the_plan_window_ends_the_fill(env):
    client = _Client({"2026-11-13": _bars(1500), "2026-11-11": "Your plan doesn't include this data timeframe. historical entitlement"})
    _use(client)
    status = bot_massive.backfill(None, dict(PLANS["starter"], name="starter"))
    assert client.asked == ["2026-11-13", "2026-11-12", "2026-11-11"]
    assert status["state"] == "done" and status["reason"] == "window" and status["start"] == "2026-11-12"
    assert bot_massive.CLOSED_PATH.read_text(encoding="utf-8").split() == ["2026-11-12"]


@_harness
def test_old_sessions_with_fewer_listed_names_are_kept(env):
    client = _Client({"2026-11-13": _bars(1500)[:250] + [SimpleNamespace(ticker=f"X{index}", close=1, open=1, high=1, low=1, volume=1, vwap=1, transactions=1, timestamp=1, otc=False) for index in range(1200)]})
    _use(client)
    status = bot_massive.backfill(None, dict(PLANS["starter"], name="starter"), limit=1)
    assert status["rows"] == 250 and status["state"] == "done"


@_harness
def test_basic_waits_between_calls_paid_plans_do_not(env):
    _use(_Client({day: _bars(1500) for day in ("2026-11-13", "2026-11-12", "2026-11-11")}))
    bot_massive.backfill(None, dict(PLANS["starter"], name="starter"), limit=3)
    assert env.waits == []
    bot_massive.SESSIONS_PATH.unlink()
    bot_massive.backfill(None, dict(PLANS["basic"], name="basic"), limit=3)
    assert env.waits == [bot_massive.PAUSE_SECONDS] * 2


@_harness
def test_fill_stops_before_the_disk_is_full_and_on_a_partial_session(env):
    _use(_Client({"2026-11-13": _bars(1500)}))
    bot_massive._free_bytes = lambda: 100 * 1024 * 1024
    status = bot_massive.backfill(None, dict(PLANS["starter"], name="starter"))
    assert (status["state"], status["reason"], status["done"]) == ("stopped", "disk", 0)
    bot_massive._free_bytes = lambda: 10 * 1024 ** 3
    _use(_Client({"2026-11-13": _bars(300)}))
    status = bot_massive.backfill(None, dict(PLANS["starter"], name="starter"))
    assert (status["state"], status["reason"]) == ("stopped", "partial")


@_harness
def test_edge_refusals_of_a_smaller_plan_are_asked_again(env):
    bot_massive.SESSIONS_PATH.write_text("2026-11-13\n2026-11-12\n", encoding="utf-8")
    bot_massive.CLOSED_PATH.write_text("2026-11-12\n2026-11-11\n", encoding="utf-8")
    _start, _end, days = bot_massive.backfill_plan(None, "starter")
    assert days[0] == date(2026, 11, 11)


def test_lock_is_exclusive_and_released_with_the_holder():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "prices.lock"
        assert not bot_config.lock_held(path)
        with bot_config.file_lock(path):
            import subprocess
            import sys

            probe = "import sys; sys.path.insert(0, sys.argv[1]); import bot_config, pathlib; print(bot_config.lock_held(pathlib.Path(sys.argv[2])))"
            held = subprocess.run([sys.executable, "-c", probe, str(Path(bot_config.__file__).parent), str(path)], capture_output=True, text=True)
            assert held.stdout.strip() == "True"
        assert not bot_config.lock_held(path)
        with bot_config.file_lock(path):
            started = timedelta(seconds=0)
            try:
                with bot_config.file_lock(path, timeout=0):
                    pass
            except TimeoutError:
                started = None
            assert started is None
