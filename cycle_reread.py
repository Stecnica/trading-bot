#!/usr/bin/env python3
"""Reread sessions already in the archive and fill the fields that were discarded."""

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
from bot_db import connect, cycle_running, ensure_schema, load_preferences, write_status
from bot_massive import reread_stored_sessions
from bot_plan import current_plan

log = get_logger()


def main():
    socket.setdefaulttimeout(90)
    if cycle_running():
        log.info("reread not started: a cycle is already running")
        return 0
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    conn = None
    held = ExitStack()
    try:
        # A history fill writes one session at a time under this lock: wait for that write.
        held.enter_context(file_lock(PRICES_LOCK, timeout=240))
        write_status("running", "reread.running")
        conn = connect()
        ensure_schema(conn)
        log.info("reread of Massive fields")

        def progress(message):
            write_status("running", message)
            log.info(message)

        plan = current_plan(load_preferences(conn))
        stored, warning = reread_stored_sessions(conn, progress, throttle=plan["throttle"])
        if warning:
            write_status("error", warning)
            log.warning("reread incomplete, bars %s", stored)
        else:
            write_status("ok", f"reread.done|{stored}")
            log.info("reread finished, bars %s", stored)
        return 0
    except Exception:
        log.exception("reread failed")
        write_status("error", "reread.stopped")
        return 1
    finally:
        if conn is not None:
            conn.close()
        held.close()
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
