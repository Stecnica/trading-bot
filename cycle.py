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

from bot_config import LOCK_PATH, get_logger
from bot_db import (
    connect,
    cycle_running,
    ensure_schema,
    load_preferences,
    seed_preferences,
    sell_ready_lots,
    write_status,
)
from bot_massive import update_from_massive

log = get_logger()


def main():
    socket.setdefaulttimeout(90)
    if cycle_running():
        log.info("cycle already running")
        return 0
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    conn = None
    try:
        write_status("running", "prices.db")
        conn = connect()
        ensure_schema(conn)
        seed_preferences(conn)
        prefs = load_preferences(conn)
        log.info("price cycle from Massive")

        def progress(message):
            write_status("running", message)
            log.info(message)

        stored, warning = update_from_massive(conn, progress)
        sold = sell_ready_lots(conn, prefs)
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
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
