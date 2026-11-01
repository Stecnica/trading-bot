#!/usr/bin/env python3
"""Rilegge le sedute già in archivio e compila i campi prima scartati."""

import os
import sys

SITE = "/var/www/clients/client0/web5/home/default_botmanager/.local/lib/python3.10/site-packages"
if SITE not in sys.path:
    sys.path.insert(0, SITE)

os.chdir("/var/www/clients/client0/web5/web")
sys.path.insert(0, "/var/www/clients/client0/web5/web")

import socket

from bot_config import LOCK_PATH, get_logger
from bot_db import connect, cycle_running, ensure_schema, write_status
from bot_massive import reread_stored_sessions

log = get_logger()


def main():
    socket.setdefaulttimeout(90)
    if cycle_running():
        log.info("rilettura non partita: un ciclo è già in esecuzione")
        return 0
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    conn = None
    try:
        write_status("running", "reread.running")
        conn = connect()
        ensure_schema(conn)
        log.info("rilettura campi Massive")

        def progress(message):
            write_status("running", message)
            log.info(message)

        stored, warning = reread_stored_sessions(conn, progress)
        if warning:
            write_status("error", warning)
            log.warning("rilettura incompleta, barre %s", stored)
        else:
            write_status("ok", f"reread.done|{stored}")
            log.info("rilettura conclusa, barre %s", stored)
        return 0
    except Exception:
        log.exception("rilettura fallita")
        write_status("error", "reread.stopped")
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
