"""Slow score. LightGBM learns the next close from the closes already stored."""

from bot_config import PRIVATE
from bot_db import connect

WINDOW = 20
MODEL_PATH = PRIVATE / "slow_lgb.txt"
SCALE_PATH = PRIVATE / "slow_scale.txt"

_booster = None
_scale = None
_known = {}


def _features(closes):
    """ROC and dispersion at 5, 10 and 20 closes. The same rolling family as Qlib Alpha158, close only."""
    if len(closes) < WINDOW + 1:
        return None
    span = [float(price) for price in closes[-(WINDOW + 1) :]]
    last = span[-1]
    if last <= 0:
        return None
    values = []
    for step in (5, 10, 20):
        base = span[-1 - step]
        if base <= 0:
            return None
        values.append(last / base - 1.0)
    returns = []
    for older, newer in zip(span, span[1:]):
        if older <= 0:
            return None
        returns.append(newer / older - 1.0)
    for step in (5, 10, 20):
        chunk = returns[-step:]
        mean = sum(chunk) / step
        var = sum((item - mean) ** 2 for item in chunk) / step
        values.append(var ** 0.5)
    return values


def train():
    """Fit on every close that still has a next one. The newest close is left for prediction."""
    import lightgbm as lgb

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT asset_name, price
            FROM market_history
            ORDER BY asset_name, timestamp
            """
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    groups = []
    current = None
    bucket = []
    for asset, price in rows:
        if asset != current:
            if len(bucket) > WINDOW + 1:
                groups.append(bucket)
            current = asset
            bucket = []
        bucket.append(float(price))
    if len(bucket) > WINDOW + 1:
        groups.append(bucket)
    features = []
    labels = []
    for closes in groups:
        for index in range(WINDOW, len(closes) - 1):
            vector = _features(closes[: index + 1])
            nxt = closes[index + 1]
            if vector is None or closes[index] <= 0:
                continue
            features.append(vector)
            labels.append(nxt / closes[index] - 1.0)
    if len(features) < 100:
        raise RuntimeError("not enough closes to fit the slow score")
    import numpy as np

    features = np.asarray(features, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.float64)
    mean = sum(labels) / len(labels)
    var = sum((item - mean) ** 2 for item in labels) / len(labels)
    scale = var ** 0.5 or 1.0
    booster = lgb.train(
        {
            "objective": "regression",
            "learning_rate": 0.05,
            "num_leaves": 31,
            "verbose": -1,
            "num_threads": 2,
        },
        lgb.Dataset(features, label=labels),
        num_boost_round=80,
    )
    PRIVATE.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(MODEL_PATH))
    SCALE_PATH.write_text("%.10f\n" % scale, encoding="utf-8")
    global _booster, _scale
    _booster = booster
    _scale = scale
    return len(features)


def _load():
    global _booster, _scale
    if _booster is not None and _scale is not None:
        return _booster is not False
    if not MODEL_PATH.exists() or not SCALE_PATH.exists():
        _booster = False
        _scale = 1.0
        return False
    import lightgbm as lgb

    _booster = lgb.Booster(model_file=str(MODEL_PATH))
    _scale = float(SCALE_PATH.read_text(encoding="utf-8").strip() or "1") or 1.0
    return True


def _squash(predicted):
    import math

    scaled = float(predicted) / (_scale or 1.0)
    if scaled > 20:
        scaled = 20.0
    elif scaled < -20:
        scaled = -20.0
    return math.tanh(scaled)


def _window_key(closes):
    return tuple(float(price) for price in closes[-(WINDOW + 1) :])


def warm(series):
    """Predict every window in one pass. The walk then reads the stored number."""
    if not _load():
        return
    import numpy as np

    keys = []
    vectors = []
    for closes in series:
        if len(closes) < WINDOW + 1:
            continue
        for end in range(WINDOW, len(closes)):
            window = closes[end - WINDOW : end + 1]
            key = tuple(float(price) for price in window)
            if key in _known:
                continue
            vector = _features(window)
            if vector is None:
                _known[key] = None
                continue
            keys.append(key)
            vectors.append(vector)
    if not vectors:
        return
    predicted = _booster.predict(np.asarray(vectors, dtype=np.float64))
    for key, value in zip(keys, predicted):
        _known[key] = _squash(value)


def predict(closes):
    """Tanh of the predicted next return. None when the model or the window is missing."""
    if not _load():
        return None
    if len(closes) < WINDOW + 1:
        return None
    key = _window_key(closes)
    if key in _known:
        return _known[key]
    vector = _features(closes)
    if vector is None:
        _known[key] = None
        return None
    value = _squash(_booster.predict([vector])[0])
    _known[key] = value
    return value
