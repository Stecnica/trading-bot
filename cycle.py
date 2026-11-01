#!/usr/bin/env python3
"""Aggiorna i prezzi e vende i lotti che hanno raggiunto la soglia."""

import os
import sys
SITE = "/var/www/clients/client0/web5/home/default_botmanager/.local/lib/python3.10/site-packages"
if SITE not in sys.path:
    sys.path.insert(0, SITE)

os.chdir("/var/www/clients/client0/web5/web")
sys.path.insert(0, "/var/www/clients/client0/web5/web")

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
        log.info("ciclo già in esecuzione")
        return 0
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    conn = None
    try:
        write_status("running", "prices.db")
        conn = connect()
        ensure_schema(conn)
        seed_preferences(conn)
        prefs = load_preferences(conn)
        log.info("ciclo prezzi da Massive")

        def progress(message):
            write_status("running", message)
            log.info(message)

        stored, warning = update_from_massive(conn, progress)
        sold = sell_ready_lots(conn, prefs)
        if warning:
            write_status("error", warning)
            log.warning("ciclo incompleto, barre %s vendite %s", stored, sold)
        elif stored == 0:
            write_status("ok", f"prices.fresh|{sold}")
            log.info("ciclo concluso, nessuna barra nuova, vendite %s", sold)
        else:
            write_status("ok", f"prices.done|{stored}|{sold}")
            log.info("ciclo concluso, barre %s vendite %s", stored, sold)
        return 0
    except Exception as exc:
        log.exception("ciclo fallito")
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
