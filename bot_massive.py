"""Daily sessions from Massive, one call for the whole US market, and during the session
one snapshot call for the delayed price of every name."""

import time as clock
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from massive import RESTClient
from massive.exceptions import AuthError, BadResponse

from bot_config import PRIVATE, get_logger
from bot_db import drop_live_bars, live_days, quantize_volume, upsert_bars
from bot_logic import money
from bot_market import candidate_symbols

log = get_logger()

NEW_YORK = ZoneInfo("America/New_York")
HISTORY_DAYS = 731
# Stocks Basic allows 5 calls a minute; the paid plans have no cap.
PAUSE_SECONDS = 13
FULL_SESSION = 480
ENOUGH = 400
SESSIONS_PATH = PRIVATE / "massive_sessions.txt"
CLOSED_PATH = PRIVATE / "massive_closed_dates.txt"
OPEN = time(9, 30)
CLOSE = time(16, 0)


def update_from_massive(conn, on_progress, max_dates=None, throttle=True):
    """Fill sessions that are already closed, and replace the provisional bars of a closed day.
    throttle waits PAUSE_SECONDS between calls, for the Basic cap."""
    secret = _api_key()
    wanted = set(candidate_symbols(500))
    end = last_completed_session()
    pending = _pending(conn, wanted, end)
    chosen = pending if max_dates is None else pending[:max_dates]
    if not chosen:
        on_progress("prices.current")
        return 0, None
    on_progress(f"prices.queue|{len(pending)}|{len(chosen)}")
    client = RESTClient(api_key=secret, retries=0, connect_timeout=15, read_timeout=90)
    stored = 0
    for index, day in enumerate(chosen):
        if throttle and index:
            clock.sleep(PAUSE_SECONDS)
        on_progress(f"prices.fetch|{day.isoformat()}|{index + 1}|{len(chosen)}")
        try:
            aggs = client.get_grouped_daily_aggs(day.isoformat(), adjusted=False, include_otc=False)
        except (AuthError, BadResponse, OSError) as exc:
            kind = _kind(exc, secret)
            log.warning("massive session %s rejected: %s", day.isoformat(), _quiet(exc, secret))
            if kind == "plan" and day < end:
                _remember(CLOSED_PATH, day)
                log.info("massive session %s outside the plan, marked closed", day.isoformat())
                on_progress(f"prices.plan|{day.isoformat()}")
                continue
            if kind == "auth":
                return stored, "prices.auth"
            if kind == "rate":
                return stored, "prices.rate"
            return stored, "prices.incomplete"
        rows = _rows(aggs, wanted, day)
        if not rows:
            if day < end:
                _remember(CLOSED_PATH, day)
                log.info("massive session %s has no bars, marked closed", day.isoformat())
                on_progress(f"prices.empty|{day.isoformat()}")
            else:
                on_progress(f"prices.unpublished|{day.isoformat()}")
            continue
        if len(rows) < ENOUGH:
            log.warning("massive session %s returned only %s symbols from the list", day.isoformat(), len(rows))
            return stored, f"prices.partial|{day.isoformat()}|{len(rows)}"
        stored += upsert_bars(conn, rows)
        dropped = drop_live_bars(conn, day)
        if dropped:
            log.info("massive session %s: %s provisional bars without a daily bar removed", day.isoformat(), dropped)
        _remember(SESSIONS_PATH, day)
        missing = sorted(wanted - {row["asset_name"] for row in rows})
        log.info(
            "massive session %s found %s, missing %s%s",
            day.isoformat(),
            len(rows),
            len(missing),
            ": " + ",".join(missing[:20]) if missing else "",
        )
    log.info("bars written or updated: %s", stored)
    return stored, None


