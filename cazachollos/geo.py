"""Distancias aproximadas entre provincias (capital a capital, factor carretera 1,25)."""

from __future__ import annotations

import math

from .normalize import norm_text

# Coordenadas aproximadas de las capitales de provincia.
PROVINCES = {
    "a coruna": (43.36, -8.41), "alava": (42.85, -2.67), "albacete": (38.99, -1.86),
    "alicante": (38.35, -0.48), "almeria": (36.84, -2.46), "asturias": (43.36, -5.85),
    "avila": (40.66, -4.70), "badajoz": (38.88, -6.97), "barcelona": (41.39, 2.17),
    "burgos": (42.34, -3.70), "caceres": (39.47, -6.37), "cadiz": (36.53, -6.29),
    "cantabria": (43.46, -3.81), "castellon": (39.99, -0.05), "ciudad real": (38.99, -3.93),
    "cordoba": (37.89, -4.78), "cuenca": (40.07, -2.13), "girona": (41.98, 2.82),
    "granada": (37.18, -3.60), "guadalajara": (40.63, -3.17), "gipuzkoa": (43.32, -1.98),
    "huelva": (37.26, -6.94), "huesca": (42.14, -0.41), "illes balears": (39.57, 2.65),
    "jaen": (37.78, -3.79), "la rioja": (42.47, -2.45), "las palmas": (28.12, -15.43),
    "leon": (42.60, -5.57), "lleida": (41.62, 0.62), "lugo": (43.01, -7.56),
    "madrid": (40.42, -3.70), "malaga": (36.72, -4.42), "murcia": (37.99, -1.13),
    "navarra": (42.81, -1.64), "ourense": (42.34, -7.86), "palencia": (42.01, -4.53),
    "pontevedra": (42.43, -8.64), "salamanca": (40.97, -5.66),
    "santa cruz de tenerife": (28.46, -16.25), "segovia": (40.95, -4.12),
    "sevilla": (37.39, -5.98), "soria": (41.76, -2.46), "tarragona": (41.12, 1.25),
    "teruel": (40.34, -1.11), "toledo": (39.86, -4.02), "valencia": (39.47, -0.38),
    "valladolid": (41.65, -4.72), "bizkaia": (43.26, -2.93), "zamora": (41.50, -5.75),
    "zaragoza": (41.65, -0.89), "ceuta": (35.89, -5.32), "melilla": (35.29, -2.94),
}

ALIASES = {
    "la coruna": "a coruna", "coruna": "a coruna", "araba": "alava", "vitoria": "alava",
    "alacant": "alicante", "oviedo": "asturias", "santander": "cantabria", "castello": "castellon",
    "gerona": "girona", "guipuzcoa": "gipuzkoa", "san sebastian": "gipuzkoa", "baleares": "illes balears",
    "mallorca": "illes balears", "palma": "illes balears", "logrono": "la rioja", "rioja": "la rioja",
    "lerida": "lleida", "pamplona": "navarra", "orense": "ourense", "tenerife": "santa cruz de tenerife",
    "gran canaria": "las palmas", "vizcaya": "bizkaia", "bilbao": "bizkaia",
}

ISLANDS = {"illes balears", "las palmas", "santa cruz de tenerife", "ceuta", "melilla"}


def province_key(name: str | None) -> str | None:
    if not name:
        return None
    k = norm_text(name).replace("provincia de ", "")
    k = ALIASES.get(k, k)
    return k if k in PROVINCES else None


def road_km(a: str | None, b: str | None) -> float | None:
    ka, kb = province_key(a), province_key(b)
    if not ka or not kb:
        return None
    if ka == kb:
        return 25.0
    (lat1, lon1), (lat2, lon2) = PROVINCES[ka], PROVINCES[kb]
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(h)) * 1.25, 0)


def needs_ferry(a: str | None, b: str | None) -> bool:
    ka, kb = province_key(a), province_key(b)
    return bool(ka and kb and ka != kb and (ka in ISLANDS or kb in ISLANDS))
