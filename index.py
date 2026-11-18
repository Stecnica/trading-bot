"""Trading bot page: volume blocks, history, and sales at the threshold."""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from bot_config import install_import_path

install_import_path()

from markupsafe import Markup
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for
from jinja2 import ChoiceLoader, FileSystemLoader

from bot_auth import authenticate, ensure_password_hash, session_alive, stamp_session
from bot_chart_cache import get_bytes as chart_cache_get, put_bytes as chart_cache_put
from bot_market import constituents, security_names
from bot_config import (
    BACKFILL_LOCK,
    FLASK_SECRET_PATH,
    LOG_PATH,
    MPLCONFIG,
    SITE_PACKAGES,
    WEB,
    get_logger,
    lock_held,
)
from bot_i18n import activate, current, language_for, languages, locales, negotiate, status_text, tr
from bot_db import (
    first_session,
    FONT_CHOICES,
    WEIGHT_CHOICES,
    WEIGHT_IDS,
    accepted_volume_class,
    asset_history_fingerprint,
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
    market_window_fingerprint,
    resolved_theme,
    normalize_ticker,
    position_rows,
    recent_transactions,
    paper_balance,
    bot_buys_on,
    recent_decisions,
    save_preferences,
    seed_preferences,
    sell_open_lot,
    sell_ready_lots,
    symbol_places,
    preference_patch,
    write_status,
    read_status,
)
from bot_logic import money
from bot_massive import history_start, last_completed_session, read_backfill_status
from bot_plan import effective_name, label_parts


def _charts():
    """Lazy import: matplotlib must not load on /login (single-thread WSGI)."""
    from bot_charts import (
        history_hits,
        history_model,
        history_png,
        treemap_grouped,
        treemap_grouped_png,
        treemap_layout,
        treemap_png,
    )

    return {
        "history_hits": history_hits,
        "history_model": history_model,
        "history_png": history_png,
        "treemap_grouped": treemap_grouped,
        "treemap_grouped_png": treemap_grouped_png,
        "treemap_layout": treemap_layout,
        "treemap_png": treemap_png,
    }


def _decide():
    from bot_decide import score_label, scores_for

    return score_label, scores_for

log = get_logger()
app = Flask(__name__)


@app.context_processor
def _inject_language():
    return {
        "t": tr,
        "lang": current(),
        "languages": languages(),
        "language": language_for(current()),
        "period_label": period_label,
    }
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
        log.warning("session secret not saved")
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


_AZIONI = {"/update", "/cycle", "/buy", "/prefs", "/exit", "/volume"}


def _safe_next(value):
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return url_for("home")
    path = value.split("?", 1)[0]
    if path.startswith("/login") or path.startswith("/chart/") or path in _AZIONI:
        return url_for("home")
    return value


@app.before_request
def guard():
    activate(negotiate(request.args.get("lang"), request.cookies.get("lang")))
    ensure_password_hash()
    if request.endpoint == "static":
        return None
    if request.endpoint == "login":
        if request.method == "POST" and not _csrf_ok():
            if session_alive(session):
                nxt = request.form.get("next") or request.args.get("next")
                return redirect(_safe_next(nxt), code=303)
            abort(400, tr("csrf.bad"))
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
        abort(400, tr("csrf.bad"))
    _ensure_csrf()
    prepare()


@app.after_request
def harden(response):
    response.headers["Strict-Transport-Security"] = "max-age=15552000"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; font-src 'self'; script-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-store"
    chosen = request.args.get("lang")
    if chosen in locales():
        response.set_cookie(
            "lang",
            chosen,
            max_age=60 * 60 * 24 * 365,
            secure=True,
            httponly=True,
            samesite="Lax",
        )
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
            return redirect(destination, code=303)
    _ensure_csrf()
    coming = request.form.get("next") if request.method == "POST" else request.args.get("next")
    return render_template(
        "login.html",
        error=error,
        csrf=session.get("csrf", ""),
        next=_safe_next(coming),
    )


@app.route("/exit", methods=["POST"])
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
        log.info("classifications updated: %s names", linked)
    finally:
        conn.close()
    _ready = True


