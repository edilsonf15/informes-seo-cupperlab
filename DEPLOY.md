# Despliegue en producción — informes.cupperlab.com

Servidor: 217.154.106.223 (no se reemplaza nada existente; se monta un proyecto nuevo).
Objetivo: la app corriendo en el subdominio **https://informes.cupperlab.com** con SSL.

La app es un servicio Python (Flask) que escucha en un puerto local (ej. 8000) y se publica
detrás de Nginx/Plesk con HTTPS. El tráfico va: navegador → HTTPS (Plesk/Nginx) → 127.0.0.1:8000 (gunicorn).

---

## A. Subdominio + SSL (en Plesk)

1. Plesk → **Dominios → Añadir subdominio** → `informes.cupperlab.com`.
2. Plesk → ese subdominio → **Certificados SSL/TLS → Let's Encrypt** → emitir (marca "proteger el subdominio").
3. Deja activado "Redirección permanente de HTTP a HTTPS".

## B. Código y dependencias

```bash
# En el servidor, en la carpeta del subdominio (ej. /var/www/vhosts/cupperlab.com/informes/)
git clone <repo>  ó  sube la carpeta "Informe SEO"  (sin la carpeta data/)
cd informes
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt gunicorn
python -m playwright install chromium
python -m playwright install-deps        # dependencias del sistema para Chromium
```

## C. Variables de entorno (crea un archivo .env y cárgalo, o ponlas en el servicio)

```bash
FLASK_SECRET_KEY="<cadena larga aleatoria>"
FLASK_APP_PASSWORD="<contraseña fuerte para entrar a la app>"
OAUTH_REDIRECT_URI="https://informes.cupperlab.com/oauth2callback"
```

## D. Servicio (gunicorn con systemd)

Crea `/etc/systemd/system/informes-seo.service`:

```ini
[Unit]
Description=Informes SEO Cupperlab
After=network.target

[Service]
WorkingDirectory=/var/www/vhosts/cupperlab.com/informes
Environment="FLASK_SECRET_KEY=..." "FLASK_APP_PASSWORD=..." "OAUTH_REDIRECT_URI=https://informes.cupperlab.com/oauth2callback"
ExecStart=/var/www/vhosts/cupperlab.com/informes/.venv/bin/gunicorn -w 2 -b 127.0.0.1:8000 --timeout 180 wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now informes-seo
```

> `--timeout 180`: la generación del PDF y el rastreo pueden tardar; no bajar de 120.

## E. Proxy inverso (Plesk → Apache/Nginx)

En Plesk → subdominio → **Configuración de Apache y nginx** → en "Directivas de nginx adicionales":

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 180s;
}
```

(Alternativa sin systemd: usar el soporte "Python" de Plesk con Passenger apuntando a `wsgi.py`
y `application` como callable; en ese caso no hace falta gunicorn ni el servicio.)

## F. Google Cloud (añadir el redirect de producción)

En el ID de cliente OAuth, además de `http://localhost:5000/oauth2callback`, añade:
`https://informes.cupperlab.com/oauth2callback`

## G. Datos

La carpeta `data/` (base de datos, credenciales, PDFs) vive en el servidor y NO se sube a git.
Sube `data/credentials/client_secret.json` por SFTP a esa carpeta. Haz copia de `data/app.db`
periódicamente (contiene proyectos y conexiones).
