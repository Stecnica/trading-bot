#!/usr/bin/env python3
"""Fill the daily price history back to the depth of the Massive plan.

    python backfill.py            fill for the plan in use (detected, or the massive_plan preference)
    python backfill.py --plan starter
    python backfill.py --dry-run  count the missing sessions and estimate rows, size and time
    python backfill.py --limit 20 fetch at most 20 sessions

One process at a time (backfill.lock). It can be stopped at any moment and started again:
it continues from the next missing session.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(_HERE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from bot_config import install_import_path

install_import_path()

import argparse
import socket

from bot_config import BACKFILL_LOCK, file_lock, get_logger
from bot_db import connect, ensure_schema, load_preferences
from bot_massive import (
    PAUSE_SECONDS,
    _free_bytes,
    backfill,
    backfill_plan,
    read_backfill_status,
    write_backfill_status,
)
from bot_plan import PLANS, current_plan

log = get_logger()
# Measured on market_history: data plus indexes per stored bar, and a paid-plan call with its write.
BYTES_PER_ROW = 300
SECONDS_PER_CALL = 2.5
NAMES_PER_SESSION = 470


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fill the daily price history for the Massive plan.")
    parser.add_argument("--plan", choices=sorted(PLANS), help="plan depth to use instead of the plan in use")
    parser.add_argument("--dry-run", action="store_true", help="only count and estimate")
    parser.add_argument("--limit", type=int, help="fetch at most this many sessions")
    args = parser.parse_args(argv)
    socket.setdefaulttimeout(90)
    conn = connect()
    try:
        ensure_schema(conn)
        prefs = load_preferences(conn)
        plan = current_plan(dict(prefs, massive_plan=args.plan) if args.plan else prefs)
        if args.dry_run:
            start, end, days = backfill_plan(conn, plan["name"])
            pause = PAUSE_SECONDS if plan["throttle"] else 0
            print(f"plan {plan['name']}: {start} to {end}, {len(days)} sessions missing")
            print(f"estimate: {len(days) * NAMES_PER_SESSION} bars, {len(days) * NAMES_PER_SESSION * BYTES_PER_ROW / 1048576:.0f} MB, "
                  f"{len(days) * (SECONDS_PER_CALL + pause) / 60:.0f} minutes; {_free_bytes() / 1048576:.0f} MB free")
            return 0
        try:
            with file_lock(BACKFILL_LOCK, timeout=0):
                status = backfill(conn, plan, limit=args.limit)
        except TimeoutError:
            print("a history fill is already running")
            return 1
        print(f"{status['state']}: {status['done']} of {status['total']} sessions, {status['rows']} bars, "
              f"{status['start']} to {status['end']}" + (f", {status['reason']}" if status.get("reason") else ""))
        return 0 if status["state"] in ("done", "running") else 2
    except Exception:
        log.exception("history fill failed")
        status = read_backfill_status()
        if status.get("state") == "running":
            write_backfill_status(dict(status, state="stopped", reason="error"))
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
