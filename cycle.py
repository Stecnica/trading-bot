#!/usr/bin/env python3
"""Update prices and sell the lots that have reached the threshold."""

import os
import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(_HERE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from bot_config import install_import_path

install_import_path()

import socket
from contextlib import ExitStack

from bot_config import LOCK_PATH, PRICES_LOCK, file_lock, get_logger
from bot_decide import apply_once
from bot_db import (
    connect,
    cycle_running,
    ensure_schema,
    load_preferences,
    seed_preferences,
    sell_ready_lots,
    write_status,
)
from bot_massive import in_session, update_from_massive, update_live
from bot_plan import PLANS, current_plan, mark_refused

log = get_logger()


def main():
    socket.setdefaulttimeout(90)
    if cycle_running():
        log.info("cycle already running")
        return 0
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    conn = None
    held = ExitStack()
    try:
        # A history fill writes one session at a time under this lock: wait for that write.
        held.enter_context(file_lock(PRICES_LOCK, timeout=240))
        write_status("running", "prices.db")
        conn = connect()
        ensure_schema(conn)
        seed_preferences(conn)
        prefs = load_preferences(conn)
        log.info("price cycle from Massive")

        def progress(message):
            write_status("running", message)
            log.info(message)

        plan = _plan(prefs)
        stored, warning = update_from_massive(conn, progress, throttle=plan["throttle"])
        if plan["intraday"] and in_session(plan["delay"]):
            stored += _live(conn, progress)
        trailing = []
        sold = sell_ready_lots(conn, prefs, sold_out=trailing)
        decision = apply_once(conn, sold_before=trailing)
        bought = decision["bought"]
        log.info(
            "score decision buy=%s score_sold=%s trailing_sold=%s cash=%s reason=%s prices=%s %s",
            bought["symbol"] if bought else "none",
            ",".join(decision["sold"]) or "none",
            ",".join(trailing) or "none",
            decision["cash"],
            decision["reason"],
            decision["source"],
            decision["priced_at"],
        )
        if warning:
            write_status("error", warning)
            log.warning("cycle incomplete, bars %s sales %s", stored, sold)
        elif stored == 0:
            write_status("ok", f"prices.fresh|{sold}")
            log.info("cycle finished, no new bars, sales %s", sold)
        else:
            write_status("ok", f"prices.done|{stored}|{sold}")
            log.info("cycle finished, bars %s sales %s", stored, sold)
        return 0
    except Exception as exc:
        log.exception("cycle failed")
        write_status("error", "prices.stopped")
        print(exc, file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()
        held.close()
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass


def _plan(prefs):
    """The plan of this cycle. Detection never stops the cycle: on any failure it runs as Basic."""
    try:
        return current_plan(prefs)
    except Exception:
        log.exception("massive plan not resolved, end of day for this cycle")
        return dict(PLANS["basic"], name="basic", source="fallback")


def _live(conn, progress):
    """Delayed or real-time prices for today's bar. A refusal turns intraday off for the day;
    any other failure leaves the daily bars in place."""
    try:
        stored, warning, refusal = update_live(conn, progress)
    except Exception:
        log.exception("intraday snapshot failed, daily bars kept")
        return 0
    if refusal:
        mark_refused()
    elif warning:
        log.warning("intraday snapshot not used: %s", warning)
    return stored


if __name__ == "__main__":
    raise SystemExit(main())
