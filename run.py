"""Punto de arranque. Ejecuta:  python run.py   y abre http://localhost:5000"""
import webbrowser
import threading
from app import create_app

app = create_app()

if __name__ == "__main__":
    # Abre el navegador automáticamente al arrancar (solo en local).
    threading.Timer(1.2, lambda: webbrowser.open("http://localhost:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
