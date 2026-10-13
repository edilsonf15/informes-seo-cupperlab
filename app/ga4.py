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


def monthly_report(creds, property_id, start_date, end_date):
    """Evolución mensual. property_id puede venir como 'properties/123' o '123'."""
    pid = property_id if property_id.startswith("properties/") else f"properties/{property_id}"
    svc = _data(creds)
    body = {
        "dateRanges": [{"startDate": start_date, "endDate": end_date}],
        "dimensions": [{"name": "yearMonth"}],
        "metrics": [
            {"name": "sessions"},
            {"name": "totalUsers"},
            {"name": "newUsers"},
            {"name": "screenPageViews"},
            {"name": "averageSessionDuration"},
        ],
        "orderBys": [{"dimension": {"dimensionName": "yearMonth"}}],
        "limit": 100000,
    }
    resp = svc.properties().runReport(property=pid, body=body).execute()
    rows = []
    for r in resp.get("rows", []):
        ym = r["dimensionValues"][0]["value"]  # '202507'
        vals = [m["value"] for m in r["metricValues"]]
        rows.append({
            "month": f"{ym[:4]}-{ym[4:]}",
            "sessions": int(float(vals[0])),
            "users": int(float(vals[1])),
            "new_users": int(float(vals[2])),
            "pageviews": int(float(vals[3])),
            "avg_duration": round(float(vals[4]), 1),
        })
    totals = {
        "sessions": sum(x["sessions"] for x in rows),
        "users": sum(x["users"] for x in rows),
        "new_users": sum(x["new_users"] for x in rows),
        "pageviews": sum(x["pageviews"] for x in rows),
    }
    return {"rows": rows, "totals": totals}
