"""Análisis de fotos con la API de Claude (Anthropic).

APAGADO POR DEFECTO — actívalo poniendo vision.activo = true en config.yaml.
¡Cuesta dinero! Cada coche analiza hasta vision.max_fotos fotos.

Requisito: ANTHROPIC_API_KEY en .env
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

from .config import Config, secret
from .models import Listing

log = logging.getLogger("cazachollos")

_PROMPT = """Eres un experto en inspección de coches de segunda mano.
Analiza estas fotos del anuncio y devuelve un JSON con exactamente estas claves:
- "riesgo_0_10": número entero 0-10 (0 = perfecto estado, 10 = gravemente dañado)
- "testigos_encendidos": true/false (¿hay testigos encendidos visibles en el cuadro?)
- "golpes_visibles": lista de strings con ubicación de cada golpe/arañazo visible (vacía si ninguno)
- "suciedad_excesiva": true/false (motor muy sucio, tapicería destrozada...)
- "resumen": frase de máx. 120 caracteres describiendo el estado general

Solo JSON, sin explicación adicional."""


def _fetch_image_b64(url: str, timeout: int = 15) -> tuple[str, str] | None:
    """Descarga una imagen y la devuelve como (base64, media_type)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CazachollosPersonal/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            ct = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
            if ct not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
                ct = "image/jpeg"
            return base64.standard_b64encode(data).decode(), ct
    except Exception as exc:
        log.debug("vision: no pude descargar %s: %s", url, exc)
        return None


def analyze_photos(lst: Listing, cfg: Config) -> dict | None:
    """Analiza las fotos del anuncio. Devuelve dict con resultado o None si falla/no aplica."""
    if not cfg.get_path("vision.activo", False):
        return None
    api_key = secret("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("vision: activo=true pero no hay ANTHROPIC_API_KEY en .env")
        return None

    images = lst.images[: cfg.get_path("vision.max_fotos", 4)]
    if not images:
        return None

    content: list = []
    for url in images:
        img = _fetch_image_b64(url)
        if img:
            b64, media_type = img
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64},
            })
    if not content:
        return None
    content.append({"type": "text", "text": _PROMPT})

    model = cfg.get_path("vision.modelo", "claude-sonnet-4-6")
    payload = json.dumps({
        "model": model,
        "max_tokens": 300,
        "messages": [{"role": "user", "content": content}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
        text = body["content"][0]["text"].strip()
        # Extraer el JSON aunque haya texto extra
        start, end = text.find("{"), text.rfind("}") + 1
        return json.loads(text[start:end]) if start >= 0 else None
    except Exception as exc:
        log.error("vision: error llamando a la API: %s", exc)
        return None
