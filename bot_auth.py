"""Session login: hashed password, attempt lock, view-only accounts. Sign-out is only the exit action."""

import fcntl
import hashlib
import hmac
import json
import os
import time
from datetime import datetime
from pathlib import Path

from bot_config import AUDIT_LOG_PATH, PRIVATE, UI_PASSWORD_LEONARDO_PATH, UI_PASSWORD_PATH, UI_PASSWORD_QA_PATH, get_logger
from bot_i18n import tr

log = get_logger()

USERNAME = "bot"
QA_USERNAME = "qa_cursor"
VIEW_USERNAME = "leonardobot"
MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
ATTEMPTS_PATH = PRIVATE / "login_attempts.json"
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1

# username -> (role, password file). view can open the pages and cannot change them.
_USERS = {
    USERNAME: ("write", UI_PASSWORD_PATH),
    QA_USERNAME: ("write", UI_PASSWORD_QA_PATH),
    VIEW_USERNAME: ("view", UI_PASSWORD_LEONARDO_PATH),
}
# Flask endpoint names that change the book, the preferences, or a running job.
WRITE_ENDPOINTS = frozenset({
    "save_prefs",
    "buy",
    "sell",
    "cycle_sells",
    "start_backfill",
    "refresh",
    "volume_view",
})
JSON_ENDPOINTS = frozenset({"save_prefs", "volume_view"})


def ensure_password_hash():
    """If a password file still holds clear text, replace it with the hash.

    Returns True when the primary `bot` hash is ready. The other files are
    hashed too when present; a missing file means that user cannot sign in.
    """
    primary_ok = _ensure_file_hash(UI_PASSWORD_PATH)
    for _role, path in _USERS.values():
        if path != UI_PASSWORD_PATH and path.exists():
            _ensure_file_hash(path)
    return primary_ok


def role_of(username):
    row = _USERS.get((username or "").strip())
    return row[0] if row else ""


def can_write(session):
    return session.get("role") == "write"


def viewer_refused(role, method, endpoint):
    """True when this request would change something a view account must not touch."""
    return role != "write" and method == "POST" and endpoint in WRITE_ENDPOINTS


def authenticate(username, password, ip):
    """Returns (ok, message). The message is empty when sign-in succeeded."""
    name = (username or "").strip()
    if not ensure_password_hash():
        record(name, ip, "login", "unconfigured")
        return False, tr("auth.unconfigured")
    locked, wait = _locked(ip)
    if locked:
        minutes = max(1, int((wait + 59) // 60))
        log.info("login locked from %s for %s minutes", ip, minutes)
        record(name, ip, "login", "locked")
        return False, tr("auth.lockout", minutes=minutes)
    ok = _password_matches(name, password)
    if not ok:
        fails = _register_failure(ip)
        log.info("login failed from %s, attempt %s", ip, fails)
        record(name, ip, "login", "failed")
        return False, tr("auth.bad")
    _clear_failures(ip)
    log.info("login succeeded from %s user=%s", ip, name)
    record(name, ip, "login", "ok")
    return True, ""


def session_alive(session):
    if not session.get("auth"):
        return False
    if session.get("user") not in _USERS:
        return False
    session.permanent = True
    return True


def stamp_session(session, username):
    name = (username or "").strip()
    now = time.time()
    session.clear()
    session.permanent = True
    session["auth"] = 1
    session["user"] = name
    session["role"] = role_of(name)
    session["auth_at"] = now
    session["last_seen"] = now
    session["csrf"] = os.urandom(16).hex()


def record(user, ip, action, result, detail="", path=None):
    """Append one access or operation. The password is never written."""
    target = Path(path) if path else AUDIT_LOG_PATH
    text = str(detail or "")
    if "password" in text.lower():
        text = ""
    row = {
        "t": datetime.now().astimezone().isoformat(timespec="seconds"),
        "user": str(user or "")[:80],
        "ip": str(ip or ""),
        "action": str(action or ""),
        "result": str(result or ""),
        "detail": text[:300],
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as handle:
            os.chmod(target, 0o600)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        log.warning("access log not written")


def _ensure_file_hash(path):
    try:
        current = path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if not current:
        return False
    if current.startswith("scrypt$"):
        return True
    stored = _format_hash(current)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(stored + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    log.info("sign-in password hashed for %s", path.name)
    return True


def _password_matches(username, password):
    name = username or ""
    row = _USERS.get(name)
    path = row[1] if row else None
    if path is None:
        # Unknown user: still burn a scrypt against primary salt shape if possible,
        # otherwise a dummy, so timing stays closer across usernames.
        stored = _read_hash(UI_PASSWORD_PATH) or {
            "salt": b"\0" * 16,
            "hash": b"\0" * 32,
        }
        candidate = _scrypt(password or "", stored["salt"])
        hmac.compare_digest(candidate, stored["hash"])
        return False
    stored = _read_hash(path)
    if not stored:
        return False
    candidate = _scrypt(password or "", stored["salt"])
    return hmac.compare_digest(candidate, stored["hash"])


def _read_hash(path=None):
    target = path if path is not None else UI_PASSWORD_PATH
    try:
        text = target.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    parts = text.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return None
    try:
        return {"salt": bytes.fromhex(parts[4]), "hash": bytes.fromhex(parts[5])}
    except ValueError:
        return None


def _format_hash(password):
    salt = os.urandom(16)
    digest = _scrypt(password, salt)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def _scrypt(password, salt):
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
    )


def _locked(ip):
    now = time.time()
    with _attempts() as data:
        row = data.get(ip) or {}
        until = float(row.get("locked_until") or 0)
        if until > now:
            return True, until - now
    return False, 0


def _register_failure(ip):
    now = time.time()
    with _attempts() as data:
        row = data.get(ip) or {"fails": 0, "locked_until": 0}
        if float(row.get("locked_until") or 0) > now:
            return int(row.get("fails") or MAX_FAILS)
        fails = int(row.get("fails") or 0) + 1
        row["fails"] = fails
        row["locked_until"] = now + LOCK_SECONDS if fails >= MAX_FAILS else 0
        data[ip] = row
        _prune(data, now)
        return fails


def _clear_failures(ip):
    with _attempts() as data:
        data.pop(ip, None)


def _prune(data, now):
    stale = []
    for ip, row in data.items():
        until = float(row.get("locked_until") or 0)
        if until and until < now - 86400:
            stale.append(ip)
        elif not until and int(row.get("fails") or 0) == 0:
            stale.append(ip)
    for ip in stale:
        data.pop(ip, None)


class _attempts:
    def __enter__(self):
        ATTEMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(ATTEMPTS_PATH, "a+", encoding="utf-8")
        os.chmod(ATTEMPTS_PATH, 0o600)
        fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        self._fh.seek(0)
        raw = self._fh.read()
        self.data = json.loads(raw) if raw.strip() else {}
        return self.data

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._fh.seek(0)
            self._fh.truncate()
            self._fh.write(json.dumps(self.data))
            self._fh.flush()
        fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        self._fh.close()
        return False
