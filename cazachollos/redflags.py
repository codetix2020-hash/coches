"""Señales de alarma (estafa, km raros, averías) y señales positivas (vendedor con prisa)."""

from __future__ import annotations

import re
import sqlite3
from datetime import date

from .config import Config
from .models import Flag, Listing
from .normalize import norm_text

SCAM_PATTERNS = [
    (r"pago por adelantado|pagar por adelantado|adelant\w* (el )?pago|senal antes de ver|reserva sin ver",
     "pide pagar antes de ver el coche"),
    (r"estoy (fuera|en el extranjero)|vivo (fuera|en el extranjero)|destinad[oa] (en|a) |militar",
     "vendedor «fuera de España» (patrón típico de estafa)"),
    (r"(envio|enviar|transportista|agencia de transporte).{0,40}(coche|vehiculo)|te lo envio",
     "ofrece enviar el coche sin verlo"),
    (r"western union|moneygram|paypal amigos|bizum.{0,20}(senal|reserva)|tarjeta regalo",
     "medio de pago no seguro"),
    (r"solo (por )?(whatsapp|email|correo)|no atiendo llamadas|contactar (solo )?por (email|correo)",
     "evita hablar por teléfono"),
]

LEGAL_PATTERNS = [
    (r"sin papeles|sin documentacion|papeles (en tramite|pendientes)|sin ficha", "grave", "sin papeles o documentación incompleta"),
    (r"embargad|embargo|reserva de dominio|precintad", "grave", "posibles cargas (embargo / reserva de dominio)"),
    (r"solo exportacion|para exportar|despiece|para piezas", "grave", "solo exportación / piezas"),
    (r"importad\w*.{0,30}(sin matricular|sin homologar|matricula extranjera)|sin matricular", "media", "importado sin matricular en España"),
    (r"sin itv|itv caducada|itv vencida|itv desfavorable|no pasa (la )?itv", "media", "ITV caducada o desfavorable"),
    (r"siniestro|siniestrado|accidentado|dano estructural|chasis", "media", "posible siniestro o daño estructural"),
    (r"no arranca|motor (gripado|roto)|biela|junta de culata", "media", "avería mecánica grave"),
    (r"km no reales|cuentakilometros (cambiado|sustituido)|km (sin|no) garantizad", "grave", "kilometraje no garantizado"),
]

POSITIVE_PATTERNS = [
    (r"\burge\b|urgente|por traslado|por viaje|necesito vender|precio negociable|acepto ofertas", "vendedor con prisa / negociable"),
    (r"libro de mantenimiento|revisiones (en|de) (la )?(casa|concesionario|oficial)|todas las revisiones", "historial de mantenimiento"),
    (r"unico (propietario|dueno)|un solo (propietario|dueno)", "único propietario"),
    (r"garaje|dormido en garaje", "dormido en garaje"),
    (r"(distribucion|embrague) (recien )?(cambiad|nuev|hech)", "mantenimiento caro ya hecho"),
]


def detect_flags(conn: sqlite3.Connection | None, lst: Listing, listing_id: int | None,
                 market_price: float | None, cfg: Config) -> list[Flag]:
    a = cfg.get("alarmas", {})
    flags: list[Flag] = []
    text = norm_text(f"{lst.title} {lst.description}")

    if market_price and lst.price:
        ratio = lst.price / market_price
        if ratio < a.get("precio_estafa_ratio", 0.55):
            flags.append(Flag("precio_estafa", "grave",
                              f"precio al {ratio:.0%} del mercado: demasiado bueno para ser verdad"))
        elif ratio < a.get("precio_sospechoso_ratio", 0.70):
            flags.append(Flag("precio_sospechoso", "media",
                              f"precio al {ratio:.0%} del mercado: comprueba por qué"))

    for pattern, msg in SCAM_PATTERNS:
        if re.search(pattern, text):
            flags.append(Flag("estafa_texto", "grave", msg))
    for pattern, sev, msg in LEGAL_PATTERNS:
        if re.search(pattern, text):
            flags.append(Flag("legal_mecanica", sev, msg))
    for pattern, msg in POSITIVE_PATTERNS:
        if re.search(pattern, text):
            flags.append(Flag("positiva", "positiva", msg))

    if lst.year and lst.km is not None:
        age = max(1, date.today().year - lst.year)
        per_year = lst.km / age
        if age >= 5 and per_year < a.get("km_anuales_min", 3000):
            flags.append(Flag("km_bajos", "media",
                              f"solo {per_year:,.0f} km/año: pide historial (posibles km bajados)".replace(",", ".")))
        if per_year > a.get("km_anuales_max", 45000):
            flags.append(Flag("km_altos", "leve", f"{per_year:,.0f} km/año: uso intensivo".replace(",", ".")))

    if len(lst.images) < a.get("fotos_minimas", 3) and lst.source not in ("email", "manual"):
        flags.append(Flag("pocas_fotos", "leve", f"solo {len(lst.images)} fotos"))
    if not lst.description or len(lst.description) < 40:
        flags.append(Flag("sin_descripcion", "leve", "descripción muy pobre"))

    if conn is not None and listing_id:
        from .dedupe import reused_photos

        if reused_photos(conn, listing_id, cfg):
            flags.append(Flag("foto_reutilizada", "grave", "sus fotos aparecen en otro anuncio distinto"))
        hist = conn.execute(
            "SELECT price FROM price_history WHERE listing_id=? ORDER BY seen_at", (listing_id,)
        ).fetchall()
        if len(hist) >= 2 and hist[0]["price"] > hist[-1]["price"]:
            drop = 1 - hist[-1]["price"] / hist[0]["price"]
            flags.append(Flag("bajada_precio", "positiva", f"ha bajado el precio un {drop:.0%}"))
        group = conn.execute("SELECT group_id FROM listings WHERE id=?", (listing_id,)).fetchone()
        if group and group["group_id"]:
            others = conn.execute(
                "SELECT source, price FROM listings WHERE group_id=? AND id != ?", (group["group_id"], listing_id)
            ).fetchall()
            for o in others:
                if o["price"] and lst.price and abs(o["price"] - lst.price) > 200:
                    flags.append(Flag("precio_distinto", "leve",
                                      f"en {o['source']} está a {o['price']:,.0f} €".replace(",", ".")))
    return flags
