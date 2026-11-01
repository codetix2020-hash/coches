Ejecuta una búsqueda en lenguaje natural con Cazachollos.

Uso: /buscar <texto>

Ejemplo: /buscar Golf diésel manual menos de 8000 euros a 100 km

Pasos que sigue este comando:
1. Parsea el texto con `cazachollos.search.parse_query` y muestra los filtros detectados.
2. Aplica esos filtros a la base de datos local y lista los anuncios que encajan.
3. Si hay resultados con score ≥ 70, los destaca como chollos.

Ejecuta en la terminal del proyecto:
```
cd C:\Users\bruno\proyectos\cazachollos-coches
.venv\Scripts\python -m cazachollos buscar $ARGUMENTS
```
