"""Distancias entre provincias.

road_km_real() usa OSRM (router.project-osrm.org) para distancia de conducción exacta.
road_km() es la versión offline rápida (haversine × 1.25) como fallback.
"""

from __future__ import annotations

import logging
import math

import httpx

from .normalize import norm_text

# Mapping of Spanish postal code prefixes (2 digits) → province key in PROVINCES
_ZIP_TO_PROVINCE = {
    "01": "alava", "02": "albacete", "03": "alicante", "04": "almeria",
    "05": "avila", "06": "badajoz", "07": "illes balears", "08": "barcelona",
    "09": "burgos", "10": "caceres", "11": "cadiz", "12": "castellon",
    "13": "ciudad real", "14": "cordoba", "15": "a coruna", "16": "cuenca",
    "17": "girona", "18": "granada", "19": "guadalajara", "20": "gipuzkoa",
    "21": "huelva", "22": "huesca", "23": "jaen", "24": "leon",
    "25": "lleida", "26": "la rioja", "27": "lugo", "28": "madrid",
    "29": "malaga", "30": "murcia", "31": "navarra", "32": "ourense",
    "33": "asturias", "34": "palencia", "35": "las palmas", "36": "pontevedra",
    "37": "salamanca", "38": "santa cruz de tenerife", "39": "cantabria", "40": "segovia",
    "41": "sevilla", "42": "soria", "43": "tarragona", "44": "teruel",
    "45": "toledo", "46": "valencia", "47": "valladolid", "48": "bizkaia",
    "49": "zamora", "50": "zaragoza", "51": "ceuta", "52": "melilla",
}


def province_from_zip(zip_code: str | None) -> str | None:
    """Devuelve la clave de provincia a partir del código postal (2 primeros dígitos)."""
    if not zip_code:
        return None
    digits = zip_code.strip().lstrip("0").zfill(5)[:2]
    # Handle short zip codes (e.g. "8403" → "08")
    if len(zip_code.strip()) < 5:
        digits = zip_code.strip().zfill(5)[:2]
    return _ZIP_TO_PROVINCE.get(digits)

log = logging.getLogger("cazachollos")

_osrm_cache: dict[tuple, tuple[float, float]] = {}


def road_km_real(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float] | None:
    """Distancia y tiempo de conducción reales via OSRM.

    Devuelve (km, minutos) o None si no se puede contactar con el servidor.
    Cachea resultados para evitar peticiones repetidas.
    """
    key = (round(lat1, 3), round(lon1, 3), round(lat2, 3), round(lon2, 3))
    if key in _osrm_cache:
        return _osrm_cache[key]
    try:
        url = (
            f"http://router.project-osrm.org/route/v1/driving/"
            f"{lon1},{lat1};{lon2},{lat2}?overview=false"
        )
        r = httpx.get(url, timeout=8)
        if r.status_code == 200:
            route = r.json()["routes"][0]
            result = (
                round(route["distance"] / 1000, 1),
                round(route["duration"] / 60, 0),
            )
            _osrm_cache[key] = result
            return result
    except Exception as exc:
        log.debug("OSRM: %s", exc)
    return None


def road_km_provinces(a: str | None, b: str | None) -> tuple[float, float] | None:
    """Distancia de conducción entre capitales de provincia (km, minutos).

    Intenta OSRM primero; si falla usa haversine × 1.25 con duración estimada.
    """
    ka, kb = province_key(a), province_key(b)
    if not ka or not kb:
        return None
    if ka == kb:
        return (25.0, 30.0)
    lat1, lon1 = PROVINCES[ka]
    lat2, lon2 = PROVINCES[kb]
    real = road_km_real(lat1, lon1, lat2, lon2)
    if real:
        return real
    # Fallback: haversine
    dist = road_km(a, b)
    return (dist, dist / 80 * 60) if dist else None

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
