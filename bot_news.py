"""Title and description, or an 8-K, onto the score. No orders are written."""

from datetime import datetime

from massive import RESTClient

from bot_config import UNIVERSE_CACHE
from bot_db import connect
from bot_massive import _api_key
from bot_score import Book, word_score

WIRE = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}


def article_text(title, description):
    parts = []
    for value in (title, description):
        if value is None:
            continue
        text = str(value).strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def wire_score(label):
    if label is None:
        return None
    return WIRE.get(str(label).strip().lower())


def _client():
    return RESTClient(api_key=_api_key(), retries=0, connect_timeout=15, read_timeout=90)


def fetch_articles(limit=20):
    """One page of recent articles. The body stays at the publisher."""
    found = []
    for item in _client().list_ticker_news(limit=limit, sort="published_utc", order="desc"):
        found.append(item)
        if len(found) >= limit:
            break
    return found


def fetch_filing(ticker):
    """The latest 8-K plain text for one symbol. None when the plan returns nothing."""
    for item in _client().list_stocks_filings_8k_text(ticker=ticker, limit=1):
        text = (item.items_text or "").strip()
        if not text:
            return None
        return {
            "ticker": item.ticker or ticker,
            "filed": item.filing_date,
            "text": text,
        }
    return None


def listed_symbols():
    if not UNIVERSE_CACHE.exists():
        return set()
    symbols = set()
    for line in UNIVERSE_CACHE.read_text(encoding="utf-8").splitlines():
        text = line.strip().upper().replace(".", "-")
        if text and text[0].isalpha():
            symbols.add(text)
    return symbols


def recent_closes(conn, symbol, count=16):
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT timestamp, price
        FROM market_history
        WHERE asset_name = %s
        ORDER BY timestamp DESC
        LIMIT %s
        """,
        (symbol, count),
    )
    rows = list(cur.fetchall())
    cur.close()
    rows.reverse()
    return rows


def _day(value):
    if value is None:
        return None
    if hasattr(value, "date") and not isinstance(value, str):
        return value.date()
    text = str(value)[:10]
    return datetime.strptime(text, "%Y-%m-%d").date()


def _index_on_or_after(closes, day):
    if day is None:
        return len(closes) - 1
    for index, bar in enumerate(closes):
        if _day(bar["timestamp"]) >= day:
            return index
    return len(closes) - 1


def replay(book, symbol, closes, published, text, wire, filing_day=None, filing_score=None):
    """The headline rides its close. The 8-K rides the close of its filing day."""
    if not closes:
        return None
    news_at = _index_on_or_after(closes, _day(published))
    filing_at = None
    if filing_score is not None:
        filing_at = _index_on_or_after(closes, filing_day)
    row = None
    for index, bar in enumerate(closes):
        extra = None
        if index == filing_at:
            extra = {"filing": filing_score}
        if index == news_at:
            row = book.update(symbol, bar["price"], text=text, wire=wire, extra=extra)
        else:
            row = book.update(symbol, bar["price"], extra=extra)
    state = book.symbols[symbol]
    if row is not None:
        row["words_graded"] = state.seen.get("words", 0) > 0
        row["filing_graded"] = state.seen.get("filing", 0) > 0
        graded = state.graded_weights()
        row["words_weight"] = graded.get("words")
        row["filing_weight"] = graded.get("filing")
    return row


def article_rows(limit=20):
    """Score listed symbols that appear in the latest articles. Reads prices, writes nothing."""
    universe = listed_symbols()
    book = Book()
    conn = connect()
    rows = []
    try:
        for item in fetch_articles(limit):
            text = article_text(item.title, item.description)
            if not text:
                continue
            for symbol in item.tickers or []:
                symbol = str(symbol).upper().replace(".", "-")
                if universe and symbol not in universe:
                    continue
                if any(row["symbol"] == symbol for row in rows):
                    continue
                closes = recent_closes(conn, symbol)
                if not closes:
                    continue
                wire = None
                for insight in item.insights or []:
                    if str(insight.ticker or "").upper().replace(".", "-") == symbol:
                        wire = wire_score(insight.sentiment)
                        break
                filing_day = None
                filing_score = None
                try:
                    filing = fetch_filing(symbol)
                except Exception:
                    filing = None
                if filing and filing.get("text"):
                    filing_day = _day(filing.get("filed"))
                    filing_score = word_score(filing["text"][:4000])
                scored = replay(
                    book,
                    symbol,
                    closes,
                    item.published_utc,
                    text,
                    wire,
                    filing_day,
                    filing_score,
                )
                if scored is None:
                    continue
                scored["title"] = item.title
                scored["words"] = word_score(text)
                rows.append(scored)
                if len(rows) >= 3:
                    return rows
    finally:
        conn.close()
    return rows
