"""Elenco titoli e scarico prezzi da Yahoo Finance."""

import re
import time
import urllib.request
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from bot_config import UNIVERSE_CACHE, get_logger
from bot_db import history_coverage, quantize_volume, upsert_bars
from bot_logic import money

log = get_logger()

# Listino di riserva se l'elenco S&P 500 non è raggiungibile. Titoli liquidi, simbolo Yahoo.
FALLBACK = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "BRK-B", "LLY", "AVGO",
    "JPM", "TSLA", "UNH", "V", "XOM", "MA", "JNJ", "COST", "HD", "PG",
    "NFLX", "BAC", "ABBV", "KO", "CRM", "ORCL", "CVX", "WMT", "MRK", "AMD",
    "PEP", "TMO", "CSCO", "ACN", "MCD", "LIN", "ABT", "WFC", "IBM", "GE",
    "CAT", "NOW", "DIS", "PM", "AXP", "GS", "QCOM", "TXN", "VZ", "INTU",
    "AMGN", "ISRG", "BKNG", "SPGI", "T", "PFE", "AMAT", "BLK", "NEE", "RTX",
    "LOW", "SYK", "HON", "UNP", "SCHW", "PLD", "ETN", "ADP", "C", "BK",
    "BSX", "DE", "MMC", "GILD", "ADI", "VRTX", "LRCX", "PANW", "KLAC", "ANET",
    "SBUX", "CB", "SO", "MO", "TMUS", "BMY", "DUK", "CI", "REGN", "EQIX",
    "CME", "ZTS", "PGR", "SNPS", "CDNS", "WM", "SHW", "ICE", "APH", "ITW",
    "CMG", "MCO", "PH", "ORLY", "MAR", "AON", "ECL", "ADSK", "ROP", "HCA",
    "NOC", "GD", "SLB", "EMR", "FDX", "NSC", "MPC", "PSX", "TGT", "USB",
    "PNC", "CL", "APD", "MCK", "TDG", "AJG", "TT", "COF", "AFL", "MET",
    "TRV", "AIG", "ALL", "SPG", "O", "WELL", "PSA", "DLR", "CCI", "SRE",
    "AEP", "D", "EXC", "XEL", "PEG", "ED", "WEC", "PCG", "AEE", "DTE",
    "MU", "NXPI", "CRWD", "ABNB", "DASH", "APP", "PLTR", "UBER", "INTC", "AMZN",
    "NKE", "MDT", "CVS", "BA", "GM", "F", "PYPL", "SQ", "SHOP", "MELI",
    "ASML", "SAP", "NVO", "TM", "SONY", "BABA", "PDD", "SE", "SNY", "UL",
    "HSBC", "BHP", "RIO", "SHEL", "BP", "TTE", "AZN", "GSK", "NVS", "LIN",
    "ELV", "HUM", "CNC", "DHR", "EW", "IDXX", "IQV", "A", "WST", "MTD",
    "CTAS", "FAST", "PAYX", "CPRT", "ODFL", "CSX", "KHC", "MDLZ", "KDP", "STZ",
    "EL", "CLX", "CHD", "SJM", "HSY", "GIS", "K", "CAG", "CPB", "HRL",
    "ROST", "TJX", "DG", "DLTR", "ORLY", "AZO", "GPC", "AAP", "TSCO", "BBY",
    "HD", "LOW", "LEN", "DHI", "PHM", "NVR", "TOL", "KBH", "MTH", "TMHC",
    "FCX", "NEM", "NUE", "STLD", "CF", "MOS", "ALB", "APD", "ECL", "SHW",
    "LMT", "NOC", "GD", "HII", "TDG", "HWM", "TXT", "LHX", "LDOS", "BA",
    "DAL", "UAL", "AAL", "LUV", "RCL", "CCL", "NCLH", "MAR", "HLT", "H",
    "SPGI", "MCO", "MSCI", "FDS", "NDAQ", "CME", "ICE", "CBOE", "MKTX", "V",
    "MA", "AXP", "COF", "SYF", "DFS", "ALLY", "SOFI", "HOOD", "SCHW", "RJF",
    "BLK", "BX", "KKR", "APO", "ARES", "TROW", "BEN", "IVZ", "AMP", "PRU",
    "MET", "AFL", "ALL", "TRV", "PGR", "CB", "AJG", "MMC", "AON", "WTW",
    "JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "TFC", "BK",
    "STT", "NTRS", "CFG", "KEY", "RF", "HBAN", "FITB", "MTB", "ZION", "CMA",
    "AMT", "PLD", "CCI", "EQIX", "PSA", "DLR", "O", "SPG", "WELL", "VICI",
    "AVB", "EQR", "ESS", "MAA", "UDR", "CPT", "INVH", "AMH", "SUI", "ELS",
    "NEE", "SO", "DUK", "AEP", "SRE", "D", "EXC", "XEL", "PEG", "ED",
    "WEC", "ES", "FE", "ETR", "PCG", "EIX", "AES", "VST", "CEG", "NRG",
    "XOM", "CVX", "COP", "EOG", "PXD", "MPC", "PSX", "VLO", "OXY", "HES",
    "DVN", "FANG", "APA", "BKR", "SLB", "HAL", "OKE", "WMB", "KMI", "ET",
    "CAT", "DE", "EMR", "ETN", "ITW", "PH", "ROK", "DOV", "IR", "XYL",
    "GE", "GEV", "HON", "MMM", "ROK", "CARR", "OTIS", "JCI", "TT", "IR",
    "UNP", "CSX", "NSC", "FDX", "UPS", "ODFL", "JBHT", "CHRW", "EXPD", "KNX",
    "T", "VZ", "TMUS", "CMCSA", "CHTR", "DIS", "NFLX", "WBD", "PARA", "FOXA",
    "EA", "TTWO", "RBLX", "SPOT", "LYV", "MTCH", "NWSA", "NYT", "OMC", "IPG",
    "PG", "KO", "PEP", "PM", "MO", "CL", "KMB", "CHD", "CLX", "EL",
    "NKE", "SBUX", "MCD", "CMG", "YUM", "DPZ", "QSR", "DRI", "WING", "CAVA",
)


