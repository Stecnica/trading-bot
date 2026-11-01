"""Volume treemap and history chart."""

import io
import os
from contextlib import contextmanager

from bot_config import MPLCONFIG

os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from bot_i18n import tr
from matplotlib.dates import date2num
from matplotlib.patches import Rectangle

TONES = {
    "stabile": "bg-primary",
    "crescita": "bg-success",
    "perdita": "bg-danger",
}
# PNG: matplotlib does not apply the classes. The values are the Bootstrap 5.3 tokens.
COLORS = {
    "stabile": "#0d6efd",
    "crescita": "#198754",
    "perdita": "#dc3545",
}
INK = "#212529"
RULE = "#dee2e6"
PAPER = "#ffffff"
_LOOK = {"scale": 1, "weight": "medium"}
_PALETTES = {
    "light": ("#212529", "#dee2e6", "#ffffff"),
    "dark": ("#dee2e6", "#495057", "#212529"),
}
_WEIGHTS = {200: "light", 300: "light", 400: "normal", 500: "medium", 600: "semibold", 700: "bold"}


@contextmanager
def _appearance(theme, scale, weight):
    """Colors, scale, and weight for one drawing. The previous values return at the end."""
    global INK, RULE, PAPER
    previous = (INK, RULE, PAPER, _LOOK["scale"], _LOOK["weight"])
    INK, RULE, PAPER = _PALETTES.get(theme, _PALETTES["light"])
    try:
        scale = int(scale)
    except (TypeError, ValueError):
        scale = 100
    _LOOK["scale"] = max(80, min(scale, 120)) / 100
    try:
        weight = int(weight)
    except (TypeError, ValueError):
        weight = 400
    _LOOK["weight"] = _WEIGHTS.get(weight, "medium")
    try:
        yield
    finally:
        INK, RULE, PAPER, _LOOK["scale"], _LOOK["weight"] = previous
# Same margins as _finish_history: a hover title must land on the drawn session.
AXIS_LEFT = 0.075
AXIS_RIGHT = 0.985
LINE_MARGIN = 0.03
CANDLE_MARGIN = 0.02


def treemap_layout(blocks, names=None):
    """Rectangles in percent. The title is the symbol and the company, not the text already drawn."""
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
    """One letter is not enough on the tile: T is AT&T."""
    if not company:
        return symbol
    if len(symbol) <= 2:
        return company
    if kind == "big" and len(company) <= max(10, int(width / 0.012)):
        return company
    return symbol


def treemap_png(blocks):
    if not blocks:
        return _message_png(tr("volume.none"))
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


def history_model(series, asset, chart_type):
    """The same numbers as the PNG, in the form the SVG vector draws itself."""
    if not series:
        return {"asset": asset, "draw": "line", "title": tr("chart.empty", asset=asset), "points": []}
    has_ohlc = all(row.get("open_price") and row.get("high_price") and row.get("low_price") for row in series)
    draw = "candle" if chart_type == "candle" and has_ohlc else "line"
    if draw == "candle":
        title = tr("chart.candle", asset=asset)
    else:
        title = tr("chart.line_no_ohlc" if chart_type == "candle" and not has_ohlc else "chart.line", asset=asset)
    points = []
    for row in series:
        points.append(
            {
                "d": row["timestamp"].strftime("%Y-%m-%d"),
                "label": row["timestamp"].strftime("%d/%m"),
                "o": _num(row.get("open_price")),
                "h": _num(row.get("high_price")),
                "l": _num(row.get("low_price")),
                "c": _num(row["price"]),
                "v": _num(row.get("volume")) or 0,
                "lines": _session_lines(row),
            }
        )
    return {"asset": asset, "draw": draw, "title": title, "points": points}


def _num(value):
    if value is None:
        return None
    return float(value)


def history_png(series, asset, chart_type, width=1280, height=720, scale=100, theme="light", weight=400):
    with _appearance(theme, scale, weight):
        if not series:
            return _message_png(tr("chart.empty", asset=asset), width, height)
        has_ohlc = all(row.get("open_price") and row.get("high_price") and row.get("low_price") for row in series)
        if chart_type == "candle" and has_ohlc:
            return _candle_png(series, asset, width, height)
        return _line_png(series, asset, width, height)


def _line_png(series, asset, width, height):
    fig, ax, volume, tick, _title_px = _history_figure(width, height)
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
    _decorate(ax, tick)
    _date_labels(ax, dates, series, tick, indexed=False)
    _volume_strip(volume, dates, series, 0.72)
    _finish_history(fig, ax, volume)
    return _png(fig)


def _candle_png(series, asset, width, height):
    fig, ax, volume, tick, _title_px = _history_figure(width, height)
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
    _decorate(ax, tick)
    _date_labels(ax, None, series, tick, indexed=True)
    _volume_strip(volume, list(range(len(series))), series, 0.6)
    _finish_history(fig, ax, volume)
    return _png(fig)


def _history_figure(width, height):
    """Price above, volume in a thin band. The dates stay in between."""
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
        label.set_fontweight(_LOOK["weight"])
        if rotate:
            label.set_rotation(30)
            label.set_ha("right")


def _volume_strip(volume, xs, series, bar_width):
    """Session volume in shares. The color follows the candle: close against open."""
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
    """Bands as a percent of the image. The title is the figure the bar does not show."""
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
    """The amount does not come from Massive: it is share volume times the average price."""
    day = row["timestamp"].strftime("%d/%m/%Y")
    close = float(row["price"])
    lines = [day, tr("chart.close", price=f"{close:.4f}".rstrip("0").rstrip("."))]
    volume = row.get("volume")
    if not volume:
        lines.append(tr("chart.amount_missing"))
        return lines
    shares = int(round(float(volume)))
    share_text = f"{shares:,}".replace(",", " ")
    vwap = row.get("vwap")
    if vwap:
        price = float(vwap)
        basis = tr("chart.basis_vwap")
    else:
        price = close
        basis = tr("chart.basis_close")
    lines.append(tr("chart.amount", value=_usd(shares * price)))
    lines.append(tr("chart.shares", shares=share_text, basis=basis))
    return lines


def _finish_history(fig, price, volume):
    fig.subplots_adjust(left=AXIS_LEFT, right=AXIS_RIGHT, top=0.97, bottom=0.025)
    fig.canvas.draw()
    price.tick_params(axis="x", labelbottom=True)
    box = price.get_position()
    band = volume.get_position()
    volume.set_position([box.x0, band.y0, box.width, band.height])


def _decorate(ax, tick):
    ax.grid(True, axis="y", color=RULE, linewidth=_pt(1))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", colors=INK, labelsize=_pt(tick), width=_pt(1), length=_pt(6))
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontweight(_LOOK["weight"])
    ax.set_facecolor(PAPER)


def _metrics(width, height):
    """Page pixels. The type grows with the box and stops before it becomes a poster title."""
    try:
        width = int(width)
        height = int(height)
    except (TypeError, ValueError):
        width, height = 1280, 720
    width = max(480, min(width, 4096))
    height = max(280, min(height, 2160))
    span = (width * height) ** 0.5
    tick = 13 + (span - 640) * (6 / 1000)
    tick = max(12, min(19, tick)) * _LOOK["scale"]
    return width, height, tick, tick + 2


def _pt(px):
    """Matplotlib points that, at 200 dpi on a figure in hundredths of an inch, stay px on screen."""
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
