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
    fetch_transactions,
    load_preferences,
    seed_preferences,
    sell_ready_lots,
    write_status,
)
from bot_logic import open_lots
from bot_market import SESSION_SIZE, candidate_symbols, symbols_due, update_quotes

log = get_logger()


def symbols_to_refresh(conn, prefs):
    """Un giro scarica al massimo 100 titoli ancora indietro, su tutto l'elenco."""
    universe = candidate_symbols(500)
    lots, _unmatched = open_lots(fetch_transactions(conn))
    ordered = []
    seen = set()
    for symbol in [lot.asset for lot in lots] + [prefs["focus_asset"]] + universe:
        if symbol and symbol not in seen:
            seen.add(symbol)
            ordered.append(symbol)
    return symbols_due(conn, ordered)[:SESSION_SIZE]


def main():
    socket.setdefaulttimeout(60)
    if cycle_running():
        log.info("ciclo già in esecuzione")
        return 0
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    conn = None
    try:
        write_status("running", "Connessione al database.")
        conn = connect()
        ensure_schema(conn)
        seed_preferences(conn)
        prefs = load_preferences(conn)
        symbols = symbols_to_refresh(conn, prefs)
        write_status("running", f"Questo giro: {len(symbols)} titoli. Ogni giro ne prende al massimo 100, fra quelli ancora indietro.")
        log.info("ciclo su %s titoli", len(symbols))

        def progress(message):
            write_status("running", message)
            log.info(message)

        stored, warning = update_quotes(conn, symbols, progress)
        sold = sell_ready_lots(conn, prefs)
        if warning:
            write_status("error", warning)
            log.warning("ciclo incompleto, barre %s vendite %s", stored, sold)
        elif stored == 0:
            write_status("ok", f"Prezzi già aggiornati. Vendite registrate: {sold}.")
            log.info("ciclo concluso, nessuna barra nuova, vendite %s", sold)
        else:
            write_status("ok", f"Aggiornamento concluso. Barre scritte: {stored}. Vendite registrate: {sold}.")
            log.info("ciclo concluso, barre %s vendite %s", stored, sold)
        return 0
    except Exception as exc:
        log.exception("ciclo fallito")
        write_status("error", "Aggiornamento interrotto. Dettaglio nel log.")
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
