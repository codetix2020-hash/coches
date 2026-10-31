"""Estima el precio de mercado de un coche comparándolo con anuncios similares."""

from __future__ import annotations

import math
import sqlite3
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .config import Config
from .models import Listing


@dataclass
class MarketEstimate:
    market_price: float | None
    comparables_n: int
    confidence: float
    method: str
    comparable_ids: list[int]
    spread: float | None = None  # dispersión relativa (IQR / mediana)


def _age(year: int | None) -> float | None:
    return None if not year else max(0.0, date.today().year - year + 0.5)


def _fit_log_linear(rows: list[tuple[float, float, float]]) -> tuple[float, float, float] | None:
    """Ajusta log(precio) = a + b*edad + c*(km/10000) por mínimos cuadrados (sin numpy)."""
    n = len(rows)
    if n < 8:
        return None
    xs1 = [r[0] for r in rows]
    xs2 = [r[1] for r in rows]
    ys = [math.log(r[2]) for r in rows]
    m1, m2, my = sum(xs1) / n, sum(xs2) / n, sum(ys) / n
    s11 = sum((x - m1) ** 2 for x in xs1)
    s22 = sum((x - m2) ** 2 for x in xs2)
    s12 = sum((a - m1) * (b - m2) for a, b in zip(xs1, xs2))
    s1y = sum((a - m1) * (y - my) for a, y in zip(xs1, ys))
    s2y = sum((b - m2) * (y - my) for b, y in zip(xs2, ys))
    det = s11 * s22 - s12 ** 2
    if abs(det) < 1e-9:
        return None
    b = (s1y * s22 - s2y * s12) / det
    c = (s2y * s11 - s1y * s12) / det
    # Sanidad: los coches pierden valor con edad y km. Si sale al revés, no fiarse.
    if b > 0.02 or c > 0.02 or b < -0.4 or c < -0.3:
        return None
    a = my - b * m1 - c * m2
    return a, b, c


def find_comparables(conn: sqlite3.Connection, lst: Listing, listing_id: int | None,
                     group_id: int | None, cfg: Config) -> list[sqlite3.Row]:
    v = cfg.get("valoracion", {})
    if not lst.make or not lst.model:
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=v.get("ventana_dias_comparables", 120))).isoformat()
    params: list = [lst.make, lst.model, since]
    sql = """SELECT * FROM listings WHERE make=? AND model=? AND last_seen >= ?
             AND price IS NOT NULL AND price > 300"""
    if listing_id:
        sql += " AND id != ?"
        params.append(listing_id)
    if group_id:
        sql += " AND (group_id IS NULL OR group_id != ?)"
        params.append(group_id)
    if lst.fuel:
        sql += " AND (fuel = ? OR fuel IS NULL)"
        params.append(lst.fuel)
    if lst.transmission:
        sql += " AND (transmission = ? OR transmission IS NULL)"
        params.append(lst.transmission)
    if lst.year:
        tol = v.get("anios_tolerancia", 2)
        sql += " AND year BETWEEN ? AND ?"
        params += [lst.year - tol, lst.year + tol]
    if v.get("usar_solo_profesionales_para_valorar") or cfg.get_path("venta.usar_solo_profesionales_para_valorar"):
        sql += " AND seller_type='profesional'"
    rows = conn.execute(sql, params).fetchall()
    if lst.km is not None:
        tol = v.get("km_tolerancia_pct", 0.45)
        lo, hi = lst.km * (1 - tol) - 15000, lst.km * (1 + tol) + 15000
        rows = [r for r in rows if r["km"] is None or lo <= r["km"] <= hi]
    # Un coche duplicado en varias webs cuenta una sola vez.
    seen, unique = set(), []
    for r in rows:
        key = r["group_id"] or r["id"]
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def estimate_market(conn: sqlite3.Connection, lst: Listing, cfg: Config,
                    listing_id: int | None = None, group_id: int | None = None) -> MarketEstimate:
    v = cfg.get("valoracion", {})
    comps = find_comparables(conn, lst, listing_id, group_id, cfg)
    if not comps:
        return MarketEstimate(None, 0, 0.0, "sin comparables", [])

    age_t = _age(lst.year)
    km_t = (lst.km or 0) / 10000
    data = [(_age(r["year"]) or age_t or 8, (r["km"] or lst.km or 0) / 10000, r["price"]) for r in comps]
    fit = _fit_log_linear(data)
    dep_year = v.get("depreciacion_anual", 0.08)
    dep_km = v.get("depreciacion_por_10000km", 0.015)

    adjusted = []
    for age_c, km_c, price in data:
        if fit:
            _, b, c = fit
            factor = math.exp(b * ((age_t or age_c) - age_c) + c * (km_t - km_c))
        else:
            factor = (1 - dep_year) ** ((age_t or age_c) - age_c) * (1 - dep_km) ** (km_t - km_c)
        adjusted.append(price * max(0.5, min(1.6, factor)))

    adjusted.sort()
    # Recorte de extremos (anuncios absurdos o chollos falsos) si hay datos suficientes.
    if len(adjusted) >= 10:
        k = len(adjusted) // 10
        adjusted = adjusted[k:-k]
    median = statistics.median(adjusted)
    spread = None
    if len(adjusted) >= 4:
        q = statistics.quantiles(adjusted, n=4)
        spread = (q[2] - q[0]) / median if median else None

    n = len(comps)
    conf = min(1.0, n / max(1, v.get("min_comparables", 5) * 3))
    if n < v.get("min_comparables", 5):
        conf *= 0.6
    if spread is not None:
        conf *= max(0.3, 1 - spread)
    method = "regresión edad+km" if fit else "mediana ajustada"
    return MarketEstimate(round(median, -1), n, round(conf, 2), method, [r["id"] for r in comps], spread)
