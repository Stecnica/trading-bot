"""Score of one symbol. The next price grades the sensors of the previous reading."""

from collections import deque
import math

TAPE = (1, 5, 15)
HOLD = "hold"
BUY = "buy"
SELL = "sell"

_sentence = None
_rsi_known = {}


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _clamp(value):
    number = _finite(value)
    if number is None:
        return None
    if number > 1:
        return 1.0
    if number < -1:
        return -1.0
    return number


def _sign(value):
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def word_score(text):
    """FinVADER compound score, from the financial word lists. None if the text or the library is absent."""
    if text is None or not str(text).strip():
        return None
    try:
        from finvader import finvader
    except ImportError:
        return None
    raw = finvader(
        str(text),
        use_sentibignomics=True,
        use_henry=True,
        indicator="compound",
    )
    return _clamp(raw)


def sentence_score(text):
    """FinBERT positive probability minus negative probability. None if the text or the library is absent."""
    global _sentence
    if text is None or not str(text).strip():
        return None
    try:
        from transformers import pipeline
    except ImportError:
        return None
    if _sentence is None:
        _sentence = pipeline("sentiment-analysis", model="ProsusAI/finbert", top_k=None)
    rows = _sentence(str(text)[:512])
    if rows and isinstance(rows[0], list):
        rows = rows[0]
    positive = 0.0
    negative = 0.0
    for row in rows or []:
        label = (row.get("label") or "").lower()
        probability = _finite(row.get("score")) or 0.0
        if label == "positive":
            positive = probability
        elif label == "negative":
            negative = probability
    return _clamp(positive - negative)


class SymbolState:
    def __init__(self):
        self.prices = deque(maxlen=40)
        self.last_sensors = {}
        self.agree = {}
        self.seen = {}
        self.wrong_abs = 0.0
        self.wrong_n = 0
        self.score = 0.0

    def deadband(self):
        if self.wrong_n <= 0:
            return 0.0
        return self.wrong_abs / self.wrong_n

    def graded_weights(self):
        weights = {}
        for name, count in self.seen.items():
            if count <= 0:
                continue
            weights[name] = self.agree.get(name, 0.0) / count
        return weights


class Book:
    """One state per symbol. A reading is a price and, when an article names the symbol, its text."""

    def __init__(self):
        self.symbols = {}

    def update(self, symbol, price, text=None, wire=None, extra=None):
        price = _finite(price)
        state = self.symbols.get(symbol)
        if state is None:
            state = SymbolState()
            self.symbols[symbol] = state
        if price is None or price <= 0:
            return self._row(symbol, state, {}, {})

        realized = None
        if state.prices and state.prices[-1]:
            realized = (price - state.prices[-1]) / state.prices[-1]
        mark = _sign(realized) if realized is not None else 0
        if mark != 0 and state.last_sensors:
            if _sign(state.score) != 0 and _sign(state.score) != mark:
                state.wrong_abs += abs(state.score)
                state.wrong_n += 1
            for name, value in state.last_sensors.items():
                state.seen[name] = state.seen.get(name, 0) + 1
                if _sign(value) == mark:
                    state.agree[name] = state.agree.get(name, 0.0) + 1.0

        state.prices.append(price)
        sensors = _sensors(list(state.prices), text)
        marked = _clamp(wire)
        if marked is not None:
            sensors["wire"] = marked
        for name, value in (extra or {}).items():
            number = _clamp(value)
            if number is not None:
                sensors[str(name)] = number
        weights = _mix(sensors, state.graded_weights())
        score = 0.0
        for name, value in sensors.items():
            score += weights[name] * value
        state.score = score
        state.last_sensors = dict(sensors)
        return self._row(symbol, state, sensors, weights)

    def _row(self, symbol, state, sensors, weights):
        score = state.score
        band = state.deadband()
        side = HOLD
        if score > band:
            side = BUY
        elif score < -band:
            side = SELL
        return {
            "symbol": symbol,
            "score": score,
            "side": side,
            "deadband": band,
            "sensors": sensors,
            "weights": weights,
        }


def _sensors(prices, text):
    sensors = {}
    last = prices[-1]
    for window in TAPE:
        if len(prices) <= window:
            continue
        base = prices[-1 - window]
        if not base:
            continue
        change = (last - base) / base
        sensors["tape_%s" % window] = _clamp(math.tanh(change * 10))
    rsi = _rsi(prices)
    if rsi is not None:
        sensors["rsi"] = rsi
    slow = _slow(prices)
    if slow is not None:
        sensors["slow"] = slow
    words = word_score(text)
    if words is not None:
        sensors["words"] = words
    sentence = sentence_score(text)
    if sentence is not None:
        sensors["sentence"] = sentence
    return sensors


def warm_rsi(series):
    """One RSI pass per name. Each step of the walk then reads the stored number."""
    try:
        import pandas as pd
        from ta.momentum import RSIIndicator
    except ImportError:
        return
    for closes in series:
        vals = []
        usable = True
        for price in closes:
            number = _finite(price)
            if number is None or number <= 0:
                usable = False
                break
            vals.append(number)
        if not usable or len(vals) < 15:
            continue
        rsi = RSIIndicator(close=pd.Series(vals, dtype="float64"), window=14).rsi()
        for index in range(14, len(vals)):
            number = _finite(rsi.iloc[index])
            mapped = None if number is None else _clamp((number - 50.0) / 50.0)
            _rsi_known[tuple(vals[: index + 1])] = mapped


def _rsi(prices):
    """14-session RSI from the ta library, mapped onto -1..1. None until the window is full."""
    if len(prices) < 15:
        return None
    key = tuple(prices)
    if key in _rsi_known:
        return _rsi_known[key]
    try:
        import pandas as pd
        from ta.momentum import RSIIndicator
    except ImportError:
        return None
    value = RSIIndicator(close=pd.Series(prices, dtype="float64"), window=14).rsi().iloc[-1]
    number = _finite(value)
    mapped = None if number is None else _clamp((number - 50.0) / 50.0)
    _rsi_known[key] = mapped
    return mapped


def _slow(prices):
    """LightGBM score of the next close, mapped onto -1..1. None until the model and the window exist."""
    if len(prices) < 21:
        return None
    try:
        from bot_slow import predict
    except ImportError:
        return None
    return _clamp(predict(prices))


def _mix(sensors, graded):
    if not sensors:
        return {}
    parts = {}
    for name in sensors:
        if name in graded and graded[name] > 0:
            parts[name] = graded[name]
        else:
            parts[name] = 1.0
    total = sum(parts.values())
    return {name: parts[name] / total for name in parts}
