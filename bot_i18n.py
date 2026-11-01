"""Interface strings. English is the default. One menu entry for each file in lang/."""

import json
import re
from contextvars import ContextVar
from pathlib import Path

DEFAULT = "en"
_FOLDER = Path(__file__).resolve().parent / "lang"
_CODE = re.compile(r"^[A-Za-z]{2,8}(?:[_-][A-Za-z0-9]{2,8})*$")
# Same exceptions as country_code_flag_conversion: the flag is not the language code.
_FLAG = {"en": "gb", "cs": "cz", "fa": "pe", "ja": "jp", "ko": "co", "uk": "ua", "zh": "cn"}
_locale = ContextVar("locale", default=DEFAULT)
_catalogs = {}
_languages = ()
_codes = frozenset()
_stamp = None
_STATUS_FIELDS = {
    "prices.queue": ("pending", "chosen"),
    "prices.fetch": ("day", "index", "total"),
    "prices.plan": ("day",),
    "prices.empty": ("day",),
    "prices.unpublished": ("day",),
    "prices.partial": ("day", "count"),
    "prices.fresh": ("sold",),
    "prices.done": ("stored", "sold"),
    "sells.done": ("sold",),
    "reread.queue": ("count",),
    "reread.fetch": ("day", "index", "total"),
    "reread.done": ("stored",),
    "buy.saved": ("asset",),
    "quotes.fetch_recent": ("index", "total", "count"),
    "quotes.fetch_full": ("index", "total", "count"),
    "quotes.skip": ("index",),
    "quotes.partial": ("failed", "stored"),
}


def flag_for(code):
    head = code.lower().replace("_", "-").split("-", 1)[0]
    return _FLAG.get(head, head)


def _load():
    global _languages, _codes, _stamp, _catalogs
    files = sorted(_FOLDER.glob("*.json"))
    stamp = tuple((path.name, path.stat().st_mtime_ns) for path in files)
    if stamp == _stamp:
        return
    catalogs = {}
    for path in files:
        code = path.stem
        if not _CODE.match(code):
            continue
        try:
            catalogs[code] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
    catalogs.setdefault(DEFAULT, {})
    languages = []
    for code, catalog in catalogs.items():
        name = catalog.get("language.name")
        if not isinstance(name, str) or not name.strip():
            name = code
        languages.append({"code": code, "flag": flag_for(code), "name": name.strip()})
    languages.sort(key=lambda item: (item["code"] != DEFAULT, item["name"].casefold(), item["code"]))
    _catalogs = catalogs
    _languages = tuple(languages)
    _codes = frozenset(catalogs)
    _stamp = stamp


def locales():
    _load()
    return _codes


def languages():
    _load()
    return _languages


def activate(code):
    _load()
    if code not in _codes:
        code = DEFAULT
    _locale.set(code)
    return code


def current():
    return _locale.get()


def language_for(code):
    _load()
    for item in _languages:
        if item["code"] == code:
            return item
    for item in _languages:
        if item["code"] == DEFAULT:
            return item
    return {"code": DEFAULT, "flag": "gb", "name": "English"}


def negotiate(query_lang, cookie_lang):
    _load()
    if query_lang in _codes:
        return query_lang
    if cookie_lang in _codes:
        return cookie_lang
    return DEFAULT


def tr(key, **kwargs):
    _load()
    code = current()
    text = _catalogs.get(code, {}).get(key)
    if text is None:
        text = _catalogs[DEFAULT].get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text


def status_text(message):
    if not message:
        return ""
    parts = str(message).split("|")
    key = parts[0]
    fields = _STATUS_FIELDS.get(key)
    if fields is None:
        _load()
        if key in _catalogs[DEFAULT] or key in _catalogs.get(current(), {}):
            return tr(key)
        return str(message)
    values = {name: parts[index + 1] if index + 1 < len(parts) else "" for index, name in enumerate(fields)}
    return tr(key, **values)
