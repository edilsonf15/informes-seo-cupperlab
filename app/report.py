"""Renderizado del informe: HTML (Jinja) -> PDF (Playwright/Chromium)."""
import os
import base64
import calendar
from datetime import date, timedelta
from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright
from . import config

_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _month_label(ym):
    """'2026-09' -> 'sep 26'."""
    try:
        y, m = ym.split("-")[:2]
        return f"{_MESES[int(m) - 1]} {y[2:]}"
    except Exception:
        return str(ym)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "static", "brand", "cupperlab-wordmark.png")
_LOGO_URI = None


def logo_uri():
    """Devuelve el wordmark de Cupperlab como data-URI (para embeber en el PDF)."""
    global _LOGO_URI
    if _LOGO_URI is None:
        try:
            with open(_LOGO_PATH, "rb") as f:
                _LOGO_URI = "data:image/png;base64," + base64.b64encode(f.read()).decode()
        except Exception:
            _LOGO_URI = ""
    return _LOGO_URI

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)


def bar_chart(series, value_key, label_key="month", color="#12324a", height=140, unit=""):
    """Genera un gráfico de barras en SVG inline (sin librerías externas)."""
    if not series:
        return ""
    values = [max(0, (row.get(value_key) or 0)) for row in series]
    labels = [str(row.get(label_key, "")) for row in series]
    vmax = max(values) or 1
    n = len(values)
    bw = 46
    gap = 16
    width = n * bw + (n + 1) * gap
    plot_h = height - 34
    bars = []
    for i, (v, lbl) in enumerate(zip(values, labels)):
        bh = int(plot_h * v / vmax)
        x = gap + i * (bw + gap)
        y = plot_h - bh + 6
        short = lbl[-2:] if "-" in lbl else lbl
        bars.append(
            f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="3" fill="{color}"/>'
            f'<text x="{x + bw/2:.0f}" y="{y - 4}" text-anchor="middle" '
            f'font-size="10" fill="#333">{_fmt(v)}</text>'
            f'<text x="{x + bw/2:.0f}" y="{plot_h + 22}" text-anchor="middle" '
            f'font-size="9" fill="#777">{short}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" '
        f'style="max-width:{width}px">{"".join(bars)}</svg>'
    )


def _fmt(v):
    try:
        v = int(v)
    except Exception:
        return str(v)
    return f"{v:,}".replace(",", ".")


def _bucket_series(daily, value_key, start=None, end=None):
    """Agrupa la serie diaria por día/semana/mes según lo largo que sea el rango."""
    rows = [r for r in (daily or []) if r.get("date")]
    if not rows:
        return []
    try:
        span = (date.fromisoformat(end) - date.fromisoformat(start)).days
    except (ValueError, TypeError):
        span = len(rows)
    gran = "day" if span <= 45 else ("week" if span <= 180 else "month")
    buckets = {}
    order = []
    for r in rows:
        try:
            d = date.fromisoformat(r["date"])
        except (ValueError, TypeError):
            continue
        if gran == "day":
            key = r["date"]
            lbl = f"{d.day} {_MESES[d.month - 1]}"
        elif gran == "week":
            wk = d - timedelta(days=d.weekday())
            key = wk.isoformat()
            lbl = f"{wk.day} {_MESES[wk.month - 1]}"
        else:
            key = f"{d.year:04d}-{d.month:02d}"
            lbl = _month_label(key)
        if key not in buckets:
            buckets[key] = {"label": lbl, "value": 0}
            order.append(key)
        buckets[key]["value"] += (r.get(value_key) or 0)
    return [buckets[k] for k in order]