@app.template_filter("glue")
def glue_parts(value):
    """A "a · b · c" line that wraps only between parts. Each separator opens the part after it,
    so nav.js can hide the one that lands at the start of a line and no line ends with "·"."""
    if not value:
        return ""
    parts = str(value).split(" · ")
    first = Markup('<span class="text-nowrap glue-part">{}</span>').format(parts[0])
    rest = (
        Markup('<span class="text-nowrap glue-part"><span class="glue-sep">·&nbsp;</span>{}</span>').format(part)
        for part in parts[1:]
    )
    return Markup('<span class="glue">{}</span>').format(Markup(" ").join([first, *rest]))


@app.template_filter("qty")
def format_qty(value):
    if value is None:
        return "—"
    return f"{Decimal(str(value)):.3f}"


@app.template_filter("qty_full")
def format_qty_full(value):
    if value is None:
        return ""
    return format(Decimal(str(value)).normalize(), "f")


@app.template_filter("px")
def format_price(value):
    if value is None:
        return "—"
    return f"{Decimal(str(value)):.3f}"


@app.template_filter("px2")
def format_price_2(value):
    if value is None:
        return "—"
    return f"{Decimal(str(value)):.2f}"


@app.template_filter("pct")
def format_pct(value):
    if value is None:
        return "—"
    return f"{Decimal(str(value)) * 100:.3f} %"


@app.template_filter("abs_pct")
def format_abs_pct(value):
    if value is None:
        return "—"
    number = (Decimal(str(value)) * 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return f"{abs(number):.3f} %"


@app.template_filter("signed_pct")
def format_signed_pct(value):
    if value is None:
        return "—"
    number = (Decimal(str(value)) * 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    text = f"{abs(number):.3f} %"
    if number > 0:
        return "+" + text
    if number < 0:
        return "−" + text
    return text


@app.template_filter("rate")
def format_rate(value):
    if value is None:
        return "—"
    return f"{Decimal(str(value)) * 100:.3f} %"


@app.template_filter("signed_px")
def format_signed_price(value):
    if value is None:
        return "—"
    number = Decimal(str(value))
    text = f"{abs(number):.3f}"
    if number > 0:
        return "+" + text
    if number < 0:
        return "−" + text
    return text


_CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CNY": "¥",
    "CHF": "CHF",
    "CAD": "C$",
    "AUD": "A$",
    "HKD": "HK$",
    "INR": "₹",
    "KRW": "₩",
}


@app.template_filter("currency")
def format_currency(value):
    """Symbol for an ISO code; rows that already store a symbol pass through."""
    if not value:
        return "—"
    code = str(value).strip()
    return _CURRENCY_SYMBOLS.get(code.upper(), code)


@app.template_filter("when")
def format_when(value):
    if not value:
        return "—"
    if isinstance(value, datetime):
        if value.time() == datetime.min.time():
            return value.strftime("%d/%m/%Y")
        return value.strftime("%d/%m/%Y %H:%M")
    return str(value)


PERIOD_KEYS = ("1", "7", "30", "90", "180", "ytd", "365", "730")
_PERIOD_MARK = {
    "1": ("1", "day"),
    "7": ("1", "week"),
    "30": ("1", "month"),
    "90": ("3", "month"),
    "180": ("6", "month"),
    "ytd": ("", "start"),
    "365": ("1", "year"),
    "730": ("2", "year"),
}


def period_label(key):
    count, part = _PERIOD_MARK[key]
    return f"{count}{tr('period.abbr.' + part)}"


def history_stats(series):
    """Numbers for the same window drawn on the chart."""
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
    """The process appears a moment after the click: at that moment it has started, not died."""
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
        "message": "prices.dead",
        "updated": updated,
    }, False, True


