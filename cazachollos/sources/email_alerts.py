"""Lee los correos de alertas (Pricauto, Trovit, coches.net, Wallapop, Milanuncios...) y saca los coches.

Es la vía más legal y estable: los portales y agregadores te envían los anuncios a TU correo.
Usa un correo dedicado (p. ej. Gmail) con "contraseña de aplicación". Solo lectura.
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from typing import Iterable

from bs4 import BeautifulSoup

from ..config import secret
from ..models import Listing
from ..normalize import parse_km, parse_price, parse_year
from .base import Connector
from .polite_http import ad_id_from_url, domain_label

log = logging.getLogger("cazachollos")

AD_URL = re.compile(
    r"https?://(?:www\.|es\.)?(?:coches\.net|wallapop\.com|milanuncios\.com|autoscout24\.es|"
    r"autocasion\.com|coches\.com|mobile\.de|suchen\.mobile\.de|pricauto\.com|trovit\.es|"
    r"coches\.trovit\.es|autouncle\.es)/[^\s\"'<>]+",
    re.I,
)
SKIP = re.compile(r"(unsubscribe|baja|darse-de-baja|preferences|preferencias|privacy|privacidad|login|"
                  r"/ayuda|/help|logo|\.png|\.jpg|\.gif|facebook|twitter|instagram|app-store|play\.google)", re.I)


def _block_text(a_tag) -> str:
    """Texto del bloque visual que rodea el enlace (tarjeta del coche en el email)."""
    node = a_tag
    best = a_tag.get_text(" ", strip=True)
    for _ in range(5):
        node = node.parent
        if node is None:
            break
        txt = node.get_text(" ", strip=True)
        if len(txt) > 400:
            break
        best = txt
    return best


def parse_alert_email(html: str, received_at: str | None = None, sender: str = "") -> list[Listing]:
    """Convierte un correo de alerta en anuncios. Funciona con la mayoría de formatos de tarjeta."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, Listing] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if SKIP.search(href):
            continue
        if not AD_URL.match(href):
            # Muchos correos usan redirecciones de seguimiento con la URL real codificada.
            m = re.search(r"(https?%3A%2F%2F[^&\"']+)", href)
            if m:
                from urllib.parse import unquote

                inner = unquote(m.group(1))
                if AD_URL.match(inner):
                    href = inner
                else:
                    continue
            elif "pricauto" not in sender.lower() and "trovit" not in sender.lower():
                continue
        block = _block_text(a)
        price = parse_price(block) if "€" in block else None
        if not price and not re.search(r"\d{4}", block):
            continue
        url = href.split("?")[0] if "wallapop" in href or "coches.net" in href else href
        key = ad_id_from_url(url)
        lst = out.get(key) or Listing(source=domain_label(url), source_id=key, url=url)
        title = a.get_text(" ", strip=True)
        if len(title) > len(lst.title) and len(title) < 140 and not re.fullmatch(r"[\d.\s€]+", title):
            lst.title = title
        lst.price = lst.price or price
        lst.km = lst.km if lst.km is not None else parse_km(block)
        lst.year = lst.year or parse_year(block)
        lst.description = lst.description or block[:500]
        prov = re.search(r"\b(?:en|·|\|)\s*([A-ZÁÉÍÓÚ][a-záéíóúñ]+(?:\s[A-ZÁÉÍÓÚ][a-záéíóúñ]+)?)\s*(?:\(|$|·|\|)", block)
        if prov and not lst.province:
            lst.province = prov.group(1)
        if re.search(r"\bparticular\b", block, re.I):
            lst.seller_type = "particular"
        elif re.search(r"\bprofesional|concesionario\b", block, re.I):
            lst.seller_type = "profesional"
        img = a.find("img") or (a.parent.find("img") if a.parent else None)
        if img and img.get("src", "").startswith("http") and img["src"] not in lst.images:
            lst.images.append(img["src"])
        lst.published_at = lst.published_at or received_at
        lst.raw = {"via": "email", "remitente": sender[:80]}
        out[key] = lst
    return [x for x in out.values() if x.price]


def _decode(value: str | None) -> str:
    return str(make_header(decode_header(value))) if value else ""


class EmailAlertsConnector(Connector):
    name = "email_alertas"

    def enabled(self) -> bool:
        return bool(self.cfg.get_path("fuentes.email_alertas.activo")) and bool(secret("IMAP_USER"))

    def fetch(self) -> Iterable[Listing]:
        host = secret("IMAP_HOST") or "imap.gmail.com"
        user, pwd = secret("IMAP_USER"), secret("IMAP_PASSWORD")
        if not user or not pwd:
            raise RuntimeError("Faltan IMAP_USER / IMAP_PASSWORD en .env")
        conf = self.cfg.get_path("fuentes.email_alertas", {})
        senders = [s.lower() for s in conf.get("remitentes", [])]
        box = imaplib.IMAP4_SSL(host)
        try:
            box.login(user, pwd)
            box.select(conf.get("carpeta", "INBOX"))
            crit = "(UNSEEN)" if conf.get("solo_no_leidos", True) else "ALL"
            _, data = box.search(None, crit)
            ids = data[0].split()[-200:]
            for msg_id in ids:
                _, msg_data = box.fetch(msg_id, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                sender = _decode(msg.get("From"))
                if senders and not any(s in sender.lower() for s in senders):
                    continue
                try:
                    received = parsedate_to_datetime(msg.get("Date")).isoformat()
                except Exception:
                    received = None
                html = ""
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "ignore")
                        break
                if not html:
                    continue
                for lst in parse_alert_email(html, received, sender):
                    yield lst
        finally:
            try:
                box.logout()
            except Exception:
                pass