def trend_area(daily, value_key, start=None, end=None, color="#1cbce4", height=180):
    """Evolución POR FECHAS (área + línea). Se adapta a día/semana/mes y nunca se rompe."""
    pts_data = _bucket_series(daily, value_key, start, end)
    if not pts_data:
        return '<div class="small muted" style="padding:18px 2px">Sin datos en el periodo elegido.</div>'
    vals = [max(0, b["value"]) for b in pts_data]
    labels = [b["label"] for b in pts_data]
    n = len(vals)
    vmax = max(vals) or 1
    W, H, pad = 680, height, 14
    plot_h = H - 36
    stepx = (W - 2 * pad) / max(1, n - 1)
    pts = []
    for i, v in enumerate(vals):
        x = pad + i * stepx
        y = 10 + plot_h - (plot_h * v / vmax)
        pts.append((x, y))
    if n == 1:
        pts = [(pad, pts[0][1]), (W - pad, pts[0][1])]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pts[0][0]:.1f},{10 + plot_h:.1f} " + line + f" {pts[-1][0]:.1f},{10 + plot_h:.1f}"
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>' for x, y in pts)
    vlabels = ""
    if n <= 14:
        vlabels = "".join(
            f'<text x="{pts[i][0]:.1f}" y="{pts[i][1] - 8:.1f}" text-anchor="middle" font-size="9.5" '
            f'font-weight="700" fill="#11151c" font-family="JetBrains Mono,monospace">{_fmt(vals[i])}</text>'
            for i in range(n))
    show = max(1, round(n / 8))
    xl = "".join(
        f'<text x="{pad + i * stepx:.1f}" y="{H - 6}" text-anchor="middle" font-size="9" '
        f'fill="#58626f" font-family="Plus Jakarta Sans,sans-serif">{labels[i]}</text>'
        for i in range(n) if i % show == 0 or i == n - 1)
    gid = f"tr{abs(hash(color + str(vmax))) % 99999}"
    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">'
        f'<defs><linearGradient id="{gid}" x1="0" x2="0" y1="0" y2="1">'
        f'<stop offset="0" stop-color="{color}" stop-opacity="0.22"/>'
        f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
        f'<polygon points="{area}" fill="url(#{gid})"/>'
        f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2.5" '
        f'stroke-linejoin="round"/>{dots}{vlabels}{xl}</svg>'
    )


def monthly_bars(series, value_key, start=None, end=None, color="#1cbce4", height=170):
    """Barras por mes con etiqueta (sep 26), valor encima y mes incompleto atenuado.

    Un mes se marca 'parcial' (atenuado) si el rango no lo cubre entero, para que
    un último mes a medias no parezca una caída real de impresiones/clics.
    """
    rows = list(series or [])
    if not rows:
        return '<div class="small muted" style="padding:18px 2px">Sin datos en el periodo elegido.</div>'

    partial = set()
    try:
        if start:
            sd = date.fromisoformat(start)
            if sd.day > 1:
                partial.add(f"{sd.year:04d}-{sd.month:02d}")
        if end:
            ed = date.fromisoformat(end)
            if ed.day < calendar.monthrange(ed.year, ed.month)[1]:
                partial.add(f"{ed.year:04d}-{ed.month:02d}")
    except (ValueError, TypeError):
        pass

    keys = [str(r.get("month", "")) for r in rows]
    values = [max(0, (r.get(value_key) or 0)) for r in rows]
    vmax = max(values) or 1
    n = len(values)
    bw = 56 if n <= 8 else (36 if n <= 14 else 24)
    gap = max(10, bw // 3)
    width = n * bw + (n + 1) * gap
    has_partial = bool(partial & set(keys))
    plot_h = height - (46 if has_partial else 38)

    bars = []
    for i, (v, k) in enumerate(zip(values, keys)):
        bh = int(plot_h * v / vmax)
        x = gap + i * (bw + gap)
        y = plot_h - bh + 10
        is_p = k in partial
        op = "0.38" if is_p else "1"
        bars.append(
            f'<rect x="{x}" y="{y}" width="{bw}" height="{max(bh,2)}" rx="4" fill="{color}" opacity="{op}"/>'
            f'<text x="{x + bw/2:.0f}" y="{y - 6}" text-anchor="middle" font-size="11" font-weight="700" '
            f'fill="#11151c" font-family="JetBrains Mono,monospace">{_fmt(v)}</text>'
            f'<text x="{x + bw/2:.0f}" y="{plot_h + 24}" text-anchor="middle" font-size="10" '
            f'fill="#58626f" font-family="Plus Jakarta Sans,sans-serif">{_month_label(k)}</text>'
            + (f'<text x="{x + bw/2:.0f}" y="{plot_h + 37}" text-anchor="middle" font-size="8" '
               f'fill="#a3adba" font-family="Plus Jakarta Sans,sans-serif">parcial</text>' if is_p else "")
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" preserveAspectRatio="xMidYMid meet" '
        f'xmlns="http://www.w3.org/2000/svg" style="max-width:{max(width, 320)}px">{"".join(bars)}</svg>'
    )


def area_chart(series, value_key, color="#1cbce4", label_key="month", height=120):
    """Gráfica de área con línea (estilo widget SE Ranking)."""
    if not series:
        return ""
    vals = [max(0, (r.get(value_key) or 0)) for r in series]
    labels = [str(r.get(label_key, "")) for r in series]
    n = len(vals)
    vmax = max(vals) or 1
    W, H, pad = 640, height, 10
    plot_h = H - 26
    stepx = (W - 2 * pad) / max(1, (n - 1))
    pts = []
    for i, v in enumerate(vals):
        x = pad + i * stepx
        y = 6 + plot_h - (plot_h * v / vmax)
        pts.append((x, y))
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pts[0][0]:.1f},{6 + plot_h:.1f} " + line + f" {pts[-1][0]:.1f},{6 + plot_h:.1f}"
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{color}"/>' for x, y in pts)
    xl = "".join(
        f'<text x="{pad + i * stepx:.1f}" y="{H - 4}" text-anchor="middle" font-size="8" fill="#9aa5b1">'
        f'{(labels[i][-2:] if "-" in labels[i] else labels[i])}</text>' for i in range(n))
    gid = f"ar{abs(hash(color + str(vmax))) % 99999}"
    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">'
        f'<defs><linearGradient id="{gid}" x1="0" x2="0" y1="0" y2="1">'
        f'<stop offset="0" stop-color="{color}" stop-opacity="0.22"/>'
        f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
        f'<polygon points="{area}" fill="url(#{gid})"/>'
        f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2.5"/>{dots}{xl}</svg>')


