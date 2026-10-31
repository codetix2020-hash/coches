"""Normaliza textos de anuncios: marcas, combustible, cambio, km, año, precio, etiqueta DGT."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from .models import Listing

MAKES = {
    "abarth": ["abarth"], "alfa-romeo": ["alfa romeo", "alfa-romeo", "alfa"],
    "audi": ["audi"], "bmw": ["bmw"], "byd": ["byd"], "citroen": ["citroen", "citroën"],
    "cupra": ["cupra"], "dacia": ["dacia"], "ds": ["ds automobiles", "ds"],
    "fiat": ["fiat"], "ford": ["ford"], "honda": ["honda"], "hyundai": ["hyundai"],
    "jaguar": ["jaguar"], "jeep": ["jeep"], "kia": ["kia"], "land-rover": ["land rover", "land-rover"],
    "lexus": ["lexus"], "mazda": ["mazda"], "mercedes-benz": ["mercedes-benz", "mercedes benz", "mercedes"],
    "mg": ["mg"], "mini": ["mini"], "mitsubishi": ["mitsubishi"], "nissan": ["nissan"],
    "opel": ["opel"], "peugeot": ["peugeot"], "porsche": ["porsche"], "renault": ["renault"],
    "seat": ["seat"], "skoda": ["skoda", "škoda"], "smart": ["smart"], "ssangyong": ["ssangyong"],
    "subaru": ["subaru"], "suzuki": ["suzuki"], "tesla": ["tesla"], "toyota": ["toyota"],
    "volkswagen": ["volkswagen", "vw"], "volvo": ["volvo"],
}

FUEL_MAP = [
    (r"h[ií]brido enchufable|phev|plug.?in", "hibrido_enchufable"),
    (r"el[eé]ctrico|\bev\b|\bbev\b", "electrico"),
    (r"h[ií]brido|hybrid|\bhev\b|\bmhev\b", "hibrido"),
    (r"di[eé]sel|gasoil|gas[oó]leo|\btdi\b|\bhdi\b|\bdci\b|\bcrdi\b|\bjtd|\bd4d\b|\btdci\b|\bcdi\b", "diesel"),
    (r"\bglp\b|\blpg\b|autogas", "glp"),
    (r"\bgnc\b|\bcng\b|gas natural", "gnc"),
    (r"gasolina|\btsi\b|\btfsi\b|\bvti\b|\bpuretech\b|\btce\b|\becoboost\b|\bgasoline\b", "gasolina"),
]


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def norm_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", strip_accents((text or "").lower())).strip()


def slug(text: str | None) -> str | None:
    if not text:
        return None
    s = re.sub(r"[^a-z0-9]+", "-", norm_text(text)).strip("-")
    return s or None


def normalize_make(raw: str | None, title: str = "") -> str | None:
    for candidate in (raw, title):
        t = norm_text(candidate)
        if not t:
            continue
        for canon, aliases in MAKES.items():
            for alias in sorted(aliases, key=len, reverse=True):
                if re.search(rf"(^|\W){re.escape(strip_accents(alias))}(\W|$)", t):
                    return canon
    return slug(raw)


def model_from_title(title: str, make: str | None) -> str | None:
    t = norm_text(title)
    if make:
        for alias in sorted(MAKES.get(make, [make]), key=len, reverse=True):
            t = re.sub(rf"(^|\W){re.escape(strip_accents(alias))}(\W|$)", " ", t, count=1)
    words = [w for w in re.split(r"\s+", t) if w and not re.fullmatch(r"\d{4}", w)]
    if not words:
        return None
    first = words[0]
    # Modelos de dos palabras habituales (Clase A, Serie 3, Grand C4...)
    if first in {"serie", "clase", "grand", "range", "model", "id", "c", "x"} and len(words) > 1:
        return slug(f"{first} {words[1]}")
    return slug(first)


def normalize_fuel(*texts: str | None) -> str | None:
    t = " ".join(norm_text(x) for x in texts if x)
    for pattern, value in FUEL_MAP:
        if re.search(pattern, t):
            return value
    return None


def normalize_transmission(*texts: str | None) -> str | None:
    t = " ".join(norm_text(x) for x in texts if x)
    if re.search(r"autom[aá]tic|\bdsg\b|\bcvt\b|\bs.?tronic\b|\bedc\b|\beat\d?\b|\bat\b|tiptronic|steptronic", t):
        return "automatico"
    if re.search(r"manual", t):
        return "manual"
    return None


def parse_int(text) -> int | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None


def parse_price(text) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    t = str(text).replace("\xa0", " ")
    m = re.search(r"(\d{1,3}(?:[.\s]\d{3})+|\d+)(?:,\d{1,2})?\s*(?:€|eur)", t, re.I) or re.search(
        r"(\d{1,3}(?:[.\s]\d{3})+|\d+)", t
    )
    if not m:
        return None
    return float(re.sub(r"[.\s]", "", m.group(1)))


def parse_km(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"(\d{1,3}(?:[.\s]\d{3})+|\d+)\s*(?:km|kms|kilómetros|kilometros)\b", str(text), re.I)
    return int(re.sub(r"[.\s]", "", m.group(1))) if m else None


def parse_year(text: str | None) -> int | None:
    if not text:
        return None
    years = [int(y) for y in re.findall(r"\b(19[89]\d|20[0-4]\d)\b", str(text))]
    return years[0] if years else None


def hash_phone(phone: str | None) -> str | None:
    """Guardamos solo una huella del teléfono para detectar duplicados (RGPD)."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)[-9:]
    if len(digits) < 9:
        return None
    return hashlib.sha256(f"cazachollos:{digits}".encode()).hexdigest()[:16]


