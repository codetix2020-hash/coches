"""Puntuación 0-100 de cada oportunidad, con los motivos explicados."""

from __future__ import annotations

from datetime import datetime, timezone

from .config import Config
from .geo import road_km
from .models import Flag, Listing

PENALTY = {"grave": 40, "media": 12, "leve": 3}

# ── Etiqueta tipo CarGurus ────────────────────────────────────────────────────

_LABEL_THRESHOLDS = [
    (80, "Chollo"),
    (65, "Bueno"),
    (50, "Justo"),
    (35, "Caro"),
    (0,  "Muy caro"),
]


def cargurus_label(ev) -> str:
    """Devuelve 'Chollo', 'Bueno', 'Justo', 'Caro', 'Muy caro' o 'Sin valoración'."""
    if ev.market_price is None or ev.comparables_n == 0:
        return "Sin valoración"
    for threshold, label in _LABEL_THRESHOLDS:
        if ev.score >= threshold:
            return label
    return "Muy caro"


def passes_filters(lst: Listing, cfg: Config) -> tuple[bool, str]:
    b = cfg.get("busqueda", {})
    if lst.price is None:
        return False, "sin precio"
    if lst.price < b.get("precio_min", 0) or lst.price > b.get("precio_max", 1e9):
        return False, "fuera de presupuesto"
    if lst.year and lst.year < b.get("anio_min", 0):
        return False, "demasiado antiguo"
    if lst.km and lst.km > b.get("km_max", 1e9):
        return False, "demasiados km"
    if b.get("combustibles") and lst.fuel and lst.fuel not in b["combustibles"]:
        return False, "combustible no deseado"
    if b.get("cambios") and lst.transmission and lst.transmission not in b["cambios"]:
        return False, "cambio no deseado"
    if b.get("marcas_incluir") and lst.make not in b["marcas_incluir"]:
        return False, "marca no incluida"
    if lst.make in (b.get("marcas_excluir") or []):
        return False, "marca excluida"
    if b.get("tipo_vendedor") and lst.seller_type not in b["tipo_vendedor"]:
        return False, "tipo de vendedor"
    dist = road_km(cfg.get_path("yo.provincia"), lst.province)
    if dist is not None and dist > b.get("radio_km", 1e9):
        return False, f"a {dist:.0f} km"
    return True, ""


def _minutes_since(published_at: str | None) -> float | None:
    if not published_at:
        return None
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 60


def score(lst: Listing, market: float | None, margin: float | None, roi: float | None,
          confidence: float, comparables_n: int, flags: list[Flag], cfg: Config) -> tuple[int, list[str]]:
    reasons: list[str] = []
    pts = 0.0
    min_margin = cfg.get_path("objetivos.margen_minimo_eur", 1000)

    if margin is not None:
        m = max(0.0, min(1.0, margin / (2 * min_margin)))
        pts += 45 * m
        reasons.append(f"margen neto estimado {margin:,.0f} € (+{45 * m:.0f})".replace(",", "."))
    else:
        reasons.append("sin precio de mercado fiable: no se puede calcular margen")
    if roi is not None:
        r = max(0.0, min(1.0, roi / 0.30))
        pts += 15 * r
        reasons.append(f"rentabilidad {roi:.0%} (+{15 * r:.0f})")
    if market and lst.price:
        disc = 1 - lst.price / market
        d = max(0.0, min(1.0, (disc - 0.05) / 0.25))
        pts += 15 * d
        reasons.append(f"{disc:.0%} por debajo del mercado (+{15 * d:.0f})")
    pts += 10 * confidence
    reasons.append(f"confianza de la valoración {confidence:.0%} con {comparables_n} comparables (+{10 * confidence:.0f})")

    mins = _minutes_since(lst.published_at)
    if mins is not None:
        f = 10 if mins < 30 else 7 if mins < 120 else 4 if mins < 720 else 1
        pts += f
        reasons.append(f"publicado hace {mins:.0f} min (+{f})")
    else:
        pts += 3
    liq = min(5.0, comparables_n / 6)
    pts += liq

    for fl in flags:
        if fl.severity == "positiva":
            pts += 3
            reasons.append(f"✓ {fl.message} (+3)")
        else:
            pts -= PENALTY.get(fl.severity, 0)
            reasons.append(f"⚠ {fl.message} (−{PENALTY.get(fl.severity, 0)})")
    if any(f.severity == "grave" for f in flags):
        pts = min(pts, 30)
        reasons.append("tope de 30 puntos por alarma grave")
    return int(max(0, min(100, round(pts)))), reasons
