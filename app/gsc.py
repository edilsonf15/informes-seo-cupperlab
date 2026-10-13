"""Cliente de Google Search Console vía API REST.

Cubre lo que antes salía de Sistrix (keywords y posiciones, pero con datos REALES
de la propia web) y la evolución mensual de clics/impresiones.
"""
from collections import defaultdict
from googleapiclient.discovery import build


def _svc(creds):
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


def list_sites(creds):
    """Sitios verificados en Search Console a los que tiene acceso la cuenta."""
    resp = _svc(creds).sites().list().execute()
    out = []
    for s in resp.get("siteEntry", []):
        out.append({"site": s.get("siteUrl"), "permission": s.get("permissionLevel")})
    return out


def _query(creds, site, start, end, dimensions, row_limit=25000):
    body = {
        "startDate": start,
        "endDate": end,
        "dimensions": dimensions,
        "rowLimit": row_limit,
    }
    return _svc(creds).searchanalytics().query(siteUrl=site, body=body).execute()


def totals(creds, site, start, end):
    resp = _query(creds, site, start, end, dimensions=[], row_limit=1)
    rows = resp.get("rows", [])
    if not rows:
        return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
    r = rows[0]
    return {
        "clicks": int(r.get("clicks", 0)),
        "impressions": int(r.get("impressions", 0)),
        "ctr": round(r.get("ctr", 0) * 100, 2),
        "position": round(r.get("position", 0), 1),
    }


def keywords(creds, site, start, end, limit=1000):
    """Lista de consultas (keywords) reales por las que aparece la web en Google."""
    resp = _query(creds, site, start, end, dimensions=["query"], row_limit=limit)
    out = []
    for r in resp.get("rows", []):
        out.append({
            "query": r["keys"][0],
            "clicks": int(r.get("clicks", 0)),
            "impressions": int(r.get("impressions", 0)),
            "ctr": round(r.get("ctr", 0) * 100, 2),
            "position": round(r.get("position", 0), 1),
        })
    return out


def top_pages(creds, site, start, end, limit=50):
    resp = _query(creds, site, start, end, dimensions=["page"], row_limit=limit)
    out = []
    for r in resp.get("rows", []):
        out.append({
            "page": r["keys"][0],
            "clicks": int(r.get("clicks", 0)),
            "impressions": int(r.get("impressions", 0)),
            "position": round(r.get("position", 0), 1),
        })
    return out


def monthly(creds, site, start, end):
    """Agrega por mes los datos diarios (Search Console no da dimensión 'mes')."""
    resp = _query(creds, site, start, end, dimensions=["date"], row_limit=25000)
    agg = defaultdict(lambda: {"clicks": 0, "impressions": 0, "pos_sum": 0.0, "n": 0})
    for r in resp.get("rows", []):
        day = r["keys"][0]            # 'YYYY-MM-DD'
        month = day[:7]               # 'YYYY-MM'
        a = agg[month]
        a["clicks"] += int(r.get("clicks", 0))
        a["impressions"] += int(r.get("impressions", 0))
        a["pos_sum"] += r.get("position", 0)
        a["n"] += 1
    rows = []
    for month in sorted(agg):
        a = agg[month]
        rows.append({
            "month": month,
            "clicks": a["clicks"],
            "impressions": a["impressions"],
            "position": round(a["pos_sum"] / a["n"], 1) if a["n"] else 0.0,
        })
    return rows


def daily(creds, site, start, end):
    """Serie diaria de clics/impresiones/posición (para la gráfica de evolución por fechas)."""
    resp = _query(creds, site, start, end, dimensions=["date"], row_limit=25000)
    rows = []
    for r in resp.get("rows", []):
        rows.append({
            "date": r["keys"][0],                     # 'YYYY-MM-DD'
            "clicks": int(r.get("clicks", 0)),
            "impressions": int(r.get("impressions", 0)),
            "position": round(r.get("position", 0), 1),
        })
    rows.sort(key=lambda x: x["date"])
    return rows


def coverage(creds, site):
    """Sitemaps enviados a Search Console (enviadas vs indexadas por Google)."""
    try:
        resp = _svc(creds).sitemaps().list(siteUrl=site).execute()
    except Exception:
        return []
    out = []
    for s in resp.get("sitemap", []):
        contents = s.get("contents", [{}])[0]
        out.append({
            "path": s.get("path"),
            "submitted": int(contents.get("submitted", 0)),
            "indexed": int(contents.get("indexed", 0)),
            "errors": int(s.get("errors", 0)),
            "warnings": int(s.get("warnings", 0)),
        })
    return out
