"""Flujo OAuth con Google y gestión de credenciales de solo lectura.

Una sola autorización por cuenta de Google sirve para TODAS las webs (propiedades
de GA4 y sitios de Search Console) a las que esa cuenta tenga acceso, igual que
hacía SE Ranking.
"""
import os
import json

# En desarrollo local usamos http://localhost, que no es https. Esto lo permite.
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
# Evita que oauthlib falle si Google devuelve los permisos en otro orden.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from . import config, db


def build_flow(state=None):
    flow = Flow.from_client_secrets_file(
        config.CLIENT_SECRET_FILE, scopes=config.SCOPES, state=state
    )
    flow.redirect_uri = config.REDIRECT_URI
    return flow


def authorization_url():
    flow = build_flow()
    url, state = flow.authorization_url(
        access_type="offline",      # para obtener refresh_token (datos sin re-login)
        include_granted_scopes="true",
        prompt="consent",            # fuerza refresh_token también en reconexiones
    )
    # PKCE: hay que conservar el code_verifier para el callback.
    return url, state, flow.code_verifier


def finish_and_store(state, authorization_response_url, code_verifier=None):
    """Intercambia el código por un token, averigua el email y lo guarda."""
    flow = build_flow(state=state)
    if code_verifier:
        flow.code_verifier = code_verifier
    flow.fetch_token(authorization_response=authorization_response_url)
    creds = flow.credentials
    email = _fetch_email(creds)
    account_id = db.upsert_account(email, creds.to_json())
    return account_id, email


def _fetch_email(creds):
    try:
        svc = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        info = svc.userinfo().get().execute()
        return info.get("email") or "cuenta-google"
    except Exception:
        return "cuenta-google"


def credentials_for_account(account_id):
    """Carga las credenciales de una cuenta, refrescando el token si hace falta."""
    row = db.get_account(account_id)
    if not row:
        return None
    data = json.loads(row["token_json"])
    creds = Credentials.from_authorized_user_info(data, scopes=config.SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        db.upsert_account(row["email"], creds.to_json())
    return creds