def candidate_symbols(limit):
    symbols = _load_sp500() or list(dict.fromkeys(FALLBACK))
    unique = []
    seen = set()
    for symbol in symbols:
        if symbol in seen:
            continue
        seen.add(symbol)
        unique.append(symbol)
        if len(unique) >= limit:
            break
    return unique


def _load_sp500():
    if UNIVERSE_CACHE.exists():
        age = datetime.now().timestamp() - UNIVERSE_CACHE.stat().st_mtime
        if age < 7 * 24 * 3600:
            cached = _read_cache()
            if len(cached) >= 100:
                return cached
    fresh = _fetch_sp500()
    if len(fresh) >= 100:
        UNIVERSE_CACHE.write_text("\n".join(fresh) + "\n", encoding="utf-8")
        return fresh
    cached = _read_cache()
    return cached or None


def _read_cache():
    if not UNIVERSE_CACHE.exists():
        return []
    symbols = []
    for line in UNIVERSE_CACHE.read_text(encoding="utf-8").splitlines():
        text = line.strip().upper().replace(".", "-")
        if text and text[0].isalpha():
            symbols.append(text)
    return symbols


def _fetch_sp500():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "trading-bot/1.0 (uso personale)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            html = response.read().decode("utf-8", "replace")
    except OSError as exc:
        log.warning("elenco S&P 500 non scaricato: %s", exc)
        return []
    start = html.find('id="constituents"')
    end = html.find("<h2", start + 1) if start != -1 else -1
    chunk = html[start:end] if start != -1 and end != -1 else html
    symbols = []
    # La prima colonna di ogni riga è il simbolo, dentro un link.
    for piece in chunk.split("<tr")[1:]:
        cell_end = piece.find("</td>")
        cell = piece[:cell_end] if cell_end != -1 else ""
        symbol = _symbol_from_cell(cell)
        if symbol:
            symbols.append(symbol)
        if len(symbols) >= 500:
            break
    log.info("elenco S&P 500: %s simboli", len(symbols))
    return symbols