def reread_stored_sessions(conn, on_progress, throttle=True):
    """Reread sessions already in the archive and fill the response fields that were discarded."""
    secret = _api_key()
    wanted = set(candidate_symbols(500))
    end = last_completed_session()
    chosen = _unfilled(conn, end)
    if not chosen:
        on_progress("reread.ready")
        return 0, None
    on_progress(f"reread.queue|{len(chosen)}")
    client = RESTClient(api_key=secret, retries=0, connect_timeout=15, read_timeout=90)
    stored = 0
    for index, day in enumerate(chosen):
        if throttle and index:
            clock.sleep(PAUSE_SECONDS)
        on_progress(f"reread.fetch|{day.isoformat()}|{index + 1}|{len(chosen)}")
        try:
            aggs = client.get_grouped_daily_aggs(day.isoformat(), adjusted=False, include_otc=False)
        except (AuthError, BadResponse, OSError) as exc:
            kind = _kind(exc, secret)
            log.warning("massive reread %s rejected: %s", day.isoformat(), _quiet(exc, secret))
            if kind == "plan":
                _remember(CLOSED_PATH, day)
                on_progress(f"prices.plan|{day.isoformat()}")
                continue
            if kind == "auth":
                return stored, "prices.auth"
            if kind == "rate":
                return stored, "prices.rate"
            return stored, "prices.incomplete"
        rows = _rows(aggs, wanted, day)
        if len(rows) < ENOUGH:
            log.warning("massive reread %s returned only %s symbols from the list", day.isoformat(), len(rows))
            return stored, (
                f"prices.partial|{day.isoformat()}|{len(rows)}"
            )
        stored += upsert_bars(conn, rows)
        log.info("massive reread %s updated %s", day.isoformat(), len(rows))
    log.info("reread finished, bars %s", stored)
    return stored, None