def _sync_notice(status, running, now):
    """The cycle message appears when it starts and when it finishes, not on every page open."""
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
    posted_asset = normalize_ticker(request.args.get("asset", ""))
    conn = connect()
    try:
        prefs = load_preferences(conn)
        asset = prefs["focus_asset"]
        buy_asset = posted_asset or asset
        order = prefs["volume_order"]
        scope = prefs["volume_scope"]
        view = prefs["page_view"]
        # History refresh must not rebuild the volume treemap/scores (~6s+).
        # Volume map JSON is loaded lazily when that tab is opened.
        volume_lazy = view == "history"
        if volume_lazy:
            blocks, tiles, frames = [], [], []
            volume_caption_text = ""
        else:
            prefs, blocks, tiles, volume_caption_text, frames = _volume_board(conn, prefs, order, scope)
        catalog = security_names()
        class_tree = classification_tree(conn)
        positions = position_rows(conn, prefs)
        _attach_score(conn, positions)
        transactions = recent_transactions(conn, prefs)
        armed_ids = {row["lot_id"] for row in positions if row.get("armed")}
        threshold = prefs["profit_threshold"]
        for row in transactions["open"]:
            row["armed"] = row["buy_id"] in armed_ids
        for row in transactions["closed"]:
            ratio = row.get("ratio")
            row["reached"] = ratio is not None and ratio >= threshold
        balance = paper_balance(conn, prefs)
        top_buy = _top_buy(conn, positions, catalog, prefs, balance)
        decisions = recent_decisions(conn)
        history = _history(conn, prefs)
        assets = list_assets(conn)
        period, days = _span(prefs["history_period"])
        if view == "history":
            stats = history_stats(load_asset_history(conn, asset, days))
        else:
            stats = history_stats([])
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
    if ok == tr("prices.started"):
        ok = ""
    status = dict(status)
    status["message"] = status_text(status.get("message"))
    chart = prefs["chart_type"]
    html = render_template(
        "index.html",
        prefs=prefs,
        theme=resolved_theme(prefs["ui_theme"]),
        fonts=FONT_CHOICES,
        weights=WEIGHT_CHOICES,
        asset=asset,
        buy_asset=buy_asset,
        blocks=blocks,
        tiles=tiles,
        positions=positions,
        top_buy=top_buy,
        decisions=decisions,
        massive=label_parts(),
        history=history,
        transactions=transactions,
        paper_balance=balance,
        assets=assets,
        asset_options=asset_options,
        names=catalog,
        status=status,
        running=running,
        sync_notice=sync_notice,
        csrf=session.get("csrf", ""),
        ok=ok,
        err=(request.args.get("err") or "")[:300],
        view=view,
        chart=chart,
        period=period,
        period_keys=PERIOD_KEYS,
        stats=stats,
        class_tree=class_tree,
        volume_caption_text=volume_caption_text,
        order=order,
        scope=scope,
        frames=frames,
        volume_lazy=volume_lazy,
    )
    response = Response(html, mimetype="text/html")
    response.headers["X-Page-Cache"] = "SKIP-VOLUME" if volume_lazy else "VOLUME"
    return response


def _pack_choice():
    order = request.values.get("order")
    return order if order in ("rank", "volume") else "rank"


def _scope_choice():
    scope = request.values.get("scope")
    return scope if scope in ("all", "sector") else "sector"


@app.route("/chart/volume.png")
def chart_blocks():
    conn = connect()
    try:
        prefs = load_preferences(conn)
        order = _pack_choice()
        scope = _scope_choice()
        _prefs, blocks, tiles, _caption, frames = _volume_board(conn, prefs, order, scope)
    finally:
        conn.close()
    if scope == "all":
        charts = _charts()
        return _png(charts["treemap_grouped_png"](frames, tiles))
    return _png(_charts()["treemap_png"](blocks, order))


def volume_caption(prefs, shown, scope="sector"):
    if scope == "all":
        return tr("volume.caption_all", shown=shown)
    chosen = prefs.get("volume_class") or ""
    if chosen.startswith("s:"):
        where = tr("volume.where_named", name=chosen[2:])
    elif chosen.startswith("u:") and "|" in chosen:
        where = tr("volume.where_named", name=chosen.split("|", 1)[1])
    else:
        where = tr("volume.where_archive")
    return tr(
        "volume.caption",
        where=where,
        count=prefs["names"],
        sessions=prefs["return_days"],
        shown=shown,
    )


