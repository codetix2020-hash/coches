"""Extrae los datos de un anuncio de su HTML público: JSON-LD (schema.org), OpenGraph y texto."""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from ..models import Listing
from ..normalize import parse_int, parse_km, parse_price, parse_year
from .polite_http import ad_id_from_url, domain_label

VEHICLE_TYPES = {"car", "vehicle", "motorizedvehicle", "product", "offer", "individualproduct"}


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _types(node: dict) -> set[str]:
    t = node.get("@type", [])
    return {x.lower() for x in (t if isinstance(t, list) else [t]) if isinstance(x, str)}


def _name(v) -> str | None:
    if isinstance(v, dict):
        return v.get("name")
    if isinstance(v, list) and v:
        return _name(v[0])
    return v if isinstance(v, str) else None


def parse_listing_html(html: str, url: str) -> Listing:
    soup = BeautifulSoup(html, "html.parser")
    lst = Listing(source=domain_label(url), source_id=ad_id_from_url(url), url=url)

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk(data):
            types = _types(node)
            if not types & VEHICLE_TYPES:
                continue
            lst.title = lst.title or node.get("name") or ""
            lst.description = lst.description or node.get("description") or ""
            lst.make = lst.make or _name(node.get("brand")) or _name(node.get("manufacturer"))
            lst.model = lst.model or _name(node.get("model"))
            lst.fuel = lst.fuel or _name(node.get("fuelType"))
            lst.transmission = lst.transmission or _name(node.get("vehicleTransmission"))
            if node.get("mileageFromOdometer"):
                odo = node["mileageFromOdometer"]
                lst.km = lst.km or parse_int(odo.get("value") if isinstance(odo, dict) else odo)
            for k in ("vehicleModelDate", "productionDate", "dateVehicleFirstRegistered", "modelDate"):
                if node.get(k) and not lst.year:
                    lst.year = parse_year(str(node[k]))
            if node.get("vehicleEngine"):
                eng = node["vehicleEngine"]
                eng = eng[0] if isinstance(eng, list) and eng else eng
                if isinstance(eng, dict) and eng.get("enginePower"):
                    p = eng["enginePower"]
                    val = parse_int(p.get("value") if isinstance(p, dict) else p)
                    unit = (p.get("unitCode") or "") if isinstance(p, dict) else ""
                    if val:
                        lst.power_cv = round(val * 1.36) if unit.upper() == "KWT" else val
            offers = node.get("offers")
            if offers:
                offers = offers[0] if isinstance(offers, list) else offers
                if isinstance(offers, dict) and offers.get("price") and not lst.price:
                    lst.price = parse_price(offers.get("price"))
            imgs = node.get("image")
            if imgs and not lst.images:
                imgs = imgs if isinstance(imgs, list) else [imgs]
                lst.images = [i if isinstance(i, str) else i.get("url", "") for i in imgs if i][:20]
            if "price" in node and not lst.price and "offer" in types:
                lst.price = parse_price(node.get("price"))

    def meta(prop: str) -> str | None:
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        return tag.get("content") if tag and tag.get("content") else None

    lst.title = lst.title or meta("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else "")
    lst.description = lst.description or meta("og:description") or meta("description") or ""
    if not lst.price:
        lst.price = parse_price(meta("product:price:amount") or meta("og:price:amount"))
    if not lst.images and meta("og:image"):
        lst.images = [meta("og:image")]

    text = soup.get_text(" ", strip=True)[:20000]
    if not lst.price:
        m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d{3,6})\s*€", text)
        lst.price = parse_price(m.group(0)) if m else None
    lst.km = lst.km if lst.km is not None else parse_km(text)
    lst.year = lst.year or parse_year(lst.title) or parse_year(text[:3000])
    if re.search(r"\bparticular\b", text, re.I):
        lst.seller_type = "particular"
    elif re.search(r"\b(profesional|concesionario|compraventa)\b", text, re.I):
        lst.seller_type = "profesional"
    lst.raw = {"parsed_from": "html", "len": len(html)}
    return lst
