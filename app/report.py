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