def _unfilled(conn, end):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DATE(timestamp), COUNT(*), SUM(vwap IS NOT NULL)
        FROM market_history
        WHERE asset_name <> 'test'
        GROUP BY DATE(timestamp)
        """
    )
    closed = _read_dates(CLOSED_PATH)
    found = []
    for raw, count, filled in cur.fetchall():
        day = _as_date(raw)
        if day > end or day in closed:
            continue
        if count < ENOUGH or (filled or 0) < ENOUGH:
            found.append(day)
    cur.close()
    return sorted(found, reverse=True)


def last_completed_session(now=None):
    """Last New York weekday whose close has already passed."""
    moment = now or datetime.now(NEW_YORK)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=NEW_YORK)
    else:
        moment = moment.astimezone(NEW_YORK)
    day = moment.date()
    if moment.hour < 16:
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def in_session(delay, now=None):
    """True from the 9:30 open until a feed that is delay late has shown the 16:00 close,
    on a New York weekday. Holidays pass here; live_rows then finds no price from today."""
    moment = _new_york(now)
    if moment.weekday() >= 5:
        return False
    opened = datetime.combine(moment.date(), OPEN, NEW_YORK)
    closed = datetime.combine(moment.date(), CLOSE, NEW_YORK) + delay
    return opened <= moment < closed


def update_live(conn, on_progress, now=None):
    """One snapshot call during the session: the delayed price of each name becomes today's
    provisional bar (live = 1), dated at the session like a daily bar, with the price moment
    in bar_ms. The daily bar replaces it once the session is published.

    Returns (stored, warning, refusal). refusal is plan or rate when Massive turned the
    call down, else None. Nothing is written when fewer than ENOUGH names have a price
    from today's session: the cycle then keeps the bars it already has.
    """
    from bot_plan import refusal_kind

    secret = _api_key()
    wanted = set(candidate_symbols(500))
    client = RESTClient(api_key=secret, retries=0, connect_timeout=15, read_timeout=90)
    on_progress("prices.live")
    try:
        snapshots = client.get_snapshot_all("stocks", include_otc=False)
    except (AuthError, BadResponse, OSError) as exc:
        kind = refusal_kind(_quiet(exc, secret))
        log.warning("massive snapshot rejected: %s", _quiet(exc, secret))
        if kind in ("plan", "rate"):
            return 0, None, kind
        if kind == "auth":
            return 0, "prices.auth", None
        return 0, "prices.incomplete", None
    rows = live_rows(snapshots, wanted, now)
    if len(rows) < ENOUGH:
        log.info("massive snapshot: only %s names priced in today's session, daily bars kept", len(rows))
        return 0, None, None
    stored = upsert_bars(conn, rows)
    newest = max(row["bar_ms"] for row in rows)
    log.info(
        "massive snapshot: %s names, newest price %s",
        len(rows),
        datetime.fromtimestamp(newest / 1000).isoformat(sep=" ", timespec="seconds"),
    )
    return stored, None, None


def live_rows(snapshots, wanted, now=None):
    """Bars from snapshot entries whose last update falls inside today's regular session.
    Price is the day's running close; bar_ms is the moment of that update."""
    moment = _new_york(now)
    opened = datetime.combine(moment.date(), OPEN, NEW_YORK)
    closed = datetime.combine(moment.date(), CLOSE, NEW_YORK) + timedelta(minutes=1)
    when = datetime(moment.year, moment.month, moment.day)
    rows = []
    seen = set()
    for snap in snapshots or []:
        symbol = (snap.ticker or "").upper().replace(".", "-")
        day = snap.day
        if symbol not in wanted or symbol in seen or day is None or not snap.updated:
            continue
        updated = datetime.fromtimestamp(snap.updated / 1e9, NEW_YORK)
        if not opened <= updated < closed:
            continue
        close = money(day.close)
        if close is None or close <= 0:
            continue
        seen.add(symbol)
        rows.append(
            {
                "asset_name": symbol,
                "timestamp": when,
                "price": close,
                "open_price": _optional(day.open),
                "high_price": _optional(day.high),
                "low_price": _optional(day.low),
                "volume": quantize_volume(day.volume),
                "vwap": _optional(day.vwap),
                "trade_count": None,
                "bar_ms": int(snap.updated // 1_000_000),
                "otc": 0,
                "live": 1,
            }
        )
    return rows


def _new_york(now):
    """A naive moment is server time, like datetime.now()."""
    return (now or datetime.now(NEW_YORK)).astimezone(NEW_YORK)


def _pending(conn, wanted, end):
    counts = _counts(conn)
    done = _read_dates(SESSIONS_PATH)
    closed = _read_dates(CLOSED_PATH)
    provisional = live_days(conn)
    start = end - timedelta(days=HISTORY_DAYS)
    pending = []
    day = end
    while day >= start:
        if day.weekday() >= 5 or day in closed:
            day -= timedelta(days=1)
            continue
        if day in provisional or (day not in done and counts.get(day, 0) < FULL_SESSION):
            pending.append(day)
        day -= timedelta(days=1)
    return pending


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    return value


def _counts(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DATE(timestamp), COUNT(DISTINCT asset_name)
        FROM market_history
        WHERE asset_name <> 'test'
        GROUP BY DATE(timestamp)
        """
    )
    found = {}
    for raw, count in cur.fetchall():
        found[_as_date(raw)] = count
    cur.close()
    return found


def _rows(aggs, wanted, day):
    when = datetime(day.year, day.month, day.day)
    rows = []
    seen = set()
    for agg in aggs or []:
        symbol = (agg.ticker or "").upper().replace(".", "-")
        if symbol not in wanted or symbol in seen:
            continue
        close = money(agg.close)
        if close is None or close <= 0:
            continue
        seen.add(symbol)
        rows.append(
            {
                "asset_name": symbol,
                "timestamp": when,
                "price": close,
                "open_price": _optional(agg.open),
                "high_price": _optional(agg.high),
                "low_price": _optional(agg.low),
                "volume": quantize_volume(agg.volume),
                "vwap": _optional(agg.vwap),
                "trade_count": _count(agg.transactions),
                "bar_ms": _millis(agg.timestamp),
                "otc": _flag(agg.otc),
            }
        )
    return rows


def _optional(value):
    amount = money(value)
    if amount is None or amount <= 0:
        return None
    return amount


def _count(value):
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _millis(value):
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _flag(value):
    if value is None:
        return None
    return 1 if value else 0


def _api_key():
    path = PRIVATE / "massive_api.env"
    if not path.exists():
        raise RuntimeError("The Massive key file is missing.")
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text.startswith("export "):
            text = text[len("export ") :].strip()
        key, sep, value = text.partition("=")
        if sep:
            found[key.strip()] = value.strip().strip('"').strip("'")
    secret = found.get("MASSIVE_API_KEY") or ""
    if not secret:
        raise RuntimeError("MASSIVE_API_KEY is missing from the key file.")
    return secret


def _read_dates(path):
    if not path.exists():
        return set()
    found = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            found.add(date.fromisoformat(text))
        except ValueError:
            continue
    return found


def _remember(path, day):
    if day in _read_dates(path):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(day.isoformat() + "\n")


def _kind(exc, secret):
    text = _quiet(exc, secret).lower()
    if "historical entitlement" in text or "past historical" in text:
        return "plan"
    if any(word in text for word in ("unknown api key", "not_authorized", "unauthorized", "invalid api")):
        return "auth"
    if any(word in text for word in ("too many", "rate limit", "429")):
        return "rate"
    return "other"


def _quiet(exc, secret):
    text = str(exc).replace(secret, "")
    return " ".join(text.split())[:300]
