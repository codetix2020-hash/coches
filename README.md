# Cazachollos 🚗

Sistema personal para encontrar coches de segunda mano por debajo de mercado y revenderlos con margen.

> **Uso exclusivamente personal** · No salta captchas ni inicia sesión en portales. Lee datos de correo electrónico y ficheros exportados.

---

## Instalación rápida (Windows)

```powershell
# 1. Abre PowerShell y ve a la carpeta del proyecto
cd C:\Users\bruno\proyectos\cazachollos-coches

# 2. Activa el entorno virtual (solo la primera vez o si cierras la terminal)
.venv\Scripts\Activate.ps1

# 3. Comprueba que todo funciona
python -m cazachollos init
```

Si PowerShell dice que la ejecución de scripts está desactivada, ejecuta esto una vez:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## Primeros pasos: probar con datos de demo

```powershell
# Carga 25 anuncios ficticios y muestra los resultados
python -m cazachollos demo

# Abre el panel web (se abre el navegador automáticamente)
python -m cazachollos dashboard
```

---

## Comandos disponibles

| Comando | Qué hace |
|---------|---------|
| `python -m cazachollos init` | Crea la BD y muestra tu configuración |
| `python -m cazachollos demo` | Carga datos de prueba y evalúa |
| `python -m cazachollos run` | Búsqueda completa (una vez) |
| `python -m cazachollos run --loop` | Búsqueda automática cada 30 min |
| `python -m cazachollos run --loop --interval 60` | Búsqueda cada 60 min |
| `python -m cazachollos chollos-hoy` | Chollos de las últimas 24 h |
| `python -m cazachollos informe-semanal` | Resumen de la semana |
| `python -m cazachollos dashboard` | Abre el panel web en http://127.0.0.1:8765 |
| `python -m cazachollos itp 8500` | Calcula el ITP para un precio dado |
| `python -m cazachollos salud` | Estado de cada conector |
| `python -m cazachollos buscar "Golf diésel manual menos de 8000"` | Búsqueda en lenguaje natural |
| `python -m cazachollos valorar <url>` | Valora un anuncio por URL |

---

## Configuración (`config.yaml`)

Abre `config.yaml` con el Bloc de notas o VS Code y cambia:

```yaml
yo:
  provincia: "Madrid"            # tu provincia (para calcular distancias)
  comunidad_autonoma: "Madrid"   # para calcular el ITP
  regimen: "particular"          # "particular" o "rebu" si eres compraventa

busqueda:
  precio_min: 1500
  precio_max: 15000
  anio_min: 2008
  km_max: 220000
  radio_km: 300

objetivos:
  margen_minimo_eur: 1000        # beneficio neto mínimo que te interesa
```

---

## Configurar alertas de Telegram

1. Abre Telegram y busca **@BotFather**.
2. Escribe `/newbot` y sigue las instrucciones.
3. Copia el token que te da (algo como `123456:ABC-DEF...`).
4. Busca **@userinfobot** y anota tu chat ID.
5. Crea el fichero `.env` en la carpeta del proyecto:

```
TELEGRAM_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=tu_chat_id
```

Sin `.env`, las alertas se imprimen en la consola (modo simulación).

---

## Importar anuncios de portales

### Desde ficheros CSV o JSON

Guarda el fichero exportado en `data/entrada/` y ejecuta:
```powershell
python -m cazachollos run
```
El sistema importa automáticamente todos los CSV y JSON de esa carpeta.

### Desde alertas de correo (Pricauto, Trovit, etc.)

Crea una cuenta de Gmail exclusiva para el proyecto, activa las alertas en los portales que uses y configura en `.env`:
```
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=tuemail@gmail.com
IMAP_PASS=contraseña-de-aplicacion-gmail
```
Luego activa en `config.yaml`:
```yaml
fuentes:
  email_alertas:
    activo: true
    remitentes: ["pricauto", "trovit", "coches.net"]
```

---

## Panel web

```powershell
python -m cazachollos dashboard
```

Se abre en http://127.0.0.1:8765. Funciones:

- **Lista de anuncios** con filtros por score, etiqueta, etapa y favoritos.
- **Ficha detallada**: desglose de costes, alarmas, historial de precio, fotos.
- **Etiquetas**: Chollo 🔥 / Bueno ✅ / Justo / Caro / Muy caro.
- **Oferta máxima**: precio máximo que puedes pagar para alcanzar tu margen.
- **Mensaje para el vendedor**: copia al portapapeles con un clic.
- **Checklist de inspección** adaptado al coche.
- **Pipeline**: visto → contactado → visitado → comprado → vendido.
- **Beneficio real**: calcula automáticamente al marcar como vendido.

---

## Tests

```powershell
python -m pytest tests/ -v
```

---

## Estructura del proyecto

```
cazachollos/
├── config.py          # carga config.yaml y .env
├── models.py          # Listing, Evaluation, Flag
├── db.py              # SQLite: anuncios, valoraciones, pipeline
├── normalize.py       # normalización de marcas, km, precios, etc.
├── dedupe.py          # deduplicación por hash foto, teléfono, texto
├── valuation.py       # precio de mercado + curvas de depreciación
├── costs.py           # ITP, reparaciones, desplazamiento, etc.
├── redflags.py        # alarmas de estafa, km bajos, problemas legales
├── scoring.py         # puntuación 0-100 + etiqueta CarGurus
├── pipeline.py        # flujo completo: guardar → valorar → alertar
├── templates.py       # mensaje al vendedor + checklist de inspección
├── search.py          # búsqueda en lenguaje natural
├── vision.py          # análisis de fotos con IA (apagado por defecto)
├── cli.py             # comandos de línea de comandos
├── sources/
│   ├── base.py        # interfaz de conectores
│   ├── email_alerts.py# lector de correo IMAP
│   ├── files_import.py# importador de CSV/JSON
│   ├── page_parser.py # extrae datos de páginas web
│   ├── polite_http.py # HTTP respetando robots.txt
│   └── demo.py        # datos ficticios para pruebas
├── notify/
│   └── telegram.py    # alertas Telegram (+ simulación)
└── web/
    ├── app.py         # panel web Starlette + Jinja2
    ├── templates/     # HTML
    └── static/        # CSS
```

---

## Cosas que necesitas hacer tú

- [ ] Crear el bot de Telegram (@BotFather) y añadir token a `.env`
- [ ] Crear correo dedicado y configurar alertas en portales
- [ ] Verificar tu tipo de ITP en `config.yaml` (habla con tu gestor)
- [ ] Si eres autónomo/compraventa: cambiar `regimen: "rebu"` y verificar exención de ITP
- [ ] Revisar los porcentajes de depreciación de Hacienda (Orden HAC/1501/2025)

---

## Cosas a verificar con tu gestor

- ¿A qué ITP estás sujeto? (varía por comunidad: 4%–8%)
- ¿Estás exento de ITP si compras para revender? (posible en REBU)
- ¿Necesitas declarar IRPF por la actividad de compraventa?
