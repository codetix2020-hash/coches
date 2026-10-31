# Cazachollos · contexto para Claude Code

## Objetivo
Sistema personal de Sky (España) para encontrar coches de segunda mano por debajo de mercado y revenderlos con margen.
Sky no es programador: explica cada paso, di qué comando ejecutar y por qué, y **avisa antes de cualquier cosa que cueste dinero o no se pueda deshacer**.

## Decisiones ya tomadas (no reabrir sin motivo)
- **Datos:** no hay API pública de portales para compradores. Fuente principal = **servicios que ya agregan portales** (Pricauto, Trovit, alertas propias de cada portal) leídos desde **un correo dedicado** (IMAP). Respaldo: importar CSV/JSON exportados. Lectura de páginas solo si robots.txt lo permite (`sources/polite_http.py`).
- **Nunca** saltar captchas, logins, bloqueos ni geobloqueos; nada de proxies residenciales. Teléfonos solo como hash (RGPD).
- **Nuestro valor añadido:** margen neto real, ITP con tablas de Hacienda, alarmas de estafa, análisis de fotos, puntuación 0-100, alertas Telegram, panel con seguimiento visto → vendido y beneficio real.
- Stack: Python 3.11+, SQLite, Starlette + Jinja2 (panel local en 127.0.0.1), requests, BeautifulSoup, Pillow. Sin numpy.
- Todos los supuestos en `config.yaml`; secretos en `.env` (nunca imprimirlos ni commitearlos).

## Estado (31-10-2026)
Hecho (sin probar todavía):
- `config.yaml`, `cazachollos/config.py`, `models.py`, `db.py` (esquema completo), `normalize.py`, `geo.py`
- `dedupe.py` (teléfono hash, dHash de fotos, texto, km/precio/provincia)
- `valuation.py` (comparables + regresión log edad/km, confianza)
- `costs.py` (ITP con tabla Hacienda + % antigüedad, transferencia, reparaciones por palabras clave, desplazamiento, capital, REBU)
- `redflags.py`, `scoring.py`, `pipeline.py`
- `sources/base.py` (salud de conectores), `polite_http.py`, `page_parser.py` (JSON-LD/OpenGraph), `email_alerts.py`

Pendiente, en este orden:
1. `sources/files_import.py` (CSV/JSON de `data/entrada`) y `sources/demo.py` (datos falsos marcados para probar).
2. `notify/telegram.py` (+ email opcional, modo simulación sin token) y `vision.py` (API de Claude, **apagado por defecto: cuesta dinero**).
3. `cli.py` + `__main__.py`: `init`, `run [--loop]`, `demo`, `valorar <url>`, `chollos-hoy`, `informe-semanal`, `dashboard`, `itp`, `salud`.
4. `web/` panel: lista con filtros, ficha con desglose de costes/alarmas/motivos, favoritos, etapas y beneficio real.
5. Tests (pytest) de cada módulo + prueba de extremo a extremo con datos demo. **Ejecutarlos y enseñar el resultado a Sky.**
6. `.claude/commands/` (/buscar, /valorar, /chollos-hoy, /informe-semanal), hooks (ruff format; pytest antes de commit), `.gitignore`, `.env.example`, `requirements.txt`, README paso a paso.
7. Docs: checklist de inspección, preguntas al vendedor, cómo pedir informe DGT, preguntas para el gestor.

## Cosas a VERIFICAR (no inventar)
- Tipo de ITP de la comunidad de Sky y casos especiales (cuotas fijas en coches viejos).
- Porcentajes de depreciación de Hacienda en `config.yaml` contra la Orden HAC/1501/2025; generar `data/hacienda/precios_medios_2026.csv` desde el BOE.
- Exención de ITP para compraventas profesionales (preguntar al gestor).
- Pricauto: precio, portales cubiertos, si exige ser compraventa, si exporta datos o tiene API.
- robots.txt y condiciones de uso de cada portal antes de activar `enriquecer_paginas`.

## Datos ya contrastados (oct. 2026)
Tasa DGT transferencia 55,70 €; informe DGT detallado 8,67 € (reducido gratis en miDGT); ITP 4-8 % según comunidad, sobre el valor de Hacienda si es mayor que el precio; garantía mínima 1 año si vendes como profesional; REBU = IVA solo sobre el margen.

## Preguntas a Sky aún sin responder
Presupuesto por coche y capital, provincia/comunidad y radio, tipo de coches, mecánica o taller, margen mínimo, sistema operativo, PC 24/7 o VPS, gasto mensual en servicios, canal de alertas, si es o será autónomo.
