"""Búsqueda en lenguaje natural: convierte frases en filtros de config.yaml.

Ejemplos:
  "Golf diésel menor de 8000 euros a 100 km"
  "SUV automático gasolina desde 2018 menos de 150000 km"
  "Seat León o Volkswagen Golf diésel manual"
"""

from __future__ import annotations

import re

from .normalize import MAKES, norm_text, normalize_fuel, normalize_transmission

# Marcas compuestas primero (más largas) para evitar falsos positivos
_ALL_MAKES = sorted(
    [(alias, canon) for canon, aliases in MAKES.items() for alias in aliases],
    key=lambda x: len(x[0]),
    reverse=True,
)

_FUEL_ALIASES = {
    "diesel": "diesel", "gasoil": "diesel", "gasoleo": "diesel",
    "gasolina": "gasolina", "nafta": "gasolina",
    "electrico": "electrico", "electrica": "electrico", "ev": "electrico",
    "hibrido": "hibrido", "hybrid": "hibrido",
    "hibrido enchufable": "hibrido_enchufable", "phev": "hibrido_enchufable", "plug-in": "hibrido_enchufable",
    "glp": "glp", "autogas": "glp",
    "gnc": "gnc", "gas natural": "gnc",
}

_TRANS_ALIASES = {
    "manual": "manual", "automatico": "automatico", "automatica": "automatico",
    "dsg": "automatico", "cvt": "automatico",
}

_BODY_TYPES = {
    "suv": None, "todoterreno": None, "monovolumen": None, "sedan": None,
    "berlina": None, "familiar": None, "coupe": None, "cabrio": None,
    "furgoneta": None, "pick-up": None,
}


def parse_query(text: str) -> dict:
    """Convierte texto libre a un dict con los filtros detectados.

    Las claves del dict usan la misma estructura que config.yaml:
      busqueda.marcas_incluir, busqueda.precio_max, busqueda.km_max, etc.
    """
    t = norm_text(text)
    filters: dict = {}

    # ── Marcas ────────────────────────────────────────────────────────────────
    makes = []
    models_raw = []
    t_work = t
    for alias, canon in _ALL_MAKES:
        if re.search(rf"(^|\W){re.escape(alias)}(\W|$)", t_work):
            makes.append(canon)
            # Intenta capturar el modelo que sigue a la marca
            m = re.search(rf"(?:{re.escape(alias)})\s+([a-z0-9][a-z0-9-]{{1,20}})", t_work)
            if m:
                word = m.group(1)
                if word not in ("diesel", "gasolina", "manual", "automatico", "electrico",
                                "hibrido", "de", "con", "sin", "por"):
                    models_raw.append(word)
            t_work = re.sub(rf"(^|\W){re.escape(alias)}(\W|$)", " ", t_work)
    if makes:
        filters["busqueda.marcas_incluir"] = list(dict.fromkeys(makes))
    if models_raw:
        filters["busqueda.modelos_incluir"] = list(dict.fromkeys(models_raw))

    # ── Combustible ───────────────────────────────────────────────────────────
    fuel_found = normalize_fuel(t)
    if fuel_found:
        filters["busqueda.combustibles"] = [fuel_found]

    # ── Transmisión ───────────────────────────────────────────────────────────
    trans = normalize_transmission(t)
    if trans:
        filters["busqueda.cambios"] = [trans]

    # ── Precio ────────────────────────────────────────────────────────────────
    # "menos de 8000", "máximo 10.000 €", "hasta 12000", "< 9000"
    m = re.search(r"(?:menos de|m[aá]ximo|hasta|<|max\.?)\s*(\d[\d.,\s]*)\s*(?:€|eur|euros?)?", t)
    if m:
        filters["busqueda.precio_max"] = int(re.sub(r"[.,\s]", "", m.group(1).strip()))
    m = re.search(r"(?:m[aá]s de|m[ií]nimo|desde|>|min\.?)\s*(\d[\d.,\s]*)\s*(?:€|eur|euros?)?", t)
    if m:
        filters["busqueda.precio_min"] = int(re.sub(r"[.,\s]", "", m.group(1).strip()))

    # ── Kilómetros ────────────────────────────────────────────────────────────
    m = re.search(r"(?:menos de|m[aá]ximo|hasta|<)\s*(\d[\d.,\s]*)\s*km", t)
    if m:
        filters["busqueda.km_max"] = int(re.sub(r"[.,\s]", "", m.group(1).strip()))

    # ── Año ───────────────────────────────────────────────────────────────────
    m = re.search(r"(?:desde|a partir de|m[ií]nimo)\s*(20\d{2}|19\d{2})", t)
    if m:
        filters["busqueda.anio_min"] = int(m.group(1))
    m = re.search(r"(?:hasta|antes de|m[aá]ximo)\s*(20\d{2}|19\d{2})", t)
    if m:
        filters["busqueda.anio_max"] = int(m.group(1))
    # Año suelto: "Golf 2018" → anio_min si no hay otro
    years = re.findall(r"\b(20[012]\d)\b", t)
    if years and "busqueda.anio_min" not in filters:
        filters["busqueda.anio_min"] = int(years[0])

    # ── Radio ─────────────────────────────────────────────────────────────────
    m = re.search(r"(?:a|en un radio de|dentro de)\s*(\d+)\s*km", t)
    if m:
        filters["busqueda.radio_km"] = int(m.group(1))

    return filters


def describe_filters(filters: dict) -> str:
    """Describe los filtros detectados en texto legible."""
    parts = []
    if v := filters.get("busqueda.marcas_incluir"):
        parts.append("Marcas: " + ", ".join(v))
    if v := filters.get("busqueda.modelos_incluir"):
        parts.append("Modelos: " + ", ".join(v))
    if v := filters.get("busqueda.combustibles"):
        parts.append("Combustible: " + ", ".join(v))
    if v := filters.get("busqueda.cambios"):
        parts.append("Cambio: " + v[0])
    if v := filters.get("busqueda.precio_min"):
        parts.append(f"Precio desde: {v:,} €".replace(",", "."))
    if v := filters.get("busqueda.precio_max"):
        parts.append(f"Precio hasta: {v:,} €".replace(",", "."))
    if v := filters.get("busqueda.km_max"):
        parts.append(f"Km máx.: {v:,}".replace(",", "."))
    if v := filters.get("busqueda.anio_min"):
        parts.append(f"Año desde: {v}")
    if v := filters.get("busqueda.anio_max"):
        parts.append(f"Año hasta: {v}")
    if v := filters.get("busqueda.radio_km"):
        parts.append(f"Radio: {v} km")
    return " · ".join(parts) if parts else "Sin filtros reconocidos"