PHONE_RE = re.compile(r"(?:\+?34[\s.-]?)?([6789]\d{2}[\s.-]?\d{3}[\s.-]?\d{3}|[6789]\d{2}[\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2})")


def estimate_dgt_label(fuel: str | None, year: int | None) -> str | None:
    """Estimación de etiqueta DGT por combustible y año de matriculación (aproximada)."""
    if fuel in ("electrico",):
        return "CERO"
    if fuel == "hibrido_enchufable":
        return "CERO"  # si autonomía eléctrica >= 40 km; si no, ECO
    if fuel in ("hibrido", "glp", "gnc"):
        return "ECO"
    if not year:
        return None
    if fuel == "gasolina":
        return "C" if year >= 2006 else ("B" if year >= 2001 else "SIN")
    if fuel == "diesel":
        return "C" if year >= 2016 else ("B" if year >= 2006 else "SIN")
    return None


def normalize_listing(lst: Listing) -> Listing:
    text = f"{lst.title} {lst.description}"
    lst.make = normalize_make(lst.make, lst.title)
    lst.model = slug(lst.model) or model_from_title(lst.title, lst.make)
    lst.fuel = normalize_fuel(lst.fuel) or normalize_fuel(text)
    lst.transmission = normalize_transmission(lst.transmission) or normalize_transmission(text)
    lst.year = lst.year or parse_year(lst.title)
    lst.km = lst.km if lst.km is not None else parse_km(text)
    lst.price = parse_price(lst.price) if not isinstance(lst.price, (int, float)) else float(lst.price)
    lst.seller_type = (lst.seller_type or "desconocido").lower()
    if lst.seller_type not in ("particular", "profesional"):
        lst.seller_type = "desconocido"
    if not lst.phone_hash:
        m = PHONE_RE.search(lst.description or "")
        if m:
            lst.phone_hash = hash_phone(m.group(0))
    lst.dgt_label = lst.dgt_label or estimate_dgt_label(lst.fuel, lst.year)
    if lst.province:
        lst.province = lst.province.strip().title()
    return lst
