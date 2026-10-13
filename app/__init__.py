"""Fábrica de la aplicación Flask."""
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from . import config, db


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    # Detrás del proxy del servidor (Dokploy/Traefik): respeta https y el host reales,
    # imprescindible para que OAuth con Google funcione en producción.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    db.init_db()

    from .routes import bp
    app.register_blueprint(bp)
    return app
