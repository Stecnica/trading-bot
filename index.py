"""Pagina del trading bot: blocchi di volume, storico e vendite sulla soglia."""

import os
import subprocess
import sys
from datetime import datetime, timedelta
from decimal import Decimal

from flask import Flask, Response, abort, redirect, render_template, request, session, url_for
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.exceptions import HTTPException

SITE = "/var/www/clients/client0/web5/home/default_botmanager/.local/lib/python3.10/site-packages"
if SITE not in sys.path:
    sys.path.insert(0, SITE)

from bot_auth import authenticate, ensure_password_hash, session_alive, stamp_session
from bot_charts import history_png, treemap_layout, treemap_png
from bot_market import security_names
from bot_config import (
    FLASK_SECRET_PATH,
    LOG_PATH,
    MPLCONFIG,
    SITE_PACKAGES,
    WEB,
    get_logger,
)
from bot_db import (
    PREF_LABELS,
    build_blocks,
    connect,
    cycle_running,
    ensure_schema,
    insert_transaction,
    latest_prices,
    list_assets,
    load_asset_history,
    load_bars_since,
    load_preferences,
    normalize_ticker,
    position_rows,
    recent_transactions,
    save_preferences,
    seed_preferences,
    sell_ready_lots,
    validate_preferences,
    write_status,
    read_status,
)
from bot_logic import money

log = get_logger()
app = Flask(__name__)
app.jinja_loader = ChoiceLoader([
    FileSystemLoader(str(WEB / "templates")),
    FileSystemLoader(str(WEB / "icons")),
])
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=365)
app.config["TEMPLATES_AUTO_RELOAD"] = True

_ready = False


def _load_secret():
    try:
        current = FLASK_SECRET_PATH.read_text(encoding="utf-8").strip()
        if current:
            return current
    except OSError:
        pass
    secret = os.urandom(16).hex()
    try:
        FLASK_SECRET_PATH.write_text(secret, encoding="utf-8")
        os.chmod(FLASK_SECRET_PATH, 0o600)
    except OSError:
        log.warning("segreto di sessione non salvato")
    return secret


app.secret_key = _load_secret()


def _client_ip():
    return request.remote_addr or "sconosciuto"


def _csrf_ok():
    token = session.get("csrf")
    return bool(token) and request.form.get("csrf") == token


def _ensure_csrf():
    if "csrf" not in session:
        session["csrf"] = os.urandom(16).hex()


_AZIONI = {"/aggiorna", "/ciclo", "/acquisto", "/preferenze", "/esci"}


def _safe_next(value):
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return url_for("home")
    path = value.split("?", 1)[0]
    if path.startswith("/login") or path.startswith("/chart/") or path in _AZIONI:
        return url_for("home")
    return value


@app.before_request
def guard():
    ensure_password_hash()
    if request.endpoint == "login":
        if request.method == "POST" and not _csrf_ok():
            abort(400, "Richiesta non valida. Ricarica la pagina.")
        _ensure_csrf()
        return None
    if not session_alive(session):
        if request.path.startswith("/chart/"):
            return Response(status=401)
        if request.method != "GET":
            return redirect(url_for("login"))
        nxt = request.full_path if request.query_string else request.path
        return redirect(url_for("login", next=nxt))
    if request.method == "POST" and not _csrf_ok():
        abort(400, "Richiesta non valida. Ricarica la pagina.")
    _ensure_csrf()
    prepare()


@app.after_request
def harden(response):
    response.headers["Strict-Transport-Security"] = "max-age=15552000"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("auth") and session_alive(session):
        return redirect(_safe_next(request.args.get("next")))
    error = ""
    if request.method == "POST":
        ok, error = authenticate(
            request.form.get("username", ""),
            request.form.get("password", ""),
            _client_ip(),
        )
        if ok:
            destination = _safe_next(request.form.get("next"))
            stamp_session(session)
            return redirect(destination)
    _ensure_csrf()
    coming = request.form.get("next") if request.method == "POST" else request.args.get("next")
    return render_template(
        "login.html",
        error=error,
        csrf=session.get("csrf", ""),
        next=_safe_next(coming),
    )


