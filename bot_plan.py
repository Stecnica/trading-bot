"""What the Massive key can do: end of day only, delayed intraday, or real time.

The plan is detected from the key with at most two light calls a day and kept in
private/massive_plan.json. The preference massive_plan overrides the detection. A refusal
of the intraday call turns it off until the next New York day, so a key that does not
include the snapshot falls back to the end-of-day path without failing every cycle.
"""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from massive import RESTClient
from massive.exceptions import AuthError, BadResponse

from bot_config import PRIVATE, get_logger

log = get_logger()

NEW_YORK = ZoneInfo("America/New_York")
PLAN_PATH = PRIVATE / "massive_plan.json"
PROBE_SYMBOL = "AAPL"
# Behaviour per plan. delay is how late the snapshot is; throttle keeps Basic under 5 calls a minute.
PLANS = {
    "basic": {"intraday": False, "delay": None, "throttle": True},
    "starter": {"intraday": True, "delay": timedelta(minutes=15), "throttle": False},
    "developer": {"intraday": True, "delay": timedelta(minutes=15), "throttle": False},
    "advanced": {"intraday": True, "delay": timedelta(0), "throttle": False},
}
# A snapshot younger than this during the session is real time.
REAL_TIME = timedelta(minutes=5)
# Starter keeps 5 years of bars, Developer 10: a daily bar from 6 years ago tells them apart.
DEEP_DAYS = 6 * 365
# After a probe that could not reach Massive, the next try waits this long.
RETRY = timedelta(hours=1)


def current_plan(prefs, now=None, client=None):
    """The plan this cycle follows: name, intraday, delay, throttle, source (manual or auto),
    the detected plan and when it was checked. Probes only when the stored detection is stale."""
    now = _new_york(now)
    stored = read_detection()
    if _stale(stored, now):
        stored = detect(now, client)
        _write(stored)
    chosen = prefs.get("massive_plan") or "auto"
    name = chosen if chosen in PLANS else stored.get("plan") or "basic"
    if name not in PLANS:
        name = "basic"
    plan = dict(PLANS[name])
    if plan["intraday"] and stored.get("refused") == now.date().isoformat():
        plan["intraday"] = False
    plan.update(
        name=name,
        source="manual" if chosen in PLANS else "auto",
        detected=stored.get("plan"),
        checked=stored.get("checked"),
        refused=stored.get("refused") == now.date().isoformat(),
    )
    return plan


def detect(now=None, client=None):
    """One snapshot call for one name, and for a delayed key one old daily bar."""
    from bot_massive import _api_key, _quiet

    now = _new_york(now)
    stored = read_detection()
    result = {"checked": now.isoformat(timespec="seconds")}
    if stored.get("refused"):
        result["refused"] = stored["refused"]
    try:
        secret = _api_key()
    except RuntimeError as exc:
        log.warning("massive plan not detected: %s", exc)
        return dict(result, plan=None, failed=True)
    client = client or RESTClient(api_key=secret, retries=0, connect_timeout=15, read_timeout=30)
    try:
        snap = client.get_snapshot_ticker("stocks", PROBE_SYMBOL)
    except (AuthError, BadResponse, OSError) as exc:
        kind = refusal_kind(_quiet(exc, secret))
        if kind in ("plan", "rate"):
            log.info("massive plan detected: basic (snapshot %s)", "refused" if kind == "plan" else "rate limited")
            return dict(result, plan="basic", delay_seconds=None, reason=kind)
        log.warning("massive plan not detected: %s", _quiet(exc, secret))
        return dict(result, plan=stored.get("plan"), failed=True)
    updated = getattr(snap, "updated", None) or getattr(getattr(snap, "min", None), "timestamp", None)
    delay = None
    if updated:
        seen = datetime.fromtimestamp(updated / (1e9 if updated > 1e14 else 1e3), NEW_YORK)
        delay = max((now - seen).total_seconds(), 0.0)
    session = _session(now)
    if session and delay is not None:
        real = delay < REAL_TIME.total_seconds()
    else:
        real = stored.get("real_time")
    if real:
        plan = "advanced"
    else:
        plan = "developer" if _deep_history(client, now) else "starter"
    result.update(plan=plan, delay_seconds=None if delay is None else round(delay), real_time=real, measured=bool(session))
    log.info(
        "massive plan detected: %s (snapshot %s s old%s)",
        plan,
        "?" if delay is None else round(delay),
        "" if session else ", market closed: delay not measured",
    )
    return result


def mark_refused(now=None):
    """The intraday call was refused: end of day until the next New York day, logged once."""
    now = _new_york(now)
    stored = read_detection()
    today = now.date().isoformat()
    if stored.get("refused") == today:
        return
    stored["refused"] = today
    stored["checked"] = None
    _write(stored)
    log.warning("massive intraday refused: end of day until tomorrow, plan detected again at the next cycle")


def read_detection():
    try:
        return json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def refusal_kind(text):
    """plan when the key lacks the entitlement, rate when over the limit, auth for a bad key."""
    text = (text or "").lower()
    if any(word in text for word in ("not entitled", "not_authorized", "upgrade your plan", "entitlement", "403")):
        return "plan"
    if any(word in text for word in ("too many", "rate limit", "429", "exceeded the maximum")):
        return "rate"
    if any(word in text for word in ("unknown api key", "unauthorized", "invalid api", "401")):
        return "auth"
    return "other"


def _stale(stored, now):
    checked = stored.get("checked")
    if not checked:
        return True
    try:
        when = datetime.fromisoformat(checked).astimezone(NEW_YORK)
    except ValueError:
        return True
    if stored.get("failed"):
        return now - when >= RETRY
    if when.date() != now.date():
        return True
    return not stored.get("measured") and _session(now) and stored.get("plan") != "basic"


def _deep_history(client, now):
    day = now.date() - timedelta(days=DEEP_DAYS)
    try:
        bars = client.get_aggs(PROBE_SYMBOL, 1, "day", (day - timedelta(days=7)).isoformat(), day.isoformat())
    except (AuthError, BadResponse, OSError):
        return False
    return bool(bars)


def _session(now):
    if now.weekday() >= 5:
        return False
    opened = datetime.combine(now.date(), datetime.min.time().replace(hour=9, minute=30), NEW_YORK)
    closed = datetime.combine(now.date(), datetime.min.time().replace(hour=16), NEW_YORK)
    return opened <= now < closed


def _write(stored):
    PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = PLAN_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(stored, sort_keys=True), encoding="utf-8")
    temporary.replace(PLAN_PATH)


def _new_york(now):
    """A naive moment is server time, like datetime.now()."""
    return (now or datetime.now(NEW_YORK)).astimezone(NEW_YORK)


def effective_name(prefs):
    """The plan a run would follow, from the stored detection only: no call to Massive."""
    chosen = prefs.get("massive_plan") or "auto"
    if chosen in PLANS:
        return chosen
    detected = read_detection().get("plan")
    return detected if detected in PLANS else "basic"


def label_parts():
    """Values the Operations panel shows next to the preference."""
    stored = read_detection()
    checked = stored.get("checked")
    try:
        when = datetime.fromisoformat(checked).astimezone() if checked else None
    except ValueError:
        when = None
    return {
        "detected": stored.get("plan"),
        "delay": stored.get("delay_seconds"),
        "real_time": stored.get("real_time"),
        "checked": when.replace(tzinfo=None) if when else None,
        "refused": stored.get("refused") == _new_york(None).date().isoformat(),
    }

