"""Punto de entrada para producción (gunicorn / passenger / waitress).

Ejemplos:
  Linux:   gunicorn -w 2 -b 127.0.0.1:8000 wsgi:application
  Windows: waitress-serve --listen=127.0.0.1:8000 wsgi:application

Variables de entorno recomendadas en producción:
  FLASK_SECRET_KEY        clave larga y aleatoria (sesiones)
  FLASK_APP_PASSWORD      contraseña de acceso a la app
  OAUTH_REDIRECT_URI      https://informes.cupperlab.com/oauth2callback
"""
from app import create_app

application = create_app()
app = application  # alias por si el servidor busca 'app'

if __name__ == "__main__":
    application.run(host="127.0.0.1", port=8000)
