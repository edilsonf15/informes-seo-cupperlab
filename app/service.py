"""Orquestación: reúne todos los datos de un informe desde sus fuentes."""
from datetime import datetime
from . import db, ga4, gsc, crawler, google_oauth, sistrix

MESES_ES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fecha_larga(iso):
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return f"{d.day} de {MESES_ES[d.month]} de {d.year}"
    except Exception:
        return iso


def keyword_buckets(keywords):
    """Cuenta keywords por tramo de posición (como el 'Número de palabras' de Sistrix)."""
    kws = keywords or []
    def c(lo, hi):
        return sum(1 for k in kws if k.get("position") and lo < k["position"] <= hi)
    return {
        "total": len(kws),
        "top3": sum(1 for k in kws if k.get("position") and k["position"] <= 3),
        "top10": sum(1 for k in kws if k.get("position") and k["position"] <= 10),
        "top100": sum(1 for k in kws if k.get("position") and k["position"] <= 100),
        "pos_4_10": c(3, 10),
        "pos_11_20": c(10, 20),
    }


def dashboard_data(project, start, end):
    """Datos en vivo para el panel (sin rastreo, para que cargue rápido)."""
    data = gather_report_data(project, start, end, include_crawl=False)
    data["buckets"] = keyword_buckets(data.get("keywords"))
    return data


def gather_report_data(project, start, end, include_crawl=True):
    """Reúne datos de GA4, Search Console y rastreo propio. Tolera fuentes no conectadas."""
    data = {
        "warnings": [],
        "ga4": None,
        "gsc_totals": None,
        "gsc_monthly": None,
        "keywords": None,
        "top_pages": None,
        "coverage": None,
        "crawl": None,
        "competition": None,
    }

    creds = None
    if project["account_id"]:
        try:
            creds = google_oauth.credentials_for_account(project["account_id"])
        except Exception as e:
            data["warnings"].append(f"No se pudo cargar la cuenta de Google: {e}")

    # --- GA4 ---
    if creds and project["ga4_property"]:
        try:
            data["ga4"] = ga4.monthly_report(creds, project["ga4_property"], start, end)
        except Exception as e:
            data["warnings"].append(f"Google Analytics (GA4): {e}")
    elif not project["ga4_property"]:
        data["warnings"].append("Sin propiedad GA4 asignada: la sección de tráfico se omite.")

    # --- Search Console ---
    if creds and project["gsc_site"]:
        site = project["gsc_site"]
        try:
            data["gsc_totals"] = gsc.totals(creds, site, start, end)
            data["gsc_monthly"] = gsc.monthly(creds, site, start, end)
            data["keywords"] = gsc.keywords(creds, site, start, end, limit=1000)
            data["top_pages"] = gsc.top_pages(creds, site, start, end, limit=30)
            data["coverage"] = gsc.coverage(creds, site)
        except Exception as e:
            data["warnings"].append(f"Search Console: {e}")
    elif not project["gsc_site"]:
        data["warnings"].append("Sin sitio de Search Console asignado: keywords y posiciones se omiten.")

    # --- Competencia (Sistrix, índice de visibilidad) ---
    competitors = db.project_competitors(project)
    sistrix_key = db.get_setting("sistrix_api_key", "")
    country = db.get_setting("sistrix_country", "es")
    if sistrix_key and competitors:
        try:
            data["competition"] = sistrix.competition(
                sistrix_key, project["domain"], competitors, country=country)
            if data["competition"].get("error"):
                data["warnings"].append(data["competition"]["error"])
        except Exception as e:
            data["warnings"].append(f"Sistrix: {e}")
    elif competitors and not sistrix_key:
        data["warnings"].append("Añade tu clave de Sistrix en Ajustes para el índice de visibilidad.")

    # --- Rastreo propio (indexación / 404) ---
    if include_crawl:
        try:
            data["crawl"] = crawler.audit(project["domain"])
        except Exception as e:
            data["warnings"].append(f"Rastreo de indexación: {e}")

    return data


def build_context(project, start, end, data, client_name, fase, fecha_elaboracion):
    competitors = db.project_competitors(project)
    kw = data.get("keywords") or []
    return {
        "titulo": "MODELO COMPILACIÓN DE EVIDENCIAS",
        "fase": fase,
        "cliente": client_name or project["name"],
        "dominio": project["domain"],
        "periodo_ini": _fecha_larga(start),
        "periodo_fin": _fecha_larga(end),
        "periodo_raw": f"{_short(start)}-{_short(end)}",
        "fecha_elaboracion": _fecha_larga(fecha_elaboracion),
        "data": data,
        "keywords": kw,
        "keywords_count": len(kw),
        "buckets": keyword_buckets(kw),
        "competitors": competitors,
        "generado": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


def _short(iso):
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return d.strftime("%d/%m/%Y")
    except Exception:
        return iso
