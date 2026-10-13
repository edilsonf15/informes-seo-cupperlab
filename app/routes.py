"""Rutas (páginas) de la aplicación."""
import os
import re
import json
from datetime import date, timedelta
from flask import (Blueprint, render_template, request, redirect, url_for,
                   session, flash, send_from_directory, abort)

from . import config, db, google_oauth, ga4, gsc, service, report, crawler

bp = Blueprint("main", __name__)


def _slug(text):
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_") or "informe"


# ---------------- Acceso ----------------
@bp.before_request
def _require_login():
    # Páginas públicas (Google las necesita para verificar la app).
    if request.endpoint in ("main.login", "main.privacy", "main.terms", "static", None):
        return
    if not session.get("auth"):
        return redirect(url_for("main.login"))


@bp.route("/privacidad")
def privacy():
    return render_template("privacy.html")


@bp.route("/terminos")
def terms():
    return render_template("terms.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == config.APP_PASSWORD:
            session["auth"] = True
            return redirect(url_for("main.dashboard"))
        flash("Contraseña incorrecta.", "error")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.pop("auth", None)
    return redirect(url_for("main.login"))


# ---------------- Ajustes ----------------
@bp.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        db.set_setting("sistrix_api_key", request.form.get("sistrix_api_key", "").strip())
        db.set_setting("sistrix_country", request.form.get("sistrix_country", "es").strip() or "es")
        flash("Ajustes guardados.", "ok")
        return redirect(url_for("main.settings"))
    key = db.get_setting("sistrix_api_key", "")
    masked = (key[:4] + "…" + key[-4:]) if len(key) > 8 else ("" if not key else "configurada")
    return render_template("settings.html", sistrix_set=bool(key), masked=masked,
                           country=db.get_setting("sistrix_country", "es"))


# ---------------- Panel ----------------
@bp.route("/")
def dashboard():
    return render_template(
        "dashboard.html",
        projects=db.list_projects(),
        accounts=db.list_accounts(),
        has_client_secret=config.client_secret_exists(),
    )


# ---------------- OAuth con Google ----------------
@bp.route("/connect")
def connect():
    if not config.client_secret_exists():
        flash("Primero sube el archivo client_secret.json de Google Cloud (ver guía).", "error")
        return redirect(url_for("main.dashboard"))
    url, state, code_verifier = google_oauth.authorization_url()
    session["oauth_state"] = state
    session["code_verifier"] = code_verifier
    return redirect(url)


@bp.route("/oauth2callback")
def oauth2callback():
    state = session.get("oauth_state")
    code_verifier = session.get("code_verifier")
    try:
        _, email = google_oauth.finish_and_store(state, request.url, code_verifier)
        flash(f"Cuenta de Google conectada: {email}", "ok")
    except Exception as e:
        flash(f"No se pudo conectar la cuenta: {e}", "error")
    return redirect(url_for("main.dashboard"))


@bp.route("/accounts/<int:account_id>/delete", methods=["POST"])
def delete_account(account_id):
    db.delete_account(account_id)
    flash("Cuenta desconectada.", "ok")
    return redirect(url_for("main.dashboard"))


# ---------------- Proyectos ----------------
@bp.route("/projects/new", methods=["GET", "POST"])
def new_project():
    accounts = db.list_accounts()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        domain = request.form.get("domain", "").strip()
        account_id = request.form.get("account_id") or None
        if not name or not domain:
            flash("Nombre y dominio son obligatorios.", "error")
            return render_template("project_new.html", accounts=accounts)
        pid = db.create_project(name, domain, account_id, None, None, None, [])
        return redirect(url_for("main.configure_project", pid=pid))
    return render_template("project_new.html", accounts=accounts)


@bp.route("/projects/<int:pid>/configure", methods=["GET", "POST"])
def configure_project(pid):
    project = db.get_project(pid)
    if not project:
        abort(404)
    properties, sites, load_error = [], [], None
    if project["account_id"]:
        try:
            creds = google_oauth.credentials_for_account(project["account_id"])
            properties = ga4.list_properties(creds)
            sites = gsc.list_sites(creds)
        except Exception as e:
            load_error = str(e)

    if request.method == "POST":
        ga4_property = request.form.get("ga4_property") or None
        gsc_site = request.form.get("gsc_site") or None
        ga4_name = next((p["display"] for p in properties if p["property"] == ga4_property), None)
        competitors = [c.strip() for c in request.form.get("competitors", "").splitlines() if c.strip()]
        db.update_project(pid, ga4_property=ga4_property, ga4_name=ga4_name,
                          gsc_site=gsc_site, competitors=competitors)
        flash("Proyecto configurado.", "ok")
        return redirect(url_for("main.project_detail", pid=pid))

    return render_template("project_configure.html", project=project,
                           properties=properties, sites=sites, load_error=load_error,
                           competitors="\n".join(db.project_competitors(project)))


@bp.route("/projects/<int:pid>")
def project_detail(pid):
    project = db.get_project(pid)
    if not project:
        abort(404)
    today = date.today()
    # Rango del panel en vivo (por defecto 12 meses).
    try:
        months = int(request.args.get("months", 12))
    except ValueError:
        months = 12
    months = max(1, min(months, 24))
    start = (today - timedelta(days=30 * months)).isoformat()
    end = today.isoformat()

    dash = None
    connected = bool(project["account_id"] and (project["ga4_property"] or project["gsc_site"]))
    if connected:
        try:
            dash = service.dashboard_data(project, start, end)
        except Exception as e:
            flash(f"No se pudo cargar el panel en vivo: {e}", "warn")

    def _dmy(iso):
        return date.fromisoformat(iso).strftime("%d/%m/%Y")

    return render_template("project_detail.html", project=project,
                           competitors=db.project_competitors(project),
                           reports=db.list_reports(pid), today=end,
                           dash=dash, connected=connected, months=months,
                           period_ini=_dmy(start), period_fin=_dmy(end),
                           bar_chart=report.bar_chart, area_chart=report.area_chart,
                           donut=report.donut, fmt=report._fmt)


# ---------------- Site Audit (Módulo 1) ----------------
@bp.route("/projects/<int:pid>/audit")
def audit(pid):
    project = db.get_project(pid)
    if not project:
        abort(404)
    row = db.latest_audit(pid)
    data = json.loads(row["data_json"]) if row else None
    return render_template("audit.html", project=project, audit=data,
                           created_at=(row["created_at"] if row else None),
                           fmt=report._fmt)


@bp.route("/projects/<int:pid>/audit/run", methods=["POST"])
def audit_run(pid):
    project = db.get_project(pid)
    if not project:
        abort(404)
    try:
        result = crawler.site_audit(project["domain"])
        db.save_audit(pid, result["score"], json.dumps(result))
        flash(f"Auditoría completada: salud {result['score']}/100 ({result['crawled']} páginas).", "ok")
    except Exception as e:
        flash(f"No se pudo completar la auditoría: {e}", "error")
    return redirect(url_for("main.audit", pid=pid))


# ---------------- Rank Tracker (Módulo 2) ----------------
@bp.route("/projects/<int:pid>/posiciones")
def ranktracker(pid):
    project = db.get_project(pid)
    if not project:
        abort(404)
    today = date.today()
    try:
        months = int(request.args.get("months", 3))
    except ValueError:
        months = 3
    months = max(1, min(months, 16))
    start = (today - timedelta(days=30 * months)).isoformat()
    end = today.isoformat()
    rank = service.rank_data(project, start, end)
    dist = service.keyword_distribution([{"position": r["position"]} for r in rank.get("rows", [])])
    return render_template("ranktracker.html", project=project, rank=rank, months=months, dist=dist,
                           bar_chart=report.bar_chart, area_chart=report.area_chart,
                           donut=report.donut, fmt=report._fmt)


@bp.route("/projects/<int:pid>/delete", methods=["POST"])
def delete_project(pid):
    db.delete_project(pid)
    flash("Proyecto eliminado.", "ok")
    return redirect(url_for("main.dashboard"))


# ---------------- Generación del informe ----------------
@bp.route("/projects/<int:pid>/generate", methods=["POST"])
def generate(pid):
    project = db.get_project(pid)
    if not project:
        abort(404)
    start = request.form.get("start")
    end = request.form.get("end")
    client_name = request.form.get("client_name", "").strip()
    report_type = request.form.get("report_type", "seo")
    fase = request.form.get("fase", "").strip() or "JUSTIFICACIÓN SITIO WEB Y PRESENCIA EN INTERNET"
    fecha_elaboracion = request.form.get("fecha_elaboracion") or date.today().isoformat()

    try:
        if report_type == "justificacion":
            data = service.gather_report_data(project, start, end)
            ctx = service.build_context(project, start, end, data, client_name, fase, fecha_elaboracion)
            html = report.render_html(ctx)
            prefix = "Justificacion"
        else:
            data = service.report_data_full(project, start, end)
            ctx = service.build_context(project, start, end, data, client_name, fase, fecha_elaboracion)
            html = report.render_seranking(ctx)
            prefix = "Informe_SEO"
        fname = f"{prefix}_{_slug(project['name'])}_{start}_{end}.pdf"
        pdf_path = os.path.join(config.REPORTS_DIR, fname)
        report.html_to_pdf(html, pdf_path)
        db.add_report(pid, fname, start, end)
        warns = data.get("warnings") or []
        if warns:
            flash("Informe generado con avisos: " + " | ".join(warns), "warn")
        else:
            flash("Informe generado correctamente con datos reales.", "ok")
    except Exception as e:
        flash(f"Error al generar el informe: {e}", "error")
    return redirect(url_for("main.project_detail", pid=pid))


@bp.route("/reports/<path:filename>")
def download_report(filename):
    return send_from_directory(config.REPORTS_DIR, filename, as_attachment=False)
