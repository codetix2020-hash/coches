"""Flujo completo: guardar → deduplicar → valorar → costes → alarmas → puntuar → avisar."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from . import db
from .config import Config
from .costs import compute_costs
from .dedupe import assign_group
from .models import Evaluation, Flag, Listing
from .normalize import normalize_listing
from .redflags import detect_flags
from .scoring import passes_filters, score
from .valuation import estimate_market

log = logging.getLogger("cazachollos")


@dataclass
class Result:
    listing_id: int
    listing: Listing
    evaluation: Evaluation
    is_new: bool
    in_filters: bool
    filter_reason: str
    duplicate_of: list[str]


def evaluate(conn: sqlite3.Connection | None, lst: Listing, cfg: Config,
             listing_id: int | None = None, group_id: int | None = None) -> Evaluation:
    est = estimate_market(conn, lst, cfg, listing_id, group_id) if conn else None
    market = est.market_price if est else None
    sale = round(market * (1 - cfg.get_path("venta.descuento_negociacion_venta", 0.06)), -1) if market else None
    costs, total, hv = compute_costs(lst, sale, cfg)
    buy = (lst.price or 0) * (1 - cfg.get_path("compra.descuento_negociacion_compra", 0.0))
    margin = round(sale - buy - total, 0) if sale else None
    roi = (margin / (buy + total)) if margin is not None and (buy + total) > 0 else None
    flags = detect_flags(conn, lst, listing_id, market, cfg)
    if est and est.comparables_n == 0:
        flags.append(Flag("sin_comparables", "leve", "aún no hay coches parecidos en la base para comparar"))
    sc, reasons = score(lst, market, margin, roi, est.confidence if est else 0.0,
                        est.comparables_n if est else 0, flags, cfg)
    if est and est.comparables_n:
        reasons.insert(0, f"mercado ≈ {market:,.0f} € ({est.method}); venta realista ≈ {sale:,.0f} €".replace(",", "."))
    return Evaluation(
        market_price=market, sale_price=sale, comparables_n=est.comparables_n if est else 0,
        confidence=est.confidence if est else 0.0, costs=costs, total_costs=total, margin=margin,
        roi=round(roi, 3) if roi is not None else None, score=sc, flags=flags, reasons=reasons,
        hacienda_value=hv,
    )


def should_alert(res: Result, cfg: Config) -> bool:
    ev = res.evaluation
    if not res.in_filters:
        return False
    if ev.score < cfg.get_path("alertas.score_minimo", 70):
        return False
    if ev.margin is None or ev.margin < cfg.get_path("objetivos.margen_minimo_eur", 1000):
        return False
    if cfg.get_path("alertas.bloquear_si_alarma_grave", True) and any(f.severity == "grave" for f in ev.flags):
        return False
    return True


def process(conn: sqlite3.Connection, listings: list[Listing], cfg: Config,
            notifier=None, vision=None) -> list[Result]:
    results: list[Result] = []
    stored: list[tuple[int, Listing, bool]] = []
    # 1) Guardar todo primero: así cada anuncio puede compararse con los del mismo lote.
    for lst in listings:
        normalize_listing(lst)
        listing_id, is_new, _ = db.upsert_listing(conn, lst)
        stored.append((listing_id, lst, is_new))
    # 2) Deduplicar, valorar y avisar.
    for listing_id, lst, is_new in stored:
        group_id, dup = assign_group(conn, listing_id, cfg)
        ev = evaluate(conn, lst, cfg, listing_id, group_id)
        ok, why = passes_filters(lst, cfg)
        res = Result(listing_id, lst, ev, is_new, ok, why, dup)
        if vision is not None and ok and ev.score >= cfg.get_path("vision.solo_si_score_mayor_que", 60):
            vres = vision(lst)
            if vres:
                db.save_vision(conn, listing_id, vres)
                ev = _apply_vision(ev, vres)
                res.evaluation = ev
        db.save_evaluation(conn, listing_id, res.evaluation)
        if notifier is not None and should_alert(res, cfg):
            for channel in cfg.get_path("alertas.canales", ["telegram"]):
                if not db.alert_already_sent(conn, listing_id, channel):
                    if notifier(channel, res):
                        db.mark_alert_sent(conn, listing_id, channel)
        results.append(res)
    return results


def _apply_vision(ev: Evaluation, v: dict) -> Evaluation:
    risk = v.get("riesgo_0_10")
    if isinstance(risk, (int, float)) and risk >= 7:
        ev.flags.append(Flag("vision", "media", f"fotos: {v.get('resumen', 'riesgo alto')}"))
        ev.score = max(0, ev.score - 12)
        ev.reasons.append(f"⚠ análisis de fotos: riesgo {risk}/10 (−12)")
    elif isinstance(risk, (int, float)):
        ev.reasons.append(f"análisis de fotos: riesgo {risk}/10")
    if v.get("testigos_encendidos"):
        ev.flags.append(Flag("testigos", "media", "testigos encendidos en el cuadro"))
    return ev
