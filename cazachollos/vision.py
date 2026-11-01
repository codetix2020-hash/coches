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


def vision_cost_estimate(cfg: Config) -> dict:
    """Devuelve el coste estimado por anuncio y mensual con los parámetros actuales.

    Modelo: claude-sonnet-5-5
    Precios (nov-2026): input $3/MTok, output $15/MTok (sin caché)
    Tokens por imagen 1280×960: ~1700 tokens (aprox. w*h/750)
    """
    model = cfg.get_path("vision.modelo", "claude-sonnet-5-5")
    max_fotos = cfg.get_path("vision.max_fotos", 4)
    score_threshold = cfg.get_path("vision.solo_si_score_mayor_que", 60)

    # Tokens estimados por imagen a resolución 1280×960 webp
    # Fórmula Anthropic: tokens ≈ (w × h) / 750   para imágenes sin cache
    tokens_por_foto = round(1280 * 960 / 750)  # ~1638 tokens
    tokens_prompt = 200
    tokens_output = 300

    input_tokens = max_fotos * tokens_por_foto + tokens_prompt
    # Precios en USD (claude-sonnet-5-5 a precios actuales)
    input_price_usd_per_mtok = 3.0
    output_price_usd_per_mtok = 15.0
    usd_eur = 0.93  # aproximado

    cost_usd = (input_tokens * input_price_usd_per_mtok + tokens_output * output_price_usd_per_mtok) / 1_000_000
    cost_eur = cost_usd * usd_eur

    return {
        "modelo": model,
        "max_fotos": max_fotos,
        "tokens_por_foto": tokens_por_foto,
        "tokens_input_total": input_tokens,
        "tokens_output_estimados": tokens_output,
        "coste_por_anuncio_usd": round(cost_usd, 4),
        "coste_por_anuncio_eur": round(cost_eur, 4),
        "solo_si_score_mayor": score_threshold,
        # Estimaciones mensuales según uso
        "mensual_10_por_dia_eur": round(cost_eur * 10 * 30, 2),
        "mensual_50_por_dia_eur": round(cost_eur * 50 * 30, 2),
        "nota": (
            f"Solo anuncios con score >{score_threshold} se analizan. "
            "Si el 10% de tus búsquedas pasa el filtro y buscas 50 coches/día, "
            f"son ~5 análisis/día = {round(cost_eur * 5 * 30, 2):.2f} €/mes."
        ),
    }


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
