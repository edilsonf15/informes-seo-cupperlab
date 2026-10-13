"""Renderizado del informe: HTML (Jinja) -> PDF (Playwright/Chromium)."""
import os
import base64
from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright
from . import config

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