def _volume_board(conn, prefs, order="rank", scope="sector"):
    """Build volume tiles/frames. Disk-cache the JSON so refresh does not re-score 500 names."""
    prefs = dict(prefs)
    prefs["volume_class"] = accepted_volume_class(conn, prefs.get("volume_class"))
    # History length is not part of this: the ranking sessions are enough.
    # Three calendar days per session cover weekends.
    window_days = max(prefs["return_days"] * 3, 40)
    fp = market_window_fingerprint(conn, window_days)
    parts = (
        current(),
        order,
        scope,
        prefs["return_days"],
        prefs["names"],
        prefs.get("volume_class") or "",
        str(prefs.get("stable_band")),
        str(prefs.get("min_side")),
        prefs.get("volume_divide"),
        prefs.get("volume_scale"),
        fp,
    )
    cached = chart_cache_get("volume", parts)
    if cached is not None:
        try:
            payload = json.loads(cached.decode("utf-8"))
            return prefs, [], payload.get("tiles") or [], payload.get("caption") or "", payload.get("frames") or []
        except (UnicodeDecodeError, ValueError, TypeError):
            pass
    wide = scope == "all"
    allowed = None if wide else class_symbols(conn, prefs["volume_class"])
    blocks = build_blocks(load_bars_since(conn, window_days), prefs, allowed, limit=not wide)
    if wide:
        places = symbol_places(conn)
        for block in blocks:
            sector, group = places.get(block["asset"], ("", ""))
            block["sector"] = sector
            block["group"] = group
    _attach_score(conn, blocks)
    names = security_names()
    charts = _charts()
    if wide:
        frames, tiles = charts["treemap_grouped"](
            blocks,
            names,
            order,
            float(prefs["min_side"]),
            prefs.get("volume_divide") == "on",
            prefs.get("volume_scale") == "on",
        )
    else:
        frames = []
        tiles = charts["treemap_layout"](blocks, names, order)
    caption = volume_caption(prefs, len(tiles), scope)
    chart_cache_put(
        "volume",
        parts,
        json.dumps({"tiles": tiles, "frames": frames, "caption": caption}, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        ),
    )
    return prefs, blocks, tiles, caption, frames


def _top_buy(conn, positions, names, prefs, cash):
    """Next bot candidates from the board the last cycle stored, sized as the cycle sizes a lot,
    with how many of them the cash covers in order and today's bot buys against the daily cap.
    rows is None before any cycle stored a board."""
    from bot_decide import load_buy_board, lot_cost, lot_size, top_buys

    board = load_buy_board()
    held = {row["asset"] for row in positions}
    candidates = top_buys(board, held, prefs, count=len(board or []))
    left = cash
    lots = 0
    for item in candidates:
        _fees, cost = lot_cost(lot_size(prefs, item["price"]), item["price"], prefs["fee_rate"])
        if cost > left:
            break
        left -= cost
        lots += 1
    rows = None
    if board is not None:
        rows = []
        for item in candidates[:5]:
            rows.append(
                {
                    "symbol": item["symbol"],
                    "name": names.get(item["symbol"], ""),
                    "score": item["score"],
                    "price": Decimal(item["price"]),
                    "session": datetime.fromisoformat(item["timestamp"]) if item.get("timestamp") else None,
                    "amount": lot_size(prefs, item["price"]),
                }
            )
    return {
        "rows": rows,
        "cash": cash,
        "lots": lots,
        "cap": prefs["max_buys_per_day"],
        "done": bot_buys_on(conn, datetime.now().date()) if prefs["max_buys_per_day"] else 0,
    }


def _attach_score(conn, rows):
    score_label, scores_for = _decide()
    found = scores_for(conn, [row["asset"] for row in rows])
    for row in rows:
        short, detail = score_label(found.get(row["asset"]))
        row["score"] = short
        row["score_detail"] = detail


