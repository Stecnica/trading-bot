"""Pagina del trading bot: blocchi di volume, storico e vendite sulla soglia."""

import os
import subprocess
import sys
from datetime import datetime, timedelta
from decimal import Decimal

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.exceptions import HTTPException

SITE = "/var/www/clients/client0/web5/home/default_botmanager/.local/lib/python3.10/site-packages"
if SITE not in sys.path:
    sys.path.insert(0, SITE)

from bot_auth import authenticate, ensure_password_hash, session_alive, stamp_session
from bot_charts import history_hits, history_model, history_png, treemap_layout, treemap_png
from bot_market import constituents, security_names
from bot_config import (
    FLASK_SECRET_PATH,
    LOG_PATH,
    MPLCONFIG,
    SITE_PACKAGES,
    WEB,
    get_logger,
)
from bot_db import (
    FONT_CHOICES,
    PREF_LABELS,
    WEIGHT_CHOICES,
    WEIGHT_IDS,
    accepted_volume_class,
    build_blocks,
    class_symbols,
    classification_tree,
    connect,
    cycle_running,
    ensure_schema,
    save_classifications,
    insert_transaction,
    latest_prices,
    list_assets,
    load_asset_history,
    load_bars_since,
    load_preferences,
    resolved_theme,
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


_AZIONI = {"/aggiorna", "/ciclo", "/acquisto", "/preferenze", "/esci", "/volume"}


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
    if request.endpoint == "static":
        return None
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
        linked = save_classifications(conn, ((symbol, sector, sub) for symbol, _name, sector, sub in constituents()))
        log.info("classificazioni aggiornate: %s titoli", linked)
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
    ("365", "1A", "Un anno"),
    ("730", "2A", "Due anni"),
)


def history_stats(series):
    """Numeri della stessa finestra disegnata nel grafico."""
    empty = {"change": "—", "last": "—", "low": "—", "high": "—", "sessions": "0", "tone": "flat"}
    if not series:
        return empty
    closes = [Decimal(str(row["price"])) for row in series]
    first, last = closes[0], closes[-1]
    change = (last - first) / first if first else None
    lows, highs = [], []
    for row in series:
        low = row.get("low_price")
        high = row.get("high_price")
        lows.append(Decimal(str(low if low is not None else row["price"])))
        highs.append(Decimal(str(high if high is not None else row["price"])))
    tone = "flat"
    text = "—"
    if change is not None:
        text = format_pct(change)
        if change > 0:
            tone = "success"
            text = "+" + text
        elif change < 0:
            tone = "danger"
    return {
        "change": text,
        "last": format_price(last),
        "low": format_price(min(lows)),
        "high": format_price(max(highs)),
        "sessions": str(len(series)),
        "tone": tone,
    }


def _span(value):
    today = datetime.now()
    if value == "ytd":
        start = today.replace(month=1, day=1)
        return "ytd", max(1, (today.date() - start.date()).days)
    if value in ("1", "7", "30", "90", "180", "365", "730"):
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
        prefs, blocks, tiles, volume_caption_text = _volume_board(conn, prefs)
        catalog = security_names()
        class_tree = classification_tree(conn)
        positions = position_rows(conn, prefs)
        transactions = recent_transactions(conn)
        assets = list_assets(conn)
        period, days = _span(request.args.get("periodo"))
        stats = history_stats(load_asset_history(conn, asset, days))
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
    return render_template(
        "index.html",
        prefs=prefs,
        theme=resolved_theme(prefs["ui_theme"]),
        fonts=FONT_CHOICES,
        weights=WEIGHT_CHOICES,
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
        stats=stats,
        class_tree=class_tree,
        volume_caption_text=volume_caption_text,
    )


@app.route("/chart/massa.png")
def chart_blocks():
    conn = connect()
    try:
        prefs = load_preferences(conn)
        _prefs, blocks, _tiles, _caption = _volume_board(conn, prefs)
    finally:
        conn.close()
    return _png(treemap_png(blocks))


def volume_caption(prefs, shown):
    chosen = prefs.get("volume_class") or ""
    if chosen.startswith("s:"):
        where = "di " + chosen[2:]
    elif chosen.startswith("u:") and "|" in chosen:
        where = "di " + chosen.split("|", 1)[1]
    else:
        where = "in archivio"
    return (
        f"Tra i titoli {where}, i {prefs['universe_size']} con il rendimento più alto "
        f"sulle ultime {prefs['return_days']} sedute. In grafico: {shown}. La dimensione è il volume."
    )


def _volume_board(conn, prefs):
    prefs = dict(prefs)
    prefs["volume_class"] = accepted_volume_class(conn, prefs.get("volume_class"))
    # I giorni dello storico non c'entrano: bastano le sedute della classifica.
    # Tre giorni di calendario per seduta coprono i fine settimana.
    window_days = max(prefs["return_days"] * 3, 40)
    allowed = class_symbols(conn, prefs["volume_class"])
    blocks = build_blocks(load_bars_since(conn, window_days), prefs, allowed)
    tiles = treemap_layout(blocks, security_names())
    return prefs, blocks, tiles, volume_caption(prefs, len(blocks))