@app.route("/esci", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


def prepare():
    global _ready
    if _ready:
        return
    conn = connect()
    try:
        ensure_schema(conn)
        seed_preferences(conn)
    finally:
        conn.close()
    _ready = True


@app.template_filter("qty")
def format_qty(value):
    if value is None:
        return "—"
    text = f"{Decimal(str(value)):.8f}".rstrip("0").rstrip(".")
    return text or "0"


@app.template_filter("px")
def format_price(value):
    if value is None:
        return "—"
    return f"{Decimal(str(value)):.4f}".rstrip("0").rstrip(".")


@app.template_filter("pct")
def format_pct(value):
    if value is None:
        return "—"
    return f"{Decimal(str(value)) * 100:.2f} %"


@app.template_filter("when")
def format_when(value):
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    return str(value)


PERIODS = (
    ("1", "1G", "Giorno"),
    ("7", "1S", "Settimana"),
    ("30", "1M", "Mese"),
    ("90", "3M", "Tre mesi"),
    ("180", "6M", "Sei mesi"),
    ("ytd", "YTD", "Da inizio anno"),
)


def _span(value):
    today = datetime.now()
    if value == "ytd":
        start = today.replace(month=1, day=1)
        return "ytd", max(1, (today.date() - start.date()).days)
    if value in ("1", "7", "30", "90", "180"):
        return value, int(value)
    return "180", 180


def _page_status(status, running, now):
    """Il processo compare un attimo dopo il clic: in quel momento è partito, non morto."""
    if status.get("state") != "running" or running:
        return status, running, False
    updated = status.get("updated") or ""
    try:
        stamp = datetime.fromisoformat(updated)
    except ValueError:
        stamp = None
    if stamp is not None and (now - stamp).total_seconds() < 20:
        return status, True, False
    return {
        "state": "error",
        "message": "L'ultimo aggiornamento non è più in esecuzione. Puoi rilanciarlo.",
        "updated": updated,
    }, False, True


def _sync_notice(status, running, now):
    """Il messaggio del ciclo compare all'avvio e alla fine, non a ogni apertura della pagina."""
    stamp = status.get("updated") or ""
    seen = session.get("sync_seen") or ""
    watching = session.get("sync_watch") or ""
    if running:
        session["sync_watch"] = stamp or "running"
        return True
    if watching and stamp and stamp != watching:
        session["sync_watch"] = ""
        session["sync_seen"] = stamp
        return True
    if not stamp or stamp == seen:
        return False
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    if (now - when).total_seconds() > 20:
        session["sync_seen"] = stamp
        return False
    session["sync_seen"] = stamp
    return True


@app.route("/")
def home():
    asset = normalize_ticker(request.args.get("asset", "")) 
    conn = connect()
    try:
        prefs = load_preferences(conn)
        asset = asset or prefs["focus_asset"]
        window_days = max(prefs["history_days"], prefs["return_days"] * 3, 40)
        blocks = build_blocks(load_bars_since(conn, window_days), prefs)
        catalog = security_names()
        tiles = treemap_layout(blocks, catalog)
        positions = position_rows(conn, prefs)
        transactions = recent_transactions(conn)
        assets = list_assets(conn)
        asset_options = [
            {"symbol": symbol, "label": f"{symbol} — {catalog[symbol]}" if catalog.get(symbol) else symbol}
            for symbol in assets
        ]
        status = read_status()
        running = cycle_running()
    finally:
        conn.close()
    now = datetime.now()
    status, running, stale = _page_status(status, running, now)
    sync_notice = _sync_notice(status, running, now)
    if stale:
        write_status(status["state"], status["message"])
    ok = (request.args.get("ok") or "")[:300]
    if ok.startswith("Aggiornamento avviato"):
        ok = ""
    vista = request.args.get("vista")
    if vista not in ("volume", "storico"):
        vista = "volume"
    grafico = request.args.get("grafico")
    if grafico not in ("line", "candle"):
        grafico = prefs["chart_type"]
    period, _days = _span(request.args.get("periodo"))
    return render_template(
        "index.html",
        prefs=prefs,
        labels=PREF_LABELS,
        asset=asset,
        blocks=blocks,
        tiles=tiles,
        positions=positions,
        transactions=transactions,
        assets=assets,
        asset_options=asset_options,
        status=status,
        running=running,
        sync_notice=sync_notice,
        csrf=session.get("csrf", ""),
        ok=ok,
        err=(request.args.get("err") or "")[:300],
        vista=vista,
        grafico=grafico,
        period=period,
        periods=PERIODS,
    )


@app.route("/chart/massa.png")
def chart_blocks():
    conn = connect()
    try:
        prefs = load_preferences(conn)
        window_days = max(prefs["history_days"], prefs["return_days"] * 3, 40)
        blocks = build_blocks(load_bars_since(conn, window_days), prefs)
    finally:
        conn.close()
    return _png(treemap_png(blocks))


@app.route("/chart/storico.png")
def chart_history():
    conn = connect()
    try:
        prefs = load_preferences(conn)
        asset = normalize_ticker(request.args.get("asset", "")) or prefs["focus_asset"]
        _period, days = _span(request.args.get("periodo"))
        series = load_asset_history(conn, asset, days)
        chart_type = request.args.get("grafico")
        if chart_type not in ("line", "candle"):
            chart_type = prefs["chart_type"]
    finally:
        conn.close()
    return _png(history_png(series, asset, chart_type))


@app.route("/preferenze", methods=["POST"])
def save_prefs():
    values, error = validate_preferences(request.form)
    if error:
        return redirect(url_for("home", err=error))
    conn = connect()
    try:
        save_preferences(conn, values)
    finally:
        conn.close()
    log.info("preferenze aggiornate")
    return redirect(url_for("home", ok="Preferenze salvate.", asset=values["focus_asset"]))


@app.route("/acquisto", methods=["POST"])
def buy():
    asset = normalize_ticker(request.form.get("asset", ""))
    if not asset:
        return redirect(url_for("home", err="Titolo non valido."))
    try:
        amount = _required_money(request.form.get("amount"))
        price = _optional_money(request.form.get("price"))
        fees = _optional_money(request.form.get("fees"))
        taxes = _optional_money(request.form.get("taxes"))
    except ValueError:
        return redirect(url_for("home", err="Quantità, prezzo o costi non leggibili.", asset=asset))
    if amount is None or amount <= 0:
        return redirect(url_for("home", err="La quantità deve essere maggiore di zero.", asset=asset))
    conn = connect()
    try:
        prefs = load_preferences(conn)
        if price is None:
            market = latest_prices(conn).get(asset)
            if market:
                price = money(market["price"])
        if price is None or price <= 0:
            return redirect(url_for("home", err="Manca il prezzo di acquisto.", asset=asset))
        notional = amount * price
        if notional > prefs["max_investment"]:
            return redirect(
                url_for(
                    "home",
                    err="L'importo supera l'investimento massimo. Alza la preferenza o riduci la quantità.",
                    asset=asset,
                )
            )
        if fees is None:
            fees = money(notional * prefs["fee_rate"]) or Decimal("0")
        if taxes is None:
            taxes = Decimal("0")
        if taxes < 0 or fees < 0:
            return redirect(url_for("home", err="Commissioni e tasse non possono essere negative.", asset=asset))
        insert_transaction(conn, "buy", asset, amount, price, fees, taxes)
    finally:
        conn.close()
    return redirect(url_for("home", ok=f"Acquisto di {asset} registrato.", asset=asset))


@app.route("/ciclo", methods=["POST"])
def cycle_sells():
    conn = connect()
    try:
        prefs = load_preferences(conn)
        sold = sell_ready_lots(conn, prefs)
    finally:
        conn.close()
    return redirect(url_for("home", ok=f"Controllo vendite concluso. Operazioni registrate: {sold}."))


@app.route("/aggiorna", methods=["POST"])
def refresh():
    if cycle_running():
        return redirect(url_for("home", err="Un aggiornamento è già in corso."))
    write_status("running", "Aggiornamento avviato.")
    env = os.environ.copy()
    env["PYTHONPATH"] = SITE_PACKAGES + os.pathsep + env.get("PYTHONPATH", "")
    env["MPLCONFIGDIR"] = str(MPLCONFIG)
    log_handle = open(LOG_PATH, "a", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, str(WEB / "cycle.py")],
        cwd=str(WEB),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log.info("ciclo avviato")
    return redirect(url_for("home"))


@app.errorhandler(Exception)
def on_error(exc):
    if isinstance(exc, HTTPException):
        return exc
    log.exception("errore pagina")
    return Response("Errore interno. Il dettaglio è nel log del bot.", 500)


def _required_money(value):
    amount = _optional_money(value)
    if amount is None:
        raise ValueError(value)
    return amount


def _optional_money(value):
    text = (value or "").strip().replace(",", ".")
    if not text:
        return None
    amount = money(text)
    if amount is None:
        raise ValueError(text)
    return amount


def _png(buffer):
    response = Response(buffer.getvalue(), mimetype="image/png")
    response.headers["Cache-Control"] = "no-store"
    return response
