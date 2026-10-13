"""Cliente de la API de SISTRIX: índice de visibilidad para la sección de competencia.

Es la única pieza del informe que no da Google gratis. La clave (API key) se saca en
sistrix.com -> Cuenta -> Acceso API, y se guarda en Ajustes de la app.
Coste: 1 crédito por línea de resultado (muy barato frente a la suscripción).
"""
import requests

BASE = "https://api.sistrix.com"
TIMEOUT = 20


def visibility_index(api_key, domain, country="es", history=False, num=24):
    """Devuelve [{'date': 'YYYY-MM-DD', 'value': float}] para un dominio.

    history=False -> solo el valor más reciente. history=True -> hasta `num` valores.
    """
    domain = domain.replace("https://", "").replace("http://", "").strip("/ ")
    params = {
        "api_key": api_key,
        "domain": domain,
        "country": country,
        "format": "json",
    }
    if history:
        params["history"] = "true"
        params["num"] = num
    r = requests.get(f"{BASE}/domain.sichtbarkeitsindex", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    # La respuesta JSON trae una lista bajo la clave del método.
    rows = []
    node = _extract_vi_list(data)
    for item in node:
        val = item.get("value")
        if val is None:
            continue
        rows.append({"date": item.get("date", ""), "value": float(val)})
    rows.sort(key=lambda x: x["date"])
    return rows


def _extract_vi_list(data):
    """Normaliza la respuesta JSON de Sistrix a una lista de {date,value}."""
    if isinstance(data, dict):
        # formatos habituales: {'answer':[{'sichtbarkeitsindex':[...]}]} o {'sichtbarkeitsindex':[...]}
        if "answer" in data and isinstance(data["answer"], list):
            out = []
            for a in data["answer"]:
                out.extend(_extract_vi_list(a))
            return out
        for k in ("sichtbarkeitsindex", "visibilityindex", "domain.sichtbarkeitsindex"):
            if k in data and isinstance(data[k], list):
                return data[k]
        # a veces viene como lista de pares
        return []
    if isinstance(data, list):
        out = []
        for a in data:
            out.extend(_extract_vi_list(a))
        return out
    return []


def competition(api_key, beneficiary, competitors, country="es", history=True):
    """Visibilidad del beneficiario + competidores. Tolera fallos por dominio."""
    out = {"beneficiary": beneficiary, "country": country, "series": [], "error": None}
    domains = [beneficiary] + list(competitors or [])
    try:
        for i, d in enumerate(domains):
            rows = visibility_index(api_key, d, country=country, history=history)
            latest = rows[-1]["value"] if rows else 0.0
            out["series"].append({
                "domain": d,
                "is_beneficiary": (i == 0),
                "latest": round(latest, 4),
                "history": rows,
            })
    except requests.HTTPError as e:
        out["error"] = f"Sistrix respondió {e.response.status_code}. Revisa la API key o los créditos."
    except Exception as e:
        out["error"] = f"No se pudo consultar Sistrix: {e}"
    return out
