"""Grafico a blocchi (volume e stato) e grafico storico."""

import io
import os

os.environ.setdefault("MPLCONFIGDIR", "/var/www/clients/client0/web5/private/mplconfig")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from matplotlib.dates import date2num
from matplotlib.patches import Rectangle

TONES = {
    "stabile": "bg-primary",
    "crescita": "bg-success",
    "perdita": "bg-danger",
}
# PNG: matplotlib non applica le classi. I valori sono i token Bootstrap 5.3.
COLORS = {
    "stabile": "#0d6efd",
    "crescita": "#198754",
    "perdita": "#dc3545",
}
INK = "#212529"
RULE = "#dee2e6"
PAPER = "#ffffff"
# Stessi margini di _finish_history: il titolo al passaggio deve cadere sulla seduta disegnata.
AXIS_LEFT = 0.075
AXIS_RIGHT = 0.985
LINE_MARGIN = 0.03
CANDLE_MARGIN = 0.02


def treemap_layout(blocks, names=None):
    """Rettangoli in percentuale. Il title è sigla e società, non il testo già disegnato."""
    if not blocks:
        return []
    sizes = [float(block["volume"]) for block in blocks]
    laid = []
    for (x, y, width, height), block in zip(_squarify(sizes), blocks):
        daily = float(block["daily"])
        sign = "+" if daily > 0 else ""
        change = f"{sign}{daily * 100:.1f}%"
        if width >= 0.07 and height >= 0.055:
            kind = "big"
        elif width >= 0.028 and height >= 0.028:
            kind = "mid"
        else:
            kind = "tiny"
        company = (names or {}).get(block["asset"], "")
        title = f"{block['asset']} — {company} {change}" if company else f"{block['asset']} {change}"
        laid.append(
            {
                "asset": block["asset"],
                "x": round(x * 100, 3),
                "y": round(y * 100, 3),
                "w": round(width * 100, 3),
                "h": round(height * 100, 3),
                "tone": TONES[block["state"]],
                "change": change,
                "label": _tile_label(block["asset"], company, kind, width),
                "title": title,
                "kind": kind,
            }
        )
    return laid


def _tile_label(symbol, company, kind, width):
    """Sul riquadro non basta una lettera: T è AT&T."""
    if not company:
        return symbol
    if len(symbol) <= 2:
        return company
    if kind == "big" and len(company) <= max(10, int(width / 0.012)):
        return company
    return symbol


def treemap_png(blocks):
    if not blocks:
        return _message_png("Nessun titolo con volume. Aggiorna i prezzi.")
    sizes = [float(block["volume"]) for block in blocks]
    fig, ax, _tick, _title = _figure()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.invert_yaxis()
    ax.axis("off")
    for (x, y, w, h), block in zip(_squarify(sizes), blocks):
        ax.add_patch(
            Rectangle(
                (x, y),
                w,
                h,
                facecolor=COLORS[block["state"]],
                edgecolor=PAPER,
                linewidth=1.2,
            )
        )
        if w > 0.07 and h > 0.055:
            sign = "+" if block["daily"] > 0 else ""
            ax.text(
                x + w / 2,
                y + h / 2,
                f"{block['asset']}\n{sign}{block['daily'] * 100:.1f}%",
                ha="center",
                va="center",
                color="white",
                fontsize=8,
                fontweight="medium",
            )
    fig.tight_layout(pad=0.4)
    return _png(fig)


def history_png(series, asset, chart_type, width=1280, height=720):
    if not series:
        return _message_png(f"Nessuno storico per {asset}.", width, height)
    has_ohlc = all(row.get("open_price") and row.get("high_price") and row.get("low_price") for row in series)
    if chart_type == "candle" and has_ohlc:
        return _candle_png(series, asset, width, height)
    return _line_png(series, asset, chart_type == "candle" and not has_ohlc, width, height)


def _line_png(series, asset, missing_ohlc, width, height):
    fig, ax, volume, tick, title_px = _history_figure(width, height)
    dates = [row["timestamp"] for row in series]
    prices = [float(row["price"]) for row in series]
    low, high = min(prices), max(prices)
    span = high - low
    pad = span * 0.22 or high * 0.012
    style = dict(color=COLORS["stabile"], linewidth=_pt(2.25))
    if len(series) <= 40:
        style.update(marker="o", markersize=_pt(8), markerfacecolor=COLORS["stabile"], markeredgecolor=PAPER, markeredgewidth=_pt(1.4))
    ax.plot(dates, prices, **style)
    ax.set_ylim(low - pad, high + pad)
    ax.margins(x=LINE_MARGIN)
    title = asset + " — chiusure giornaliere"
    if missing_ohlc:
        title += " (mancano i prezzi per le candele)"
    _decorate(ax, title, tick, title_px)
    _date_labels(ax, dates, series, tick, indexed=False)
    _volume_strip(volume, dates, series, 0.72)
    _finish_history(fig, ax, volume)
    return _png(fig)


