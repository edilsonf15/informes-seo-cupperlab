"""Configuración central de la aplicación."""
import os
import secrets

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CRED_DIR = os.path.join(DATA_DIR, "credentials")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
DB_PATH = os.path.join(DATA_DIR, "app.db")

# El cliente OAuth que descargas de Google Cloud va aquí (ver README).
CLIENT_SECRET_FILE = os.path.join(CRED_DIR, "client_secret.json")

# Permisos de SOLO LECTURA. No permiten modificar nada en las cuentas de Google.
SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",   # GA4
    "https://www.googleapis.com/auth/webmasters.readonly",  # Search Console
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",       # para saber qué cuenta se conectó
]

# Debe coincidir EXACTAMENTE con el "URI de redirección autorizado" en Google Cloud.
REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:5000/oauth2callback")

# Clave de sesión: por entorno en producción; si no, se genera aleatoria (segura).
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

# Contraseña para entrar a la app. En producción se define con FLASK_APP_PASSWORD.
# El valor por defecto es solo para uso local.
APP_PASSWORD = os.environ.get("FLASK_APP_PASSWORD", "cupperlab")

# Marca y textos por defecto del informe (se pueden cambiar al generar).
AGENCIA = "Cupperlab"
TITULO_INFORME = "MODELO COMPILACIÓN DE EVIDENCIAS"

for _d in (DATA_DIR, CRED_DIR, REPORTS_DIR):
    os.makedirs(_d, exist_ok=True)

# En producción (Dokploy/servidor) es más cómodo pasar el client_secret como variable
# de entorno en vez de subir el archivo. Si está la variable y no existe el archivo, se crea.
_cs_env = os.environ.get("GOOGLE_CLIENT_SECRET_JSON")
if _cs_env and not os.path.exists(CLIENT_SECRET_FILE):
    try:
        with open(CLIENT_SECRET_FILE, "w", encoding="utf-8") as _f:
            _f.write(_cs_env)
    except Exception:
        pass


def client_secret_exists() -> bool:
    return os.path.exists(CLIENT_SECRET_FILE)