@app.route("/volume", methods=["POST"])
def volume_view():
    try:
        sessions = int(request.form.get("return_days", ""))
        count = int(request.form.get("names", ""))
    except (TypeError, ValueError):
        return jsonify(error=tr("volume.bad_values")), 400
    if not 1 <= sessions <= 240:
        return jsonify(error=tr("volume.bad_sessions")), 400
    if not 10 <= count <= 500 or count % 10 != 0:
        return jsonify(error=tr("volume.bad_count")), 400
    conn = connect()
    try:
        raw_group = (request.form.get("volume_class") or "").strip()
        chosen = accepted_volume_class(conn, raw_group)
        if raw_group and not chosen:
            return jsonify(error=tr("volume.bad_group")), 400
        prefs = load_preferences(conn)
        raw_band = request.form.get("stable_band")
        if raw_band is None or not str(raw_band).strip():
            band = prefs["stable_band"]
        else:
            try:
                band = Decimal(str(raw_band).strip().replace(",", "."))
            except (ArithmeticError, ValueError):
                return jsonify(error=tr("prefs.err.band")), 400
            if not (Decimal("0") <= band <= Decimal("0.2")):
                return jsonify(error=tr("prefs.err.band")), 400
        raw_side = request.form.get("min_side")
        if raw_side is None or not str(raw_side).strip():
            side = prefs["min_side"]
        else:
            try:
                side = Decimal(str(raw_side).strip().replace(",", "."))
            except (ArithmeticError, ValueError):
                return jsonify(error=tr("prefs.err.side")), 400
            if not (Decimal("0") <= side <= Decimal("2")):
                return jsonify(error=tr("prefs.err.side")), 400
        stored_band = format(band.normalize(), "f")
        stored_side = format(side.normalize(), "f")
        divide = request.form.get("divide")
        if divide not in ("off", "on"):
            divide = prefs["volume_divide"]
        scale = request.form.get("scale")
        if scale not in ("off", "on"):
            scale = prefs.get("volume_scale", "off")
        prefs["return_days"] = sessions
        prefs["names"] = count
        prefs["volume_class"] = chosen
        prefs["stable_band"] = band
        prefs["min_side"] = side
        prefs["volume_divide"] = divide
        prefs["volume_scale"] = scale
        order = request.form.get("order")
        if order not in ("rank", "volume"):
            order = prefs["volume_order"]
        scope = request.form.get("scope")
        if scope not in ("all", "sector"):
            scope = prefs["volume_scope"]
        prefs["volume_order"] = order
        prefs["volume_scope"] = scope
        save_preferences(
            conn,
            {
                "return_days": str(sessions),
                "names": str(count),
                "volume_class": chosen,
                "stable_band": stored_band,
                "min_side": stored_side,
                "volume_divide": divide,
                "volume_scale": scale,
                "volume_order": order,
                "volume_scope": scope,
            },
        )
        prefs, blocks, tiles, caption, frames = _volume_board(conn, prefs, order, scope)
    finally:
        conn.close()
    return jsonify(
        tiles=tiles,
        frames=frames,
        sessions=sessions,
        count=count,
        group=chosen,
        caption=caption,
        order=order,
        scope=scope,
        band=stored_band,
        side=stored_side,
        divide=divide,
        scale=scale,
        flat=tr("volume.flat", band=format_pct(band)),
    )


@app.route("/chart/stats.json")
def chart_stats():
    conn = connect()
    try:
        prefs = load_preferences(conn)
        asset = normalize_ticker(request.args.get("asset", "")) or prefs["focus_asset"]
        _period, days = _span(request.args.get("period"))
        stats = history_stats(load_asset_history(conn, asset, days))
    finally:
        conn.close()
    return jsonify(stats)


def _history_context():
    """Prefs + fingerprint first; full bars only when a cache miss must rebuild."""
    conn = connect()
    try:
        prefs = load_preferences(conn)
        asset = normalize_ticker(request.args.get("asset", "")) or prefs["focus_asset"]
        _period, days = _span(request.args.get("period"))
        chart_type = request.args.get("chart")
        if chart_type not in ("line", "candle"):
            chart_type = prefs["chart_type"]
        fp = asset_history_fingerprint(conn, asset, days)
        return conn, asset, days, chart_type, fp
    except Exception:
        conn.close()
        raise


def _history_series(conn, asset, days):
    try:
        return load_asset_history(conn, asset, days)
    finally:
        conn.close()


@app.route("/chart/history.png")
def chart_history():
    width = _chart_px("w", 1280, 480, 4096)
    height = _chart_px("h", 720, 280, 2160)
    scale = _chart_px("scale", 100, 80, 120)
    scale = int(round(scale / 5) * 5)
    theme = request.args.get("theme")
    if theme not in ("light", "dark"):
        theme = "light"
    weight = request.args.get("weight")
    if weight not in WEIGHT_IDS:
        weight = "400"
    conn, asset, days, chart_type, fp = _history_context()
    parts = (current(), asset, days, chart_type, width, height, scale, theme, weight, fp)
    cached = chart_cache_get("png", parts)
    if cached is not None:
        conn.close()
        return _png_bytes(cached, hit=True)
    series = _history_series(conn, asset, days)
    buffer = _charts()["history_png"](series, asset, chart_type, width, height, scale, theme, weight)
    payload = buffer.getvalue()
    chart_cache_put("png", parts, payload)
    return _png_bytes(payload, hit=False)


