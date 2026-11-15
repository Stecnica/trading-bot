"""Disk-backed cache for page data JSON (volume board, series) and optional PNG."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from bot_config import WEB

CACHE_DIR = WEB / "cache" / "charts"
MAX_BYTES = 80 * 1024 * 1024
TTL_SECONDS = 7 * 24 * 3600


def get_bytes(kind, parts):
    """Return cached bytes or None. kind: volume, series, hits, png, …"""
    path = _path(kind, parts)
    if not path.is_file():
        return None
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return None
    if age > TTL_SECONDS:
        _unlink(path)
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def put_bytes(kind, parts, payload):
    """Store payload; prune old/large files afterward."""
    if not payload:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _path(kind, parts)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    except OSError:
        _unlink(temporary)
        return
    _prune()


def _path(kind, parts):
    raw = "|".join(str(part) for part in (kind, *parts))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    suffix = ".png" if kind == "png" else ".json"
    return CACHE_DIR / f"{digest}{suffix}"


def _unlink(path):
    try:
        path.unlink()
    except OSError:
        pass


def _prune():
    try:
        files = [path for path in CACHE_DIR.iterdir() if path.is_file() and not path.name.endswith(".tmp")]
    except OSError:
        return
    now = time.time()
    kept = []
    for path in files:
        try:
            info = path.stat()
        except OSError:
            continue
        if now - info.st_mtime > TTL_SECONDS:
            _unlink(path)
            continue
        kept.append((info.st_mtime, info.st_size, path))
    total = sum(size for _mtime, size, _path in kept)
    if total <= MAX_BYTES:
        return
    kept.sort()
    for _mtime, size, path in kept:
        if total <= MAX_BYTES:
            break
        _unlink(path)
        total -= size
