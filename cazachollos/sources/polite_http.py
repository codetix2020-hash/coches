"""Descargas respetuosas: comprueba robots.txt, limita la velocidad, usa caché y un user-agent honesto.

No se salta captchas, logins ni bloqueos: si la web dice que no, no se descarga.
"""

from __future__ import annotations

import hashlib
import logging
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

from ..config import ROOT

log = logging.getLogger("cazachollos")
CACHE = ROOT / "data" / "cache"
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_last_hit: dict[str, float] = {}


class Blocked(Exception):
    """La web no permite esta descarga (robots.txt, 403, captcha...)."""


def _robots_for(base: str, ua: str) -> urllib.robotparser.RobotFileParser | None:
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = requests.get(f"{base}/robots.txt", headers={"User-Agent": ua}, timeout=15)
            if resp.status_code >= 400:
                # Sin robots.txt accesible: actuamos con prudencia y no rastreamos.
                _robots[base] = None
                return None
            rp.parse(resp.text.splitlines())
            _robots[base] = rp
        except requests.RequestException:
            _robots[base] = None
    return _robots[base]


def allowed(url: str, ua: str) -> bool:
    p = urlparse(url)
    rp = _robots_for(f"{p.scheme}://{p.netloc}", ua)
    return bool(rp and rp.can_fetch(ua, url))


def get(url: str, ua: str, pause: float = 8.0, cache_hours: float = 12.0) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".html")
    if key.exists() and time.time() - key.stat().st_mtime < cache_hours * 3600:
        return key.read_text(encoding="utf-8", errors="ignore")
    if not allowed(url, ua):
        raise Blocked(f"robots.txt no permite descargar {url} (o no se pudo leer)")
    host = urlparse(url).netloc
    wait = pause - (time.time() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(url, headers={"User-Agent": ua, "Accept-Language": "es-ES"}, timeout=25)
    _last_hit[host] = time.time()
    if resp.status_code in (401, 403, 429) or "captcha" in resp.text[:5000].lower():
        raise Blocked(f"{host} ha bloqueado o limitado el acceso ({resp.status_code}); no insistimos")
    resp.raise_for_status()
    key.write_text(resp.text, encoding="utf-8")
    return resp.text


def get_bytes(url: str, ua: str, pause: float = 2.0) -> bytes | None:
    host = urlparse(url).netloc
    wait = pause - (time.time() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    try:
        resp = requests.get(url, headers={"User-Agent": ua}, timeout=20)
        _last_hit[host] = time.time()
        return resp.content if resp.ok else None
    except requests.RequestException:
        return None


def domain_label(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.").removeprefix("es.")
    for name in ("coches.net", "wallapop", "milanuncios", "autoscout24", "autocasion", "coches.com",
                 "mobile.de", "pricauto", "trovit", "autouncle", "flexicar", "ocasionplus"):
        if name in host:
            return name.replace(".", "")
    return host.split(".")[0] or "web"


def ad_id_from_url(url: str) -> str:
    """ID estable por URL (quitando parámetros de seguimiento)."""
    p = urlparse(url)
    clean = f"{p.netloc.lower().removeprefix('www.')}{p.path.rstrip('/')}"
    return hashlib.sha1(clean.encode()).hexdigest()[:16]