def _candle_png(series, asset, width, height):
    fig, ax, volume, tick, title_px = _history_figure(width, height)
    for index, row in enumerate(series):
        open_price = float(row["open_price"])
        close = float(row["price"])
        high = float(row["high_price"])
        low = float(row["low_price"])
        color = COLORS["crescita"] if close >= open_price else COLORS["perdita"]
        ax.vlines(index, low, high, color=color, linewidth=_pt(1.25))
        body_low = min(open_price, close)
        body = abs(close - open_price) or (close * 0.0005)
        ax.add_patch(Rectangle((index - 0.3, body_low), 0.6, body, facecolor=color, edgecolor=color))
    ax.margins(x=CANDLE_MARGIN)
    _decorate(ax, asset + " — candele", tick, title_px)
    _date_labels(ax, None, series, tick, indexed=True)
    _volume_strip(volume, list(range(len(series))), series, 0.6)
    _finish_history(fig, ax, volume)
    return _png(fig)


def _history_figure(width, height):
    """Prezzo sopra, volume in una fascia sottile. Le date restano in mezzo."""
    width, height, tick, title = _metrics(width, height)
    fig = plt.figure(figsize=(width / 100, height / 100), dpi=200)
    fig.patch.set_facecolor(PAPER)
    grid = fig.add_gridspec(2, 1, height_ratios=[7.4, 1], hspace=0.22)
    price = fig.add_subplot(grid[0])
    volume = fig.add_subplot(grid[1], sharex=price)
    return fig, price, volume, tick, title


def _date_labels(ax, dates, series, tick, indexed):
    if indexed or len(series) <= 12:
        if indexed:
            step = max(1, len(series) // 8)
            ticks = list(range(0, len(series), step))
            labels = [series[i]["timestamp"].strftime("%d/%m") for i in ticks]
        else:
            ticks = dates
            labels = [day.strftime("%d/%m") for day in dates]
        ax.set_xticks(ticks)
        ax.set_xticklabels(labels)
    rotate = len(series) > 12
    ax.tick_params(axis="x", labelbottom=True)
    for label in ax.get_xticklabels():
        label.set_fontsize(_pt(tick))
        label.set_fontweight("medium")
        if rotate:
            label.set_rotation(30)
            label.set_ha("right")


def _volume_strip(volume, xs, series, bar_width):
    """Volume in azioni della seduta. Il colore segue la candela: chiusura contro apertura."""
    amounts = [float(row["volume"] or 0) for row in series]
    peak = max(amounts) if amounts else 0
    if peak <= 0:
        volume.set_visible(False)
        return
    colors = []
    previous = None
    for row in series:
        close = float(row["price"])
        open_price = row.get("open_price")
        if open_price:
            rising = close >= float(open_price)
        elif previous is None:
            rising = True
        else:
            rising = close >= previous
        colors.append(COLORS["crescita"] if rising else COLORS["perdita"])
        previous = close
    volume.bar(xs, amounts, width=bar_width, color=colors, linewidth=0, align="center")
    volume.set_ylim(0, peak * 1.08)
    volume.set_facecolor(PAPER)
    volume.grid(False)
    for name in ("top", "right", "left"):
        volume.spines[name].set_visible(False)
    volume.spines["bottom"].set_color(RULE)
    volume.spines["bottom"].set_linewidth(_pt(1))
    volume.tick_params(axis="both", which="both", left=False, labelleft=False, bottom=False, labelbottom=False)


def history_hits(series, chart_type):
    """Fasce in percentuale dell'immagine. Il title è la cifra che la barra non mostra."""
    if not series:
        return []
    indexed = chart_type == "candle" and all(
        row.get("open_price") and row.get("high_price") and row.get("low_price") for row in series
    )
    margin = CANDLE_MARGIN if indexed else LINE_MARGIN
    xs = list(range(len(series))) if indexed else [date2num(row["timestamp"]) for row in series]
    width = AXIS_RIGHT - AXIS_LEFT
    if xs[-1] == xs[0]:
        spans = [(AXIS_LEFT, width)]
    else:
        span = xs[-1] - xs[0]
        view_lo = xs[0] - margin * span
        view_hi = xs[-1] + margin * span
        view = view_hi - view_lo
        spans = []
        for index, x in enumerate(xs):
            start = view_lo if index == 0 else (xs[index - 1] + x) / 2
            end = view_hi if index + 1 == len(xs) else (x + xs[index + 1]) / 2
            left = AXIS_LEFT + (start - view_lo) / view * width
            spans.append((left, AXIS_LEFT + (end - view_lo) / view * width - left))
    return [
        {"x": round(left * 100, 3), "w": round(band * 100, 3), "lines": _session_lines(row)}
        for (left, band), row in zip(spans, series)
    ]


def _usd(amount):
    if amount >= 1e12:
        text, unit = amount / 1e12, "bilioni"
    elif amount >= 1e9:
        text, unit = amount / 1e9, "miliardi"
    elif amount >= 1e6:
        text, unit = amount / 1e6, "milioni"
    elif amount >= 1e3:
        text, unit = amount / 1e3, "mila"
    else:
        return f"{amount:.2f} USD"
    return f"{text:.2f} {unit} USD"


def _session_lines(row):
    """L'importo non arriva da Massive: è il volume in azioni per il prezzo medio."""
    day = row["timestamp"].strftime("%d/%m/%Y")
    close = float(row["price"])
    lines = [day, "chiusura " + f"{close:.4f}".rstrip("0").rstrip(".")]
    volume = row.get("volume")
    if not volume:
        lines.append("importo assente")
        return lines
    shares = int(round(float(volume)))
    share_text = f"{shares:,}".replace(",", " ")
    vwap = row.get("vwap")
    if vwap:
        price = float(vwap)
        basis = "prezzo medio"
    else:
        price = close
        basis = "chiusura"
    lines.append("importo " + _usd(shares * price))
    lines.append(f"{share_text} azioni × {basis}")
    return lines


def _finish_history(fig, price, volume):
    fig.subplots_adjust(left=AXIS_LEFT, right=AXIS_RIGHT, top=0.90, bottom=0.025)
    fig.canvas.draw()
    price.tick_params(axis="x", labelbottom=True)
    box = price.get_position()
    band = volume.get_position()
    volume.set_position([box.x0, band.y0, box.width, band.height])


def _decorate(ax, title, tick, title_px):
    ax.set_title(title, loc="left", fontsize=_pt(title_px), color=INK, pad=_pt(8))
    ax.grid(True, axis="y", color=RULE, linewidth=_pt(1))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", colors=INK, labelsize=_pt(tick), width=_pt(1), length=_pt(6))
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontweight("medium")
    ax.set_facecolor(PAPER)


def _metrics(width, height):
    """Pixel di pagina. Il carattere cresce col riquadro e si ferma prima di diventare un titolo da manifesto."""
    try:
        width = int(width)
        height = int(height)
    except (TypeError, ValueError):
        width, height = 1280, 720
    width = max(480, min(width, 4096))
    height = max(280, min(height, 2160))
    span = (width * height) ** 0.5
    tick = 13 + (span - 640) * (6 / 1000)
    tick = max(12, min(19, tick))
    return width, height, tick, tick + 2


def _pt(px):
    """Punti matplotlib che, a 200 dpi su una figura in centesimi di pollice, restano px sullo schermo."""
    return px * 72 / 100


def _figure(width=1280, height=720):
    width, height, tick, title = _metrics(width, height)
    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=200)
    fig.patch.set_facecolor(PAPER)
    return fig, ax, tick, title