@app.route("/chart/series.json")
def chart_series():
    conn, asset, days, chart_type, fp = _history_context()
    parts = (current(), asset, days, chart_type, fp)
    cached = chart_cache_get("series", parts)
    if cached is not None:
        conn.close()
        response = Response(cached, mimetype="application/json")
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Chart-Cache"] = "HIT"
        return response
    series = _history_series(conn, asset, days)
    payload = json.dumps(
        _charts()["history_model"](series, asset, chart_type),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    chart_cache_put("series", parts, payload)
    response = Response(payload, mimetype="application/json")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Chart-Cache"] = "MISS"
    return response


@app.route("/chart/sessions.json")
def chart_hits():
    conn, asset, days, chart_type, fp = _history_context()
    parts = (current(), asset, days, chart_type, fp)
    cached = chart_cache_get("hits", parts)
    if cached is not None:
        conn.close()
        response = Response(cached, mimetype="application/json")
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Chart-Cache"] = "HIT"
        return response
    series = _history_series(conn, asset, days)
    payload = json.dumps(
        {"hits": _charts()["history_hits"](series, chart_type)},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    chart_cache_put("hits", parts, payload)
    response = Response(payload, mimetype="application/json")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Chart-Cache"] = "MISS"
    return response


@app.route("/prefs", methods=["POST"])
def save_prefs():
    clamped = []
    values, error = preference_patch(request.form, clamped)
    if error:
        # 200 with ok false: the server replaces the body of any 4xx with its own page.
        return jsonify(ok=False, error=error)
    conn = connect()
    try:
        save_preferences(conn, values)
        prefs = load_preferences(conn)
        payload = {"ok": True, "values": values, "clamped": clamped}
        payload["balance"] = format_price(paper_balance(conn, prefs))
        if {"max_investment", "initial_capital", "fee_rate", "lot_sizing", "max_buys_per_day"}.intersection(values):
            rows = position_rows(conn, prefs)
            payload["top_buy_html"] = render_template(
                "_top_buy.html",
                top_buy=_top_buy(conn, rows, security_names(), prefs, paper_balance(conn, prefs)),
                decisions=recent_decisions(conn),
                names=security_names(),
            )
        if {"profit_threshold", "fee_rate", "tax_rate", "max_price_age_hours", "max_hold_days", "trail", "sell_delay_score"}.intersection(values):
            rows = position_rows(conn, prefs)
            _attach_score(conn, rows)
            payload["positions_html"] = render_template(
                "_positions.html",
                positions=rows,
                csrf=session.get("csrf", ""),
                names=security_names(),
            )
            payload["positions_help"] = tr(
                "positions.help",
                threshold=format_pct(prefs["profit_threshold"]),
            ) + tr(
                "positions.help_trail",
                delay=prefs["sell_delay_score"],
                trail=format_pct(prefs["trail"]),
                days=prefs["max_hold_days"],
            )
    finally:
        conn.close()
    log.info("preferences updated")
    return jsonify(payload)


def _buy_back(**extra):
    return redirect(url_for("home", **extra))


@app.route("/buy", methods=["POST"])
def buy():
    asset = normalize_ticker(request.form.get("asset", ""))
    if not asset:
        return _buy_back(err=tr("buy.bad_symbol"))
    try:
        amount = _required_money(request.form.get("amount"))
        price = _optional_money(request.form.get("price"))
        fees = _optional_money(request.form.get("fees"))
        taxes = _optional_money(request.form.get("taxes"))
    except ValueError:
        return _buy_back(err=tr("buy.bad_numbers"), asset=asset)
    if amount is None or amount <= 0:
        return _buy_back(err=tr("buy.bad_amount"), asset=asset)
    if amount > Decimal("1000000000"):
        return _buy_back(err=tr("buy.over_billion"), asset=asset)
    conn = connect()
    try:
        prefs = load_preferences(conn)
        if price is None:
            market = latest_prices(conn).get(asset)
            if market:
                price = money(market["price"])
        if price is None or price <= 0:
            return _buy_back(err=tr("buy.no_price"), asset=asset)
        if price > Decimal("1000000000"):
            return _buy_back(err=tr("buy.over_billion"), asset=asset)
        notional = amount * price
        if notional > prefs["max_investment"]:
            return _buy_back(
                err=tr("buy.over_max"),
                asset=asset,
            )
        if fees is None:
            fee_rate = prefs["fee_rate"]
            fees = money(notional * fee_rate) or Decimal("0")
        else:
            fee_rate = (fees / notional).quantize(Decimal("0.000001")) if notional > 0 else None
        if taxes is None:
            taxes = Decimal("0")
        if taxes < 0 or fees < 0:
            return _buy_back(err=tr("buy.negative"), asset=asset)
        cash_out = money(notional + fees + taxes) or Decimal("0")
        available = paper_balance(conn, prefs)
        if cash_out > available:
            return _buy_back(err=tr("buy.over_balance"), asset=asset)
        insert_transaction(conn, "buy", asset, amount, price, fees, taxes, fee_rate=fee_rate)
    finally:
        conn.close()
    return _buy_back(ok=tr("buy.saved", asset=asset), asset=asset)


@app.route("/sell", methods=["POST"])
def sell():
    """Record one paper sale for an open lot. Same path as bot sells."""
    conn = connect()
    try:
        prefs = load_preferences(conn)
        asset, error = sell_open_lot(conn, prefs, request.form.get("lot"))
    finally:
        conn.close()
    if error:
        return redirect(url_for("home", err=tr(error)))
    return redirect(url_for("home", ok=tr("sell.saved", asset=asset)))


@app.route("/cycle", methods=["POST"])
def cycle_sells():
    conn = connect()
    try:
        prefs = load_preferences(conn)
        sold = sell_ready_lots(conn, prefs)
    finally:
        conn.close()
    return redirect(url_for("home", ok=tr("sells.done", sold=sold)))


def _history(conn, prefs):
    """Stored range, the start the plan reaches, and the fill job: running, its progress, how it ended."""
    plan = effective_name(prefs)
    end = last_completed_session()
    status = read_backfill_status()
    running = lock_held(BACKFILL_LOCK)
    if status.get("state") == "running" and not running:
        status = dict(status, state="stopped", reason="interrupted")
    first = first_session(conn)
    target = history_start(plan, end)
    return {
        "plan": plan,
        "first": first,
        "target": datetime.combine(target, datetime.min.time()),
        "complete": first is not None and first.date() <= target + timedelta(days=7),
        "running": running,
        "status": status,
        "text": _backfill_text(status, running),
    }


@app.route("/backfill", methods=["POST"])
def start_backfill():
    if lock_held(BACKFILL_LOCK):
        return redirect(url_for("home", err=tr("history.busy")))
    env = os.environ.copy()
    env["PYTHONPATH"] = SITE_PACKAGES + os.pathsep + env.get("PYTHONPATH", "")
    env["MPLCONFIGDIR"] = str(MPLCONFIG)
    log_handle = open(LOG_PATH, "a", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, str(WEB / "backfill.py")],
        cwd=str(WEB),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log.info("history fill started")
    return redirect(url_for("home", ok=tr("history.started")))


@app.route("/backfill/status")
def backfill_status():
    status = read_backfill_status()
    running = lock_held(BACKFILL_LOCK)
    return jsonify(running=running, text=_backfill_text(status, running))


def _backfill_text(status, running):
    """The progress line while the fill runs, else how the last one ended."""
    if running:
        return tr("history.running", day=_day_text(status.get("day")), done=status.get("done", 0), total=status.get("total", 0))
    if status.get("state") == "done":
        return tr("history.complete", plan=(status.get("plan") or "").capitalize())
    if status.get("state") in ("stopped", "running"):
        reason = status.get("reason") if status.get("state") == "stopped" else "interrupted"
        return tr("history.stopped", reason=tr("history.reason." + (reason or "error")))
    return ""


def _day_text(value):
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "—"


@app.route("/update", methods=["POST"])
def refresh():
    if cycle_running():
        return redirect(url_for("home", err=tr("prices.busy")))
    write_status("running", "prices.started")
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
    log.info("cycle started")
    return redirect(url_for("home"))


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
    return _png_bytes(buffer.getvalue(), hit=False)


def _png_bytes(payload, hit=False):
    response = Response(payload, mimetype="image/png")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Chart-Cache"] = "HIT" if hit else "MISS"
    return response
