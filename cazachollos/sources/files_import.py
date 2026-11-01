"""Importa CSV y JSON exportados de portales (Pricauto, Apify…) desde data/entrada/."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Iterable

from ..models import Listing
from ..normalize import parse_int, parse_km, parse_price, parse_year, slug
from .base import Connector

log = logging.getLogger("cazachollos")

# Mapas de columnas frecuentes (nombre_normalizado → nombres posibles en CSV/JSON)
_COL = {
    "source_id": ["id", "source_id", "anuncio_id", "listing_id", "ref"],
    "url": ["url", "link", "enlace", "href"],
    "title": ["title", "titulo", "titulo_anuncio", "name"],
    "description": ["description", "descripcion", "desc", "texto"],
    "make": ["make", "marca", "brand"],
    "model": ["model", "modelo"],
    "version": ["version", "variant", "variante", "trim"],
    "year": ["year", "anio", "año", "matriculacion", "year_registration", "fecha_matriculacion"],
    "km": ["km", "kms", "kilometros", "mileage", "odometer"],
    "price": ["price", "precio", "price_eur"],
    "fuel": ["fuel", "combustible", "fuel_type"],
    "transmission": ["transmission", "cambio", "gear"],
    "power_cv": ["power_cv", "cv", "hp", "potencia", "power"],
    "province": ["province", "provincia", "location", "ciudad", "city"],
    "postal_code": ["postal_code", "cp", "zip", "codigo_postal"],
    "seller_type": ["seller_type", "tipo_vendedor", "vendor_type"],
    "phone": ["phone", "telefono", "tel"],
    "images": ["images", "fotos", "photos", "image_urls"],
    "published_at": ["published_at", "fecha_publicacion", "date", "created_at"],
    "dgt_label": ["dgt_label", "etiqueta_dgt", "etiqueta"],
}


def _get(row: dict, field: str, default=None):
    for key in _COL.get(field, [field]):
        v = row.get(key)
        if v not in (None, "", [], {}):
            return v
    return default


def _row_to_listing(row: dict, source: str) -> Listing | None:
    raw_id = _get(row, "source_id")
    if not raw_id:
        # Generamos un ID desde los datos si no hay uno explícito.
        parts = [str(_get(row, f) or "") for f in ("make", "model", "year", "km", "price")]
        raw_id = "-".join(p for p in parts if p) or None
    if not raw_id:
        return None

    raw_images = _get(row, "images")
    if isinstance(raw_images, str):
        images = [u.strip() for u in raw_images.split(",") if u.strip()]
    elif isinstance(raw_images, list):
        images = [str(u) for u in raw_images]
    else:
        images = []

    return Listing(
        source=source,
        source_id=str(raw_id),
        url=str(_get(row, "url") or ""),
        title=str(_get(row, "title") or ""),
        description=str(_get(row, "description") or ""),
        make=_get(row, "make"),
        model=slug(_get(row, "model")),
        version=_get(row, "version"),
        year=parse_year(str(_get(row, "year") or "")),
        km=parse_km(str(_get(row, "km") or "")) if isinstance(_get(row, "km"), str) else parse_int(_get(row, "km")),
        price=parse_price(str(_get(row, "price") or "")) if isinstance(_get(row, "price"), str) else _get(row, "price"),
        fuel=_get(row, "fuel"),
        transmission=_get(row, "transmission"),
        power_cv=parse_int(_get(row, "power_cv")),
        province=_get(row, "province"),
        postal_code=str(_get(row, "postal_code") or "") or None,
        seller_type=str(_get(row, "seller_type") or "desconocido"),
        images=images,
        published_at=str(_get(row, "published_at") or "") or None,
        dgt_label=_get(row, "dgt_label"),
        raw=dict(row),
    )


def _read_file(path: Path) -> Iterable[dict]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with open(path, encoding="utf-8-sig") as fh:
            yield from csv.DictReader(fh)
    elif suffix == ".json":
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            yield from data
        elif isinstance(data, dict):
            # Puede venir como {"listings": [...]} o {"data": [...]}
            for key in ("listings", "data", "items", "results", "anuncios"):
                if isinstance(data.get(key), list):
                    yield from data[key]
                    return
            yield data  # objeto único
    else:
        log.warning("files_import: formato no soportado (%s), se ignora", path.name)


class FilesImportConnector(Connector):
    name = "files_import"

    def enabled(self) -> bool:
        return True  # siempre activo si hay ficheros en la carpeta

    def fetch(self) -> Iterable[Listing]:
        folder = self.cfg.get_path("fuentes.importar_ficheros.carpeta", "data/entrada")
        from ..config import ROOT
        p = Path(folder) if Path(folder).is_absolute() else ROOT / folder
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            return

        found = sorted(p.glob("*.csv")) + sorted(p.glob("*.json"))
        if not found:
            log.info("files_import: ningún fichero en %s", p)
            return

        total = 0
        for path in found:
            source = f"import:{path.stem}"
            count = 0
            try:
                for row in _read_file(path):
                    lst = _row_to_listing(row, source)
                    if lst:
                        yield lst
                        count += 1
            except Exception as exc:
                log.error("files_import: error leyendo %s: %s", path.name, exc)
            else:
                log.info("files_import: %s → %d anuncios", path.name, count)
                total += count

        log.info("files_import: total %d anuncios importados", total)