def _message_png(text, width=1280, height=720):
    fig, ax, tick, _title = _figure(width, height)
    ax.axis("off")
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=_pt(tick), color=INK, wrap=True)
    fig.tight_layout()
    return _png(fig)


def _png(fig):
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png")
    plt.close(fig)
    buffer.seek(0)
    return buffer


def _worst(row, side):
    total = sum(row)
    if total <= 0:
        return float("inf")
    worst = max(row)
    best = min(row)
    return max((side * side * worst) / (total * total), (total * total) / (side * side * best))


def _squarify(sizes):
    total = sum(sizes)
    if total <= 0:
        return []
    areas = [size / total for size in sizes]
    rects = []

    def layout(items, x, y, width, height):
        if not items:
            return
        if len(items) == 1 or width <= 0 or height <= 0:
            rects.append((x, y, max(width, 0), max(height, 0)))
            return
        vertical = width < height
        side = height if vertical else width
        row = []
        rest = items[:]
        while rest:
            if not row or _worst(row + [rest[0]], side) <= _worst(row, side):
                row.append(rest.pop(0))
            else:
                break
        if not rest:
            row = items[:]
            rest = []
        consumed = sum(row)
        if vertical:
            row_height = consumed / width if width else 0
            cursor = x
            for value in row:
                row_width = value / row_height if row_height else 0
                rects.append((cursor, y, row_width, row_height))
                cursor += row_width
            layout(rest, x, y + row_height, width, height - row_height)
        else:
            row_width = consumed / height if height else 0
            cursor = y
            for value in row:
                row_height = value / row_width if row_width else 0
                rects.append((x, cursor, row_width, row_height))
                cursor += row_height
            layout(rest, x + row_width, y, width - row_width, height)

    layout(areas, 0, 0, 1, 1)
    return rects
