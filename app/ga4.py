"""Cliente de Google Analytics 4 (GA4) vía API REST.

- list_properties: lista las propiedades GA4 a las que tiene acceso la cuenta.
- monthly_report: evolución mes a mes del periodo (sesiones, usuarios, etc.).
"""
from googleapiclient.discovery import build


def _admin(creds):
    return build("analyticsadmin", "v1beta", credentials=creds, cache_discovery=False)


def _data(creds):
    return build("analyticsdata", "v1beta", credentials=creds, cache_discovery=False)


def list_properties(creds):
    """Devuelve [{'property': 'properties/123', 'display': 'Nombre (cuenta)'}]."""
    svc = _admin(creds)
    out = []
    page_token = None
    while True:
        resp = svc.accountSummaries().list(pageToken=page_token).execute()
        for acc in resp.get("accountSummaries", []):
            acc_name = acc.get("displayName", "")
            for prop in acc.get("propertySummaries", []):
                out.append({
                    "property": prop.get("property"),           # 'properties/123'
                    "display": f"{prop.get('displayName','')}  ·  {acc_name}",
                })
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


# Métricas GA4 (mismas tarjetas que el informe de Looker Studio del cliente)
_METRICS = [
    "sessions", "engagedSessions", "totalUsers", "activeUsers", "newUsers",
    "screenPageViews", "conversions", "userEngagementDuration", "engagementRate",
]


def monthly_report(creds, property_id, start_date, end_date):
    """Evolución mensual. property_id puede venir como 'properties/123' o '123'."""
    pid = property_id if property_id.startswith("properties/") else f"properties/{property_id}"
    svc = _data(creds)
    body = {
        "dateRanges": [{"startDate": start_date, "endDate": end_date}],
        "dimensions": [{"name": "yearMonth"}],
        "metrics": [{"name": m} for m in _METRICS],
        "orderBys": [{"dimension": {"dimensionName": "yearMonth"}}],
        "limit": 100000,
    }
    resp = svc.properties().runReport(property=pid, body=body).execute()
    rows = []
    for r in resp.get("rows", []):
        ym = r["dimensionValues"][0]["value"]  # '202507'
        v = {_METRICS[i]: float(m["value"]) for i, m in enumerate(r["metricValues"])}
        rows.append({
            "month": f"{ym[:4]}-{ym[4:]}",
            "sessions": int(v["sessions"]),
            "engaged_sessions": int(v["engagedSessions"]),
            "users": int(v["totalUsers"]),
            "new_users": int(v["newUsers"]),
            "pageviews": int(v["screenPageViews"]),
            "conversions": int(v["conversions"]),
        })

    def s(k):
        return sum(x[k] for x in rows)

    # Totales (de todo el periodo) pidiendo una fila agregada
    body2 = {
        "dateRanges": [{"startDate": start_date, "endDate": end_date}],
        "metrics": [{"name": m} for m in _METRICS],
    }
    tr = svc.properties().runReport(property=pid, body=body2).execute().get("rows", [])
    tv = {_METRICS[i]: float(m["value"]) for i, m in enumerate(tr[0]["metricValues"])} if tr else {}
    sessions = int(tv.get("sessions", 0))
    users = int(tv.get("totalUsers", 0))
    active = int(tv.get("activeUsers", 0)) or users
    engaged = int(tv.get("engagedSessions", 0))
    totals = {
        "sessions": sessions,
        "engaged_sessions": engaged,
        "users": users,
        "new_users": int(tv.get("newUsers", 0)),
        "pageviews": int(tv.get("screenPageViews", 0)),
        "conversions": int(tv.get("conversions", 0)),
        # tasa de interacción (%)
        "engagement_rate": round(tv.get("engagementRate", (engaged / sessions if sessions else 0)) * 100, 2),
        # % de usuarios nuevos
        "new_users_pct": round(int(tv.get("newUsers", 0)) / users * 100, 2) if users else 0,
        # tiempo promedio de interacción por usuario (seg)
        "avg_engagement_sec": round(tv.get("userEngagementDuration", 0) / active, 1) if active else 0,
    }
    sec = totals["avg_engagement_sec"]
    totals["avg_engagement_fmt"] = (f"{int(sec // 60)} min {int(sec % 60)} s" if sec >= 60
                                    else f"{sec} seg")
    return {"rows": rows, "totals": totals}
