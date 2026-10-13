# Imagen de producción para Dokploy.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Navegador Chromium + sus dependencias del sistema (para generar el PDF)
RUN playwright install --with-deps chromium

# Código de la app
COPY . .

# Carpeta de datos persistente (se monta como volumen en Dokploy)
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8000

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "--timeout", "180", "wsgi:application"]