@app.route("/volume", methods=["POST"])
def volume_view():
    try:
        sessions = int(request.form.get("return_days", ""))
        count = int(request.form.get("universe_size", ""))
    except (TypeError, ValueError):
        return jsonify(error="Valori non leggibili."), 400
    if not 1 <= sessions <= 120:
        return jsonify(error="Le sedute vanno da 1 a 120."), 400
    if not 10 <= count <= 500 or count % 10 != 0:
        return jsonify(error="I titoli vanno da 10 a 500, a passi di 10."), 400
    conn = connect()
    try:
        raw_group = (request.form.get("volume_class") or "").strip()
        chosen = accepted_volume_class(conn, raw_group)
        if raw_group and not chosen:
            return jsonify(error="Gruppo sconosciuto."), 400
        prefs = load_preferences(conn)
        prefs["return_days"] = sessions
        prefs["universe_size"] = count
        prefs["volume_class"] = chosen
        save_preferences(
            conn,
            {
                "return_days": str(sessions),
                "universe_size": str(count),
                "volume_class": chosen,
            },
        )
        prefs, blocks, tiles, caption = _volume_board(conn, prefs)
    finally:
        conn.close()
    return jsonify(tiles=tiles, sessions=sessions, count=count, group=chosen, caption=caption)


@app.route("/chart/statistiche.json")
def chart_stats():
    conn = connect()
    try:
        prefs = load_preferences(conn)
        asset = normalize_ticker(request.args.get("asset", "")) or prefs["focus_asset"]
        _period, days = _span(request.args.get("periodo"))
        stats = history_stats(load_asset_history(conn, asset, days))
    finally:
        conn.close()
    return jsonify(stats)


def _history_query():
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
    return asset, series, chart_type


@app.route("/chart/storico.png")
def chart_history():
    asset, series, chart_type = _history_query()
    width = _chart_px("w", 1280, 480, 4096)
    height = _chart_px("h", 720, 280, 2160)
    scale = _chart_px("scala", 100, 80, 120)
    scale = int(round(scale / 5) * 5)
    theme = request.args.get("tema")
    if theme not in ("light", "dark"):
        theme = "light"
    weight = request.args.get("peso")
    if weight not in WEIGHT_IDS:
        weight = "400"
    return _png(history_png(series, asset, chart_type, width, height, scale, theme, weight))


@app.route("/chart/serie.json")
def chart_series():
    asset, series, chart_type = _history_query()
    response = jsonify(history_model(series, asset, chart_type))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/chart/sedute.json")
def chart_hits():
    _asset, series, chart_type = _history_query()
    response = jsonify(hits=history_hits(series, chart_type))
    response.headers["Cache-Control"] = "no-store"
    return response


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


def _buy_back(**extra):
    extra["pannello"] = "acquisto"
    return redirect(url_for("home", **extra))


@app.route("/acquisto", methods=["POST"])
def buy():
    asset = normalize_ticker(request.form.get("asset", ""))
    if not asset:
        return _buy_back(err="Titolo non valido.")
    try:
        amount = _required_money(request.form.get("amount"))
        price = _optional_money(request.form.get("price"))
        fees = _optional_money(request.form.get("fees"))
        taxes = _optional_money(request.form.get("taxes"))
    except ValueError:
        return _buy_back(err="Quantità, prezzo o costi non leggibili.", asset=asset)
    if amount is None or amount <= 0:
        return _buy_back(err="La quantità deve essere maggiore di zero.", asset=asset)
    conn = connect()
    try:
        prefs = load_preferences(conn)
        if price is None:
            market = latest_prices(conn).get(asset)
            if market:
                price = money(market["price"])
        if price is None or price <= 0:
            return _buy_back(err="Manca il prezzo di acquisto.", asset=asset)
        notional = amount * price
        if notional > prefs["max_investment"]:
            return _buy_back(
                err="L'importo supera l'investimento massimo. Alza la preferenza o riduci la quantità.",
                asset=asset,
            )
        if fees is None:
            fees = money(notional * prefs["fee_rate"]) or Decimal("0")
        if taxes is None:
            taxes = Decimal("0")
        if taxes < 0 or fees < 0:
            return _buy_back(err="Commissioni e tasse non possono essere negative.", asset=asset)
        insert_transaction(conn, "buy", asset, amount, price, fees, taxes)
    finally:
        conn.close()
    return _buy_back(ok=f"Acquisto di {asset} registrato.", asset=asset)


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


def _chart_px(name, default, low, high):
    try:
        value = int(request.args.get(name, ""))
    except (TypeError, ValueError):
        return default
    return max(low, min(value, high))


def _png(buffer):
    response = Response(buffer.getvalue(), mimetype="image/png")
    response.headers["Cache-Control"] = "no-store"
    return response
