"""Rastreador propio: reemplaza Screaming Frog para la sección de indexación.

Descarga el sitemap, clasifica las URLs (páginas reales, etiquetas, fichas de
archivo, noticias...) y comprueba el código HTTP (200/301/404) y la indexabilidad
(index / noindex) de una muestra. Pensado para correr acotado en tiempo.

Lecciones de producción respetadas:
 - concurrencia MODERADA (8 hilos), timeout 10 s, 1 reintento;
 - errores de conexión se marcan 'ERR', NO se cuentan como 404;
 - con miles de URLs se comprueba una muestra representativa por tipo.
"""
import re
import time
import requests
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from lxml import etree

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CupperlabSEO/1.0; +https://cupperlab.com)"}
TIMEOUT = 10
MAX_WORKERS = 8
SM_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _norm(domain: str) -> str:
    domain = domain.strip()
    if not domain.startswith("http"):
        domain = "https://" + domain
    return domain.rstrip("/")


def _get(url, allow_redirects=False):
    for attempt in range(2):
        try:
            return requests.get(url, headers=HEADERS, timeout=TIMEOUT,
                                 allow_redirects=allow_redirects)
        except requests.RequestException:
            if attempt == 0:
                time.sleep(0.4)
                continue
            return None
    return None


def _fetch_sitemap_urls(base):
    """Devuelve (lista_urls, sub_sitemaps[{name,count}]). Soporta sitemap index."""
    candidates = [base + "/sitemap_index.xml", base + "/sitemap.xml"]
    urls, subs = [], []
    seen = set()
    root_sitemaps = []
    for c in candidates:
        r = _get(c, allow_redirects=True)
        if r is not None and r.status_code == 200 and b"<" in r.content:
            root_sitemaps.append((c, r.content))
            break
    if not root_sitemaps:
        return urls, subs

    _, content = root_sitemaps[0]
    try:
        tree = etree.fromstring(content)
    except Exception:
        return urls, subs

    tag = etree.QName(tree).localname
    if tag == "sitemapindex":
        for loc in tree.findall(".//sm:sitemap/sm:loc", SM_NS):
            sm_url = (loc.text or "").strip()
            if not sm_url:
                continue
            rr = _get(sm_url, allow_redirects=True)
            if rr is None or rr.status_code != 200:
                subs.append({"name": sm_url, "count": 0})
                continue
            try:
                sub = etree.fromstring(rr.content)
            except Exception:
                continue
            locs = [(l.text or "").strip() for l in sub.findall(".//sm:url/sm:loc", SM_NS)]
            locs = [u for u in locs if u]
            subs.append({"name": sm_url, "count": len(locs)})
            for u in locs:
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
    else:  # urlset directo
        locs = [(l.text or "").strip() for l in tree.findall(".//sm:url/sm:loc", SM_NS)]
        locs = [u for u in locs if u]
        subs.append({"name": root_sitemaps[0][0], "count": len(locs)})
        for u in locs:
            if u not in seen:
                seen.add(u)
                urls.append(u)
    return urls, subs


def _classify(url: str) -> str:
    u = url.lower()
    if re.search(r"/(tag|etiqueta|etiquetas)/", u):
        return "Etiquetas / tags"
    if re.search(r"(wpfd_file|/download/|\.pdf$|/descargas?/)", u):
        return "Fichas / archivos"
    if re.search(r"/(category|categoria|categorias)/", u):
        return "Categorías"
    if re.search(r"/\d{4}/\d{2}/", u) or "/noticia" in u or "/blog/" in u:
        return "Noticias / blog"
    return "Páginas reales"


def _check_url(url):
    r = _get(url, allow_redirects=False)
    if r is None:
        return {"url": url, "status": "ERR", "code": 0, "indexable": None, "type": _classify(url)}
    code = r.status_code
    indexable = None
    if code == 200 and "text/html" in r.headers.get("Content-Type", ""):
        xrobots = r.headers.get("X-Robots-Tag", "").lower()
        body = r.text[:200000].lower()
        m = re.search(r'<meta[^>]+name=["\']robots["\'][^>]*>', body)
        meta = m.group(0) if m else ""
        noindex = "noindex" in xrobots or "noindex" in meta
        indexable = not noindex
    return {
        "url": url,
        "status": "OK" if code == 200 else ("REDIR" if 300 <= code < 400 else ("404" if code == 404 else str(code))),
        "code": code,
        "indexable": indexable,
        "type": _classify(url),
    }


def audit(domain: str, max_urls: int = 180, time_budget: float = 40.0):
    """Audita el dominio. Devuelve composición del sitemap, muestra de URLs y 404s."""
    base = _norm(domain)
    started = time.time()
    all_urls, subs = _fetch_sitemap_urls(base)

    # Composición por tipo (sobre el total real del sitemap)
    composition = {}
    for u in all_urls:
        t = _classify(u)
        composition[t] = composition.get(t, 0) + 1

    # Si no hay sitemap, al menos comprueba la home y rutas típicas
    if not all_urls:
        all_urls = [base + p for p in ["/", "/contacto", "/servicios", "/sobre-nosotros"]]

    # Muestra representativa: reparte el presupuesto entre tipos
    sample = _representative_sample(all_urls, max_urls)

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_check_url, u): u for u in sample}
        for fut in as_completed(futs):
            if time.time() - started > time_budget:
                break
            try:
                results.append(fut.result())
            except Exception:
                pass

    codes = {"OK": 0, "REDIR": 0, "404": 0, "ERR": 0, "otros": 0}
    for r in results:
        if r["status"] == "OK":
            codes["OK"] += 1
        elif r["status"] == "REDIR":
            codes["REDIR"] += 1
        elif r["status"] == "404":
            codes["404"] += 1
        elif r["status"] == "ERR":
            codes["ERR"] += 1
        else:
            codes["otros"] += 1

    broken = [r for r in results if r["status"] == "404"][:6]
    indexables = sum(1 for r in results if r["indexable"] is True)
    noindex = sum(1 for r in results if r["indexable"] is False)

    return {
        "base": base,
        "total_sitemap": len(all_urls),
        "subsitemaps": subs,
        "composition": [{"type": k, "count": v} for k, v in sorted(composition.items(), key=lambda x: -x[1])],
        "checked": len(results),
        "codes": codes,
        "broken_examples": [b["url"] for b in broken],
        "indexable_count": indexables,
        "noindex_count": noindex,
        "sample": sorted(results, key=lambda r: (r["type"], r["url"]))[:120],
        "elapsed": round(time.time() - started, 1),
    }


def _representative_sample(urls, max_urls):
    by_type = {}
    for u in urls:
        by_type.setdefault(_classify(u), []).append(u)
    if sum(len(v) for v in by_type.values()) <= max_urls:
        return urls
    per = max(5, max_urls // max(1, len(by_type)))
    sample = []
    for t, lst in by_type.items():
        sample.extend(lst[:per])
    return sample[:max_urls]
