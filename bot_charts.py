"""Grafico a blocchi (volume e stato) e grafico storico."""

import io
import os

os.environ.setdefault("MPLCONFIGDIR", "/var/www/clients/client0/web5/private/mplconfig")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

COLORS = {
    "stabile": "#1565c0",
    "crescita": "#2e7d32",
    "perdita": "#c62828",
}


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
                "color": COLORS[block["state"]],
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
                edgecolor="#ffffff",
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
    fig, ax, tick, title_px = _figure(width, height)
    dates = [row["timestamp"] for row in series]
    prices = [float(row["price"]) for row in series]
    low, high = min(prices), max(prices)
    span = high - low
    pad = span * 0.22 or high * 0.012
    style = dict(color="#1565c0", linewidth=_pt(2.25))
    if len(series) <= 40:
        style.update(marker="o", markersize=_pt(8), markerfacecolor="#1565c0", markeredgecolor="#ffffff", markeredgewidth=_pt(1.4))
    ax.plot(dates, prices, **style)
    ax.set_ylim(low - pad, high + pad)
    ax.margins(x=0.03)
    title = asset + " — chiusure giornaliere"
    if missing_ohlc:
        title += " (mancano i prezzi per le candele)"
    _decorate(ax, title, tick, title_px)
    if len(series) <= 12:
        ax.set_xticks(dates)
        ax.set_xticklabels([day.strftime("%d/%m") for day in dates])
        for label in ax.get_xticklabels():
            label.set_fontsize(_pt(tick))
            label.set_fontweight("medium")
    else:
        fig.autofmt_xdate()
        for label in ax.get_xticklabels():
            label.set_fontsize(_pt(tick))
            label.set_fontweight("medium")
    fig.tight_layout()
    return _png(fig)


def _candle_png(series, asset, width, height):
    fig, ax, tick, title_px = _figure(width, height)
    for index, row in enumerate(series):
        open_price = float(row["open_price"])
        close = float(row["price"])
        high = float(row["high_price"])
        low = float(row["low_price"])
        color = "#2e7d32" if close >= open_price else "#c62828"
        ax.vlines(index, low, high, color=color, linewidth=_pt(1.25))
        body_low = min(open_price, close)
        body = abs(close - open_price) or (close * 0.0005)
        ax.add_patch(Rectangle((index - 0.3, body_low), 0.6, body, facecolor=color, edgecolor=color))
    step = max(1, len(series) // 8)
    ticks = list(range(0, len(series), step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([series[i]["timestamp"].strftime("%d/%m") for i in ticks])
    _decorate(ax, asset + " — candele", tick, title_px)
    fig.tight_layout()
    return _png(fig)


def _decorate(ax, title, tick, title_px):
    ax.set_title(title, loc="left", fontsize=_pt(title_px), color="#1a1a1a", pad=_pt(8))
    ax.grid(True, axis="y", color="#e6e6e6", linewidth=_pt(1))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", colors="#222222", labelsize=_pt(tick), width=_pt(1), length=_pt(6))
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontweight("medium")
    ax.set_facecolor("#ffffff")


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
    fig.patch.set_facecolor("#ffffff")
    return fig, ax, tick, title


def _message_png(text, width=1280, height=720):
    fig, ax, tick, _title = _figure(width, height)
    ax.axis("off")
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=_pt(tick), color="#333333", wrap=True)
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
