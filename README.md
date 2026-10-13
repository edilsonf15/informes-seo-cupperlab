# Informes SEO — Justificación de subvenciones (Cupperlab)

Aplicación propia que **reemplaza SE Ranking, Sistrix y Screaming Frog** para generar la
justificación anual de subvenciones web. Se conecta a **Google Analytics 4** y **Google Search
Console** (datos reales de la propia web) y rastrea el sitio para la indexación y los enlaces rotos.

Funciona **en tu PC** (local) y está preparada para **subirla a un servidor** más adelante sin cambios.

---

## 1. Arrancar la aplicación (local)

Abre PowerShell en esta carpeta y ejecuta:

```bash
C:\Users\edils\AppData\Local\Python\pythoncore-3.14-64\python.exe run.py
```

Se abrirá sola en el navegador: **http://localhost:5000**

> La primera vez, si instalas en otro PC, ejecuta antes:
> `python -m pip install -r requirements.txt` y `python -m playwright install chromium`

---

## 2. Alta en Google Cloud (se hace UNA sola vez)

Para que la app pueda leer Analytics y Search Console necesita unas credenciales OAuth. Esto lo
haces tú en tu cuenta de Google (yo no puedo meter tus credenciales). Pasos:

1. Entra en **https://console.cloud.google.com/** e inicia sesión con la cuenta de la agencia.
2. Crea un proyecto nuevo (arriba, "Seleccionar proyecto" → "Proyecto nuevo"). Llámalo `Informes SEO`.
3. Menú → **APIs y servicios → Biblioteca**. Busca y pulsa **Habilitar** en estas dos:
   - **Google Analytics Data API**
   - **Google Search Console API**
   - (opcional, recomendada) **Google Analytics Admin API** — para listar las propiedades.
4. Menú → **APIs y servicios → Pantalla de consentimiento de OAuth**:
   - Tipo de usuario: **Externo** → Crear.
   - Rellena nombre de la app (`Informes SEO Cupperlab`) y tu correo.
   - En **Usuarios de prueba** añade los correos de Google que vais a usar (el tuyo y el de Víctor).
     Mientras la app esté "en pruebas" solo esos correos pueden conectarse (es suficiente).
5. Menú → **APIs y servicios → Credenciales → Crear credenciales → ID de cliente de OAuth**:
   - Tipo de aplicación: **Aplicación web**.
   - En **URIs de redirección autorizados** añade exactamente:
     `http://localhost:5000/oauth2callback`
   - Crear → **Descargar el JSON**.
6. Renombra ese archivo a **`client_secret.json`** y colócalo en:
   `data/credentials/client_secret.json`
7. Recarga http://localhost:5000 y pulsa **"Conectar cuenta de Google"**.

> Cuando subáis la app a un servidor, repetís solo el punto 5 añadiendo el URI de redirección de ese
> dominio (p. ej. `https://informes.cupperlab.com/oauth2callback`).

---

## 3. Uso

1. **Conecta** una o varias cuentas de Google (las que tengan acceso a los Analytics/Search Console
   de los clientes). Una sola conexión sirve para todas las webs de esa cuenta.
2. **Nuevo proyecto** → nombre de la web + dominio + cuenta de Google.
3. **Configurar fuentes** → elige la propiedad de GA4 y el sitio de Search Console de esa web
   (la app te los lista automáticamente), y opcionalmente los competidores.
4. En la web del proyecto → **Generar informe**: pon el periodo (ej. 24/07/2025 → 24/07/2026) y
   genera. La app lee los datos reales, rastrea el sitio y produce el **PDF de justificación**.

---

## 4. Qué pieza reemplaza a qué

| Antes | Ahora (gratis, datos reales) |
|---|---|
| SE Ranking (tráfico 12 meses) | Google Analytics 4 API |
| Sistrix (keywords, posiciones) | Google Search Console API |
| Screaming Frog (indexación, 404) | Rastreador propio (`app/crawler.py`) |

**Nota honesta:** el "índice de visibilidad" de competidores que daba Sistrix usa datos de terceros
que ninguna API gratuita de Google ofrece (Search Console solo da datos de tus propias webs
verificadas). Por eso esa comparativa se lista con los competidores que indiques; si en el futuro
quieres el índice numérico de competidores habría que añadir una API de pago (DataForSEO, Serpstat).

---

## 5. Estructura

```
run.py                     arranque
app/
  config.py                rutas, permisos OAuth, marca
  db.py                    SQLite (cuentas, proyectos, informes)
  google_oauth.py          login con Google (solo lectura)
  ga4.py                   Google Analytics 4
  gsc.py                   Google Search Console
  crawler.py               rastreo de indexación / 404
  service.py               reúne los datos del informe
  report.py                HTML -> PDF (Playwright)
  templates/               páginas web + plantilla del informe
  static/style.css
data/                      base de datos, credenciales y PDFs (NO se sube a internet)
```

## 6. Subir a internet (más adelante)

La app es un servidor Flask estándar. Para producción: `gunicorn` (Linux) o `waitress` (Windows)
detrás de Nginx, y añadir el URI de redirección del dominio en Google Cloud. La base de datos SQLite
se puede migrar a PostgreSQL si hay mucho volumen. Todo el código ya está preparado para ese salto.
