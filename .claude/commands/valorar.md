Valora un anuncio de coche a partir de su URL.

Uso: /valorar <url>

Ejemplo: /valorar https://www.coches.net/coches-segunda-mano/volkswagen-golf-...

Qué hace:
1. Descarga la página si `enriquecer_paginas.activo = true` en config.yaml.
2. Extrae marca, modelo, año, km, precio, descripción e imágenes.
3. Busca comparables en la BD, estima precio de mercado y calcula costes.
4. Muestra: score, etiqueta, margen neto, oferta máxima y mensaje para el vendedor.

Ejecuta:
```
cd C:\Users\bruno\proyectos\cazachollos-coches
.venv\Scripts\python -m cazachollos valorar $ARGUMENTS
```
