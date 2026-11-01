"""Conector para AutoScout24 (España y Alemania).

Usa el JSON embebido en __NEXT_DATA__ — no necesita API key ni browser headless.
- country="ES"  → autoscout24.es  (coches de segunda mano en España)
- country="DE"  → autoscout24.de  (mercado alemán, para importaciones)

Configura en config.yaml → fuentes.autoscout24:
  activo: true
  paises: [ES]          # o [ES, DE]
  marcas: [volkswagen, seat, toyota]
  precio_max: 15000
  km_max: 150000
  anio_min: 2013
  paginas: 3            # cuántas páginas scrapeamos por búsqueda
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Iterator

import httpx

from ..models import Listing
from ..normalize import normalize_fuel, normalize_listing, normalize_transmission
from .base import Connector

log = logging.getLogger("cazachollos")

_DOMAINS = {
    "ES": "www.autoscout24.es",
    "DE": "www.autoscout24.de",
}

# AutoScout24 country codes in URL (cy= parameter)
_CY_CODES = {
    "ES": "E",   # España
    "DE": "D",   # Deutschland
    "IT": "I",   # Italia
    "FR": "F",   # France
    "PT": "P",   # Portugal
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

# AutoScout24 fuel names → normalized
_FUEL_MAP = {
    "Diésel": "diesel",
    "Diesel": "diesel",
    "Benzin": "gasolina",
    "Gasolina": "gasolina",
    "Hybrid": "hibrido",
    "Hybride": "hibrido",
    "Electro": "electrico",
    "Eléctrico": "electrico",
    "Electric": "electrico",
    "GPL": "glp",
    "LPG": "glp",
    "Gas": "glp",
}

_TRANS_MAP = {
    "manual": "manual",
    "Manual": "manual",
    "Schaltgetriebe": "manual",
    "automatic": "automatico",
    "Automatik": "automatico",
    "Automático": "automatico",
}


def _parse_int(s: str | None) -> int | None:
    if not s:
        return None
    cleaned = re.sub(r"[^\d]", "", str(s))
    return int(cleaned) if cleaned else None


def _extract_year(first_reg: str | None) -> int | None:
    """'1/2018' → 2018, '2018' → 2018, '01/2018' → 2018."""
    if not first_reg:
        return None
    m = re.search(r"(\d{4})", first_reg)
    return int(m.group(1)) if m else None


def _full_url(domain: str, relative_url: str) -> str:
    if relative_url.startswith("http"):
        return relative_url
    return f"https://{domain}{relative_url}"


def _image_hires(url: str) -> str:
    """Converts AS24 thumbnail URLs to full-size."""
    return re.sub(r"/\d+x\d+\.webp$", "/1280x960.webp", url)


class AutoScout24Connector(Connector):
    """Scraper de AutoScout24 para España y/o Alemania."""

    name = "autoscout24"

    def __init__(self, cfg):
        self.cfg = cfg
        src_cfg = cfg.get_path("fuentes.autoscout24", {})
        self.countries: list[str] = src_cfg.get("paises", ["ES"])
        self.brands: list[str] = src_cfg.get("marcas", [])
        self.price_max: int | None = src_cfg.get("precio_max")
        self.km_max: int | None = src_cfg.get("km_max")
        self.year_min: int | None = src_cfg.get("anio_min")
        self.pages: int = src_cfg.get("paginas", 2)
        self.delay: float = src_cfg.get("delay_segundos", 1.5)
        self._client = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=25,
        )

    def enabled(self) -> bool:
        return bool(self.cfg.get_path("fuentes.autoscout24.activo", False))

    def health(self) -> dict:
        try:
            r = self._client.get("https://www.autoscout24.es/", timeout=10)
            return {"ok": r.status_code == 200, "latency_ms": r.elapsed.total_seconds() * 1000}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Main fetch
    # ------------------------------------------------------------------

    def fetch(self) -> Iterator[Listing]:
        for country in self.countries:
            domain = _DOMAINS.get(country, "www.autoscout24.es")
            brands = self.brands or [None]  # None = all brands
            for brand in brands:
                yield from self._fetch_brand(domain, country, brand)

    def _fetch_brand(self, domain: str, country: str, brand: str | None) -> Iterator[Listing]:
        for page in range(1, self.pages + 1):
            url = self._build_url(domain, country, brand, page)
            log.info("autoscout24[%s]: fetching page %d/%d — %s", country, page, self.pages, url)
            try:
                listings = self._fetch_page(url)
                if not listings:
                    log.info("autoscout24[%s]: page %d empty, stopping", country, page)
                    break
                for raw in listings:
                    lst = self._parse(raw, country, domain)
                    if lst:
                        yield lst
                if page < self.pages:
                    time.sleep(self.delay)
            except Exception as exc:
                log.error("autoscout24[%s]: error on page %d: %s", country, page, exc)
                break

    def _build_url(self, domain: str, country: str, brand: str | None, page: int) -> str:
        cy = _CY_CODES.get(country, country)
        parts = ["https://", domain, "/lst"]
        if brand:
            parts.append(f"/{brand.lower()}")
        parts.append(f"?atype=C&cy={cy}&sort=standard&desc=0")
        if self.price_max:
            parts.append(f"&priceto={self.price_max}")
        if self.km_max:
            parts.append(f"&mileageto={self.km_max}")
        if self.year_min:
            parts.append(f"&fregfrom={self.year_min}")
        if page > 1:
            parts.append(f"&page={page}")
        return "".join(parts)

    def _fetch_page(self, url: str) -> list[dict]:
        r = self._client.get(url)
        if r.status_code != 200:
            log.warning("autoscout24: HTTP %d for %s", r.status_code, url)
            return []
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
            r.text,
            re.DOTALL,
        )
        if not m:
            log.warning("autoscout24: no __NEXT_DATA__ in %s", url)
            return []
        data = json.loads(m.group(1))
        listings = data.get("props", {}).get("pageProps", {}).get("listings", [])
        if not isinstance(listings, list):
            return []
        return listings

    def _parse(self, raw: dict, country: str, domain: str) -> Listing | None:
        try:
            vehicle = raw.get("vehicle", {})
            price_info = raw.get("price", {})
            location = raw.get("location", {})

            price = price_info.get("priceRaw")
            if not price:
                return None

            make = vehicle.get("make", "").lower()
            model_name = vehicle.get("model", "")
            model = model_name.lower()
            # Build a descriptive title if AS24 only returns generic "Volkswagen Golf"
            motor = vehicle.get("motorTypeName", "") or vehicle.get("modelVersionInput", "")
            raw_title = raw.get("title", f"{vehicle.get('make', '')} {model_name}")
            title = raw_title
            if motor and motor.lower() not in raw_title.lower():
                title = f"{raw_title} {motor}"

            # Subtitle / description
            subtitle = vehicle.get("subtitle", "")

            # Extract structured details from vehicleDetails array
            vd = {item["iconName"]: item["data"]
                  for item in (raw.get("vehicleDetails") or [])
                  if "iconName" in item and "data" in item}

            # Year: try vehicleDetails "calendar" first, then vehicle.firstRegistration
            year = _extract_year(
                vd.get("calendar") or vehicle.get("firstRegistration")
            )
            # km: try vehicleDetails "mileage_odometer" first, then vehicle field
            km = _parse_int(vd.get("mileage_odometer") or vehicle.get("mileageInKm"))

            fuel_raw = vehicle.get("fuel", "")
            fuel = _FUEL_MAP.get(fuel_raw) or normalize_fuel(fuel_raw)

            trans_raw = vehicle.get("transmission", "")
            transmission = _TRANS_MAP.get(trans_raw) or normalize_transmission(trans_raw)

            # Power: extract CV from vehicleDetails speedometer field "81 kW (110 CV)"
            power_cv = None
            speed_data = vd.get("speedometer", "")
            cv_match = re.search(r"\((\d+)\s*CV\)", speed_data, re.IGNORECASE)
            if cv_match:
                power_cv = int(cv_match.group(1))
            elif vehicle.get("rawPowerInHp"):
                power_cv = int(vehicle["rawPowerInHp"])

            relative_url = raw.get("url", "")
            url = _full_url(domain, relative_url)

            images = [_image_hires(img) for img in (raw.get("images") or [])[:10]]

            province = location.get("city") or location.get("zip") or ""
            seller = raw.get("seller", {})
            seller_type = "profesional" if seller.get("type") == "D" else "particular"

            # Source id: AS24 listing UUID
            source_id = raw.get("id", re.search(r"[a-f0-9-]{36}", relative_url or ""))
            if hasattr(source_id, "group"):
                source_id = source_id.group(0)
            source_id = f"as24_{country}_{source_id}"

            lst = Listing(
                source=f"autoscout24_{country.lower()}",
                source_id=source_id,
                url=url,
                title=title,
                description=subtitle,
                make=make,
                model=model,
                year=year,
                km=km,
                price=int(price),
                fuel=fuel,
                transmission=transmission,
                power_cv=power_cv,
                province=province,
                seller_type=seller_type,
                images=images,
                raw={"country": country, "location": location, "vehicle": vehicle},
            )
            return normalize_listing(lst)
        except Exception as exc:
            log.debug("autoscout24: parse error: %s — %s", exc, raw.get("id"))
            return None
