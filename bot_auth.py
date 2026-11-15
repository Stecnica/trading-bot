"""Session login: hashed password, attempt lock. Sign-out is only the exit action."""

import fcntl
import hashlib
import hmac
import json
import os
import time

from bot_config import PRIVATE, UI_PASSWORD_PATH, UI_PASSWORD_QA_PATH, get_logger
from bot_i18n import tr

log = get_logger()

USERNAME = "bot"
QA_USERNAME = "qa_cursor"
MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
ATTEMPTS_PATH = PRIVATE / "login_attempts.json"
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1

# username -> password file (primary + optional temporary QA)
_USER_FILES = {
    USERNAME: UI_PASSWORD_PATH,
    QA_USERNAME: UI_PASSWORD_QA_PATH,
}


def ensure_password_hash():
    """If a password file still holds clear text, replace it with the hash.

    Returns True when the primary `bot` hash is ready. QA file is hashed too
    when present; a missing QA file is fine (that user simply cannot sign in).
    """
    primary_ok = _ensure_file_hash(UI_PASSWORD_PATH)
    if UI_PASSWORD_QA_PATH.exists():
        _ensure_file_hash(UI_PASSWORD_QA_PATH)
    return primary_ok


def authenticate(username, password, ip):
    """Returns (ok, message). The message is empty when sign-in succeeded."""
    if not ensure_password_hash():
        return False, tr("auth.unconfigured")
    locked, wait = _locked(ip)
    if locked:
        minutes = max(1, int((wait + 59) // 60))
        log.info("login locked from %s for %s minutes", ip, minutes)
        return False, tr("auth.lockout", minutes=minutes)
    ok = _password_matches(username, password)
    if not ok:
        fails = _register_failure(ip)
        log.info("login failed from %s, attempt %s", ip, fails)
        return False, tr("auth.bad")
    _clear_failures(ip)
    log.info("login succeeded from %s user=%s", ip, username)
    return True, ""


def session_alive(session):
    if not session.get("auth"):
        return False
    session.permanent = True
    return True


def stamp_session(session):
    now = time.time()
    session.clear()
    session.permanent = True
    session["auth"] = 1
    session["auth_at"] = now
    session["last_seen"] = now
    session["csrf"] = os.urandom(16).hex()


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
    path = _USER_FILES.get(name)
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
