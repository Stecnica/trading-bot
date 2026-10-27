"""Sedute giornaliere da Massive, una chiamata per tutto il mercato USA."""

import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from massive import RESTClient
from massive.exceptions import AuthError, BadResponse

from bot_config import PRIVATE, get_logger
from bot_db import quantize_volume, upsert_bars
from bot_logic import money
from bot_market import candidate_symbols

log = get_logger()

NEW_YORK = ZoneInfo("America/New_York")
HISTORY_DAYS = 731
PAUSE_SECONDS = 13
FULL_SESSION = 480
ENOUGH = 400
SESSIONS_PATH = PRIVATE / "massive_sessions.txt"
CLOSED_PATH = PRIVATE / "massive_closed_dates.txt"


def update_from_massive(conn, on_progress, max_dates=None):
    """Completa le sedute già chiuse. Il piano gratuito non pubblica il giorno in corso."""
    secret = _api_key()
    wanted = set(candidate_symbols(500))
    end = last_completed_session()
    pending = _pending(conn, wanted, end)
    chosen = pending if max_dates is None else pending[:max_dates]
    if not chosen:
        on_progress("Prezzi già aggiornati.")
        return 0, None
    on_progress(
        f"Massive: {len(pending)} sedute chiuse da completare. "
        f"Questo giro ne chiede {len(chosen)}. La seduta in corso non è inclusa."
    )
    client = RESTClient(api_key=secret, retries=0, connect_timeout=15, read_timeout=90)
    stored = 0
    for index, day in enumerate(chosen):
        if index:
            time.sleep(PAUSE_SECONDS)
        on_progress(f"Scarico la seduta {day.isoformat()}, {index + 1} di {len(chosen)}.")
        try:
            aggs = client.get_grouped_daily_aggs(day.isoformat(), adjusted=False, include_otc=False)
        except (AuthError, BadResponse, OSError) as exc:
            kind = _kind(exc, secret)
            log.warning("massive seduta %s rifiutata: %s", day.isoformat(), _quiet(exc, secret))
            if kind == "auth":
                return stored, "Massive ha rifiutato la chiave. Le barre già scritte restano."
            if kind == "rate":
                return stored, "Massive ha chiesto di rallentare. Le barre già scritte restano."
            return stored, "Massive non ha completato lo scarico. Le barre già scritte restano."
        rows = _rows(aggs, wanted, day)
        if not rows:
            if day < end:
                _remember(CLOSED_PATH, day)
                log.info("massive seduta %s senza barre, segnata chiusa", day.isoformat())
                on_progress(f"La seduta {day.isoformat()} non ha barre. Non la richiedo più.")
            else:
                on_progress(f"La seduta {day.isoformat()} non è ancora pubblicata.")
            continue
        if len(rows) < ENOUGH:
            log.warning("massive seduta %s solo %s simboli dell'elenco", day.isoformat(), len(rows))
            return stored, (
                f"La seduta {day.isoformat()} ha restituito solo {len(rows)} titoli dell'elenco. "
                "Mi fermo prima di segnarla come completa."
            )
        stored += upsert_bars(conn, rows)
        _remember(SESSIONS_PATH, day)
        missing = sorted(wanted - {row["asset_name"] for row in rows})
        log.info(
            "massive seduta %s trovati %s, mancano %s%s",
            day.isoformat(),
            len(rows),
            len(missing),
            ": " + ",".join(missing[:20]) if missing else "",
        )
    log.info("barre scritte o aggiornate: %s", stored)
    return stored, None


def last_completed_session(now=None):
    """Ultimo giorno feriale di New York di cui la chiusura è già passata."""
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


def _pending(conn, wanted, end):
    counts = _counts(conn)
    done = _read_dates(SESSIONS_PATH)
    closed = _read_dates(CLOSED_PATH)
    start = end - timedelta(days=HISTORY_DAYS)
    pending = []
    day = end
    while day >= start:
        if day.weekday() < 5 and day not in done and day not in closed and counts.get(day, 0) < FULL_SESSION:
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
            }
        )
    return rows


def _optional(value):
    amount = money(value)
    if amount is None or amount <= 0:
        return None
    return amount


def _api_key():
    path = PRIVATE / "massive_api.env"
    if not path.exists():
        raise RuntimeError("Manca il file delle chiavi Massive.")
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
        raise RuntimeError("Nel file delle chiavi manca MASSIVE_API_KEY.")
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
    if any(word in text for word in ("unknown api key", "not_authorized", "unauthorized", "invalid api")):
        return "auth"
    if any(word in text for word in ("too many", "rate limit", "429")):
        return "rate"
    return "other"


def _quiet(exc, secret):
    text = str(exc).replace(secret, "")
    return " ".join(text.split())[:300]