def donut(segments, center_label="KEYWORDS"):
    """Donut de distribución (Top 3 / 4-10 / ... ) estilo SE Ranking."""
    total = sum(s["value"] for s in segments) or 1
    r = 52
    circ = 2 * 3.14159 * r
    off = 0.0
    arcs = ""
    for s in segments:
        dash = (s["value"] / total) * circ
        arcs += (f'<circle cx="70" cy="70" r="{r}" fill="none" stroke="{s["color"]}" stroke-width="15" '
                 f'stroke-dasharray="{dash:.1f} {circ - dash:.1f}" stroke-dashoffset="{-off:.1f}" '
                 f'transform="rotate(-90 70 70)"/>')
        off += dash
    return (f'<svg viewBox="0 0 140 140" width="140" height="140" xmlns="http://www.w3.org/2000/svg">{arcs}'
            f'<text x="70" y="66" text-anchor="middle" font-family="Sora,sans-serif" font-size="26" font-weight="800" fill="#0e1319">{int(total)}</text>'
            f'<text x="70" y="84" text-anchor="middle" font-family="JetBrains Mono,monospace" font-size="8" fill="#7b8694">{center_label}</text></svg>')


def render_html(context):
    tpl = _env.get_template("report_justificacion.html")
    context.setdefault("fmt", _fmt)
    context.setdefault("bar_chart", bar_chart)
    return tpl.render(**context)


def render_seranking(context):
    """Informe SEO completo estilo SE Ranking, con marca Cupperlab."""
    tpl = _env.get_template("report_seranking.html")
    context.setdefault("fmt", _fmt)
    context.setdefault("bar_chart", bar_chart)
    context.setdefault("area_chart", area_chart)
    context.setdefault("donut", donut)
    context.setdefault("logo_uri", logo_uri())
    return tpl.render(**context)


def html_to_pdf(html_string, pdf_path):
    """Escribe el HTML a disco y lo imprime a PDF con Chromium."""
    html_path = pdf_path.replace(".pdf", ".html")
    # Las rutas de assets (logo, css) se resuelven relativas al archivo HTML,
    # así que escribimos el HTML en la carpeta de reports junto a /assets.
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_string)
    url = "file:///" + html_path.replace("\\", "/")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        page.pdf(
            path=pdf_path,
            format="A4",
            print_background=True,
            margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
        )
        browser.close()
    return pdf_path