def _symbol_from_cell(cell):
    match = re.search(r">([A-Za-z][A-Za-z0-9.\-]{0,7})</a>", cell)
    if not match:
        return None
    text = match.group(1).upper().replace(".", "-")
    if any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for char in text):
        return None
    return text


def session_current(latest, now):
    """La seduta giornaliera di venerdì resta valida per tutto il fine settimana."""
    if latest is None:
        return False
    day = now.date()
    if day.weekday() >= 5:
        friday = day - timedelta(days=day.weekday() - 4)
        return latest.date() >= friday
    return (now - latest).total_seconds() < 36 * 3600


def update_quotes(conn, symbols, on_progress):
    coverage = history_coverage(conn, symbols)
    full, recent = [], []
    now = datetime.now()
    for symbol in symbols:
        count, latest = coverage.get(symbol, (0, None))
        fresh = session_current(latest, now)
        if count >= 60 and fresh:
            continue
        if count >= 60:
            recent.append(symbol)
        else:
            full.append(symbol)
    batches = [("storico 6 mesi", full, "6mo"), ("ultime sedute", recent, "5d")]
    planned = sum((len(group) + 9) // 10 for _label, group, _period in batches if group)
    done = 0
    stored = 0
    failed = []
    waited = False
    if planned == 0:
        on_progress("Prezzi già aggiornati.")
        return 0, None
    for label, group, period in batches:
        for offset in range(0, len(group), 10):
            batch = group[offset : offset + 10]
            done += 1
            on_progress(f"Scarico {label}, blocco {done}/{planned} ({len(batch)} titoli)")
            rows = _download_batch(batch, period)
            if not rows and not waited:
                on_progress("Yahoo non ha risposto. Attendo e riprovo una volta.")
                log.warning("blocco vuoto, attendo: %s", ",".join(batch))
                time.sleep(45)
                waited = True
                rows = _download_batch(batch, period)
            if not rows:
                failed.extend(batch)
                log.warning("blocco saltato: %s", ",".join(batch))
                on_progress(f"Blocco {done} saltato. Continuo con gli altri.")
                continue
            stored += upsert_bars(conn, rows)
            time.sleep(3)
    if failed:
        message = (
            f"Questo giro non ha aggiornato {len(failed)} titoli: barre nuove {stored}. "
            "Lo storico già in archivio resta. Il prossimo giro riprova solo quelli rimasti indietro."
        )
        log.warning(message)
        return stored, message
    log.info("barre scritte o aggiornate: %s", stored)
    return stored, None


def _download_batch(batch, period):
    try:
        frame = yf.download(
            batch,
            period=period,
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            threads=False,
            progress=False,
            timeout=45,
        )
    except Exception:
        log.exception("blocco non scaricato: %s", ",".join(batch))
        return []
    return bars_from_download(frame, batch)


def bars_from_download(frame, tickers):
    rows = []
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return rows
    for ticker in tickers:
        sub = _slice_ticker(frame, ticker)
        if sub is None or sub.empty or "Close" not in sub.columns:
            continue
        sub = sub.dropna(subset=["Close"])
        for ts, row in sub.iterrows():
            close = money(row["Close"])
            if close is None or close <= 0:
                continue
            when = ts.to_pydatetime()
            if when.tzinfo is not None:
                when = when.replace(tzinfo=None)
            when = when.replace(microsecond=0)
            rows.append(
                {
                    "asset_name": ticker,
                    "timestamp": when,
                    "price": close,
                    "open_price": _optional_money(row.get("Open")),
                    "high_price": _optional_money(row.get("High")),
                    "low_price": _optional_money(row.get("Low")),
                    "volume": quantize_volume(row.get("Volume")),
                }
            )
    return rows


def _slice_ticker(frame, ticker):
    if not isinstance(frame.columns, pd.MultiIndex):
        return frame
    level0 = set(frame.columns.get_level_values(0))
    if ticker in level0:
        return frame[ticker]
    level1 = set(frame.columns.get_level_values(1))
    if ticker in level1:
        return frame.xs(ticker, axis=1, level=1)
    return None


def _optional_money(value):
    try:
        if value is None or pd.isna(value):
            return None
    except TypeError:
        return None
    amount = money(value)
    if amount is None or amount <= 0:
        return None
    return amount
