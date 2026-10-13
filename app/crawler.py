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
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from lxml import etree
import lxml.html

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


# ============================================================
#  SITE AUDIT (estilo SE Ranking) — auditoría técnica on-page
# ============================================================
def _audit_one(url):
    """Descarga una URL y extrae sus señales SEO on-page."""
    t0 = time.time()
    r = _get(url, allow_redirects=False)
    if r is None:
        return {"url": url, "status": 0, "state": "ERR"}
    resp_ms = int((time.time() - t0) * 1000)
    code = r.status_code
    info = {
        "url": url, "status": code, "resp_ms": resp_ms,
        "state": "OK" if code == 200 else ("REDIR" if 300 <= code < 400 else "BROKEN" if code >= 400 else "OTHER"),
        "redirect_to": r.headers.get("Location", "") if 300 <= code < 400 else "",
        "title": "", "title_len": 0, "meta_desc": "", "md_len": 0,
        "h1_count": 0, "canonical": "", "indexable": None,
        "words": 0, "imgs": 0, "imgs_noalt": 0, "int_links": 0, "ext_links": 0,
        "is_html": "text/html" in r.headers.get("Content-Type", ""),
    }
    if code == 200 and info["is_html"]:
        try:
            doc = lxml.html.fromstring(r.content)
        except Exception:
            return info
        host = urlparse(url).netloc
        title = (doc.findtext(".//title") or "").strip()
        info["title"] = title[:200]; info["title_len"] = len(title)
        md = doc.xpath('//meta[@name="description"]/@content')
        md = (md[0] if md else "").strip()
        info["meta_desc"] = md[:300]; info["md_len"] = len(md)
        info["h1_count"] = len(doc.xpath("//h1"))
        can = doc.xpath('//link[@rel="canonical"]/@href')
        info["canonical"] = (can[0] if can else "")
        robots = " ".join(doc.xpath('//meta[@name="robots"]/@content')).lower()
        xrobots = r.headers.get("X-Robots-Tag", "").lower()
        info["indexable"] = not ("noindex" in robots or "noindex" in xrobots)
        imgs = doc.xpath("//img")
        info["imgs"] = len(imgs)
        info["imgs_noalt"] = sum(1 for im in imgs if not (im.get("alt") or "").strip())
        text = doc.text_content() or ""
        info["words"] = len(text.split())
        for a in doc.xpath("//a/@href"):
            if a.startswith("#") or a.startswith("mailto:") or a.startswith("tel:"):
                continue
            netloc = urlparse(urljoin(url, a)).netloc
            if netloc == host or not netloc:
                info["int_links"] += 1
            else:
                info["ext_links"] += 1
    return info


def site_audit(domain, max_urls=120, time_budget=48.0):
    """Auditoría técnica tipo SE Ranking: rastrea y puntúa la salud on-page."""
    base = _norm(domain)
    started = time.time()
    all_urls, _subs = _fetch_sitemap_urls(base)
    if not all_urls:
        all_urls = [base + "/"]
    sample = _representative_sample(all_urls, max_urls)
    if base + "/" not in sample:
        sample = [base + "/"] + sample

    pages = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_audit_one, u): u for u in sample}
        for fut in as_completed(futs):
            if time.time() - started > time_budget:
                break
            try:
                pages.append(fut.result())
            except Exception:
                pass

    html_pages = [p for p in pages if p.get("state") == "OK" and p.get("is_html")]
    n = max(1, len(html_pages))
    crawled = len(pages)

    def urls_with(pred, src=None):
        return [p["url"] for p in (src or html_pages) if pred(p)]

    broken = urls_with(lambda p: p["state"] == "BROKEN", pages)
    server_err = urls_with(lambda p: p["status"] >= 500, pages)
    redirects = urls_with(lambda p: p["state"] == "REDIR", pages)
    no_title = urls_with(lambda p: p["title_len"] == 0)
    long_title = urls_with(lambda p: p["title_len"] > 60)
    short_title = urls_with(lambda p: 0 < p["title_len"] < 30)
    no_md = urls_with(lambda p: p["md_len"] == 0)
    long_md = urls_with(lambda p: p["md_len"] > 160)
    no_h1 = urls_with(lambda p: p["h1_count"] == 0)
    multi_h1 = urls_with(lambda p: p["h1_count"] > 1)
    noindex = urls_with(lambda p: p["indexable"] is False)
    low_words = urls_with(lambda p: p["words"] < 200)
    imgs_noalt = urls_with(lambda p: p["imgs_noalt"] > 0)
    slow = urls_with(lambda p: p["resp_ms"] > 3000)
    no_canonical = urls_with(lambda p: not p["canonical"])

    # Títulos duplicados
    seen = {}
    for p in html_pages:
        if p["title"]:
            seen.setdefault(p["title"], []).append(p["url"])
    dup_titles = [u for lst in seen.values() if len(lst) > 1 for u in lst]

    def issue(key, label, sev, urls, weight):
        return {"key": key, "label": label, "sev": sev,
                "count": len(urls), "sample": urls[:8], "weight": weight}

    errors = [i for i in [
        issue("broken", "Páginas con error (4xx)", "error", broken, 25),
        issue("server", "Errores de servidor (5xx)", "error", server_err, 25),
        issue("no_title", "Páginas sin título (title)", "error", no_title, 15),
        issue("no_h1", "Páginas sin encabezado H1", "error", no_h1, 12),
        issue("dup_titles", "Títulos duplicados", "error", dup_titles, 12),
    ] if i["count"]]
    warnings = [i for i in [
        issue("no_md", "Sin meta descripción", "warning", no_md, 10),
        issue("multi_h1", "Más de un H1", "warning", multi_h1, 7),
        issue("long_title", "Título demasiado largo (>60)", "warning", long_title, 6),
        issue("short_title", "Título demasiado corto (<30)", "warning", short_title, 5),
        issue("low_words", "Poco contenido (<200 palabras)", "warning", low_words, 8),
        issue("imgs_noalt", "Imágenes sin atributo alt", "warning", imgs_noalt, 6),
        issue("slow", "Páginas lentas (>3 s)", "warning", slow, 6),
    ] if i["count"]]
    notices = [i for i in [
        issue("long_md", "Meta descripción muy larga (>160)", "notice", long_md, 2),
        issue("redirects", "Redirecciones (3xx)", "notice", redirects, 2),
        issue("noindex", "Páginas noindex", "notice", noindex, 2),
        issue("no_canonical", "Sin etiqueta canonical", "notice", no_canonical, 2),
    ] if i["count"]]

    # Puntuación de salud 0-100
    score = 100.0
    for i in errors + warnings:
        score -= i["weight"] * min(1.0, i["count"] / n)
    score = max(0, round(score))

    return {
        "base": base,
        "crawled": crawled,
        "html_pages": len(html_pages),
        "score": score,
        "counts": {
            "ok": len(html_pages), "broken": len(broken), "redirects": len(redirects),
            "errors": sum(i["count"] for i in errors),
            "warnings": sum(i["count"] for i in warnings),
            "notices": sum(i["count"] for i in notices),
        },
        "errors": errors, "warnings": warnings, "notices": notices,
        "pages": sorted(pages, key=lambda p: (p.get("state") != "BROKEN", p["url"]))[:150],
        "elapsed": round(time.time() - started, 1),
    }
