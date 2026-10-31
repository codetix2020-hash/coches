"""Costes de comprar y revender: ITP (con tablas de Hacienda), transferencia, reparaciones, etc."""

from __future__ import annotations

import csv
from datetime import date
from functools import lru_cache
from pathlib import Path

from .config import ROOT, Config
from .geo import needs_ferry, road_km
from .models import Listing
from .normalize import norm_text, normalize_make, slug


@lru_cache(maxsize=4)
def _load_hacienda(path: str) -> list[dict]:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def hacienda_value(lst: Listing, cfg: Config) -> float | None:
    """Valor fiscal = precio medio de la tabla de Hacienda × % por antigüedad.

    Formato CSV: marca,modelo,anio_desde,anio_hasta,combustible,cv,precio_medio
    """
    rows = _load_hacienda(cfg.get_path("itp.tabla_precios_csv", ""))
    if not rows or not lst.make or not lst.year:
        return None
    best = None
    for r in rows:
        if normalize_make(r.get("marca")) != lst.make:
            continue
        model_ok = slug(r.get("modelo")) == lst.model or (lst.model or "") in (slug(r.get("modelo")) or "")
        if not model_ok:
            continue
        y0, y1 = int(r.get("anio_desde") or 0), int(r.get("anio_hasta") or 9999)
        if not (y0 <= lst.year <= y1):
            continue
        if r.get("combustible") and lst.fuel and norm_text(r["combustible"])[:3] != lst.fuel[:3]:
            continue
        score = 0
        if r.get("cv") and lst.power_cv:
            score = -abs(int(r["cv"]) - lst.power_cv)
        if best is None or score > best[0]:
            best = (score, float(r["precio_medio"]))
    if best is None:
        return None
    years = max(1, date.today().year - lst.year + 1)
    pct = 0.10
    for limit, value in cfg.get_path("itp.depreciacion_hacienda", []):
        if years <= limit:
            pct = value
            break
    return round(best[1] * pct, 2)


def itp_cost(lst: Listing, buy_price: float, cfg: Config) -> tuple[float, str, float | None]:
    regimen = cfg.get_path("yo.regimen", "particular")
    hv = hacienda_value(lst, cfg)
    if regimen == "rebu" and cfg.get_path("itp.exento_si_profesional", False):
        return 0.0, "exento (compraventa profesional para reventa; VERIFICAR con gestor)", hv
    ccaa = cfg.get_path("yo.comunidad_autonoma")
    rate = cfg.get_path("itp.tipos_ccaa", {}).get(ccaa, cfg.get_path("itp.tipo_por_defecto", 0.04))
    base = max(buy_price, hv or 0)
    note = f"{rate:.0%} sobre {base:,.0f} €".replace(",", ".")
    if hv and hv > buy_price:
        note += " (Hacienda valora el coche por encima de lo que pagas)"
    elif not hv:
        note += " (sin tabla de Hacienda cargada: base = precio de compra)"
    return round(base * rate, 2), note, hv


def repair_estimate(lst: Listing, cfg: Config) -> tuple[float, list[str]]:
    r = cfg.get("reparaciones", {})
    age = date.today().year - lst.year if lst.year else 10
    total, notes = 0.0, []
    for band, value in r.get("base_por_antiguedad", {}).items():
        lo, hi = (int(x) for x in band.split("-"))
        if lo <= age <= hi:
            total += value
            notes.append(f"mantenimiento básico ({age} años): {value} €")
            break
    if lst.km and lst.km > 150000:
        extra = r.get("extra_por_km_mas_de_150000", 0)
        total += extra
        notes.append(f"más de 150.000 km: {extra} €")
    text = norm_text(f"{lst.title} {lst.description}")
    for word, value in r.get("palabras_clave", {}).items():
        if norm_text(word) in text:
            # Si el anuncio dice que está cambiado/nuevo, no sumamos.
            idx = text.find(norm_text(word))
            ctx = text[max(0, idx - 25): idx + len(word) + 25]
            if any(ok in ctx for ok in ("nuevo", "cambiad", "recien", "hecha", "hecho", "sustituid")):
                continue
            total += value
            notes.append(f"anuncio menciona «{word}»: {value} €")
    return total, notes


def compute_costs(lst: Listing, sale_price: float | None, cfg: Config) -> tuple[dict, float, float | None]:
    c = cfg.get("costes", {})
    buy = (lst.price or 0) * (1 - cfg.get_path("compra.descuento_negociacion_compra", 0.0))
    costs: dict[str, dict] = {}

    itp, itp_note, hv = itp_cost(lst, buy, cfg)
    costs["itp"] = {"eur": itp, "nota": itp_note}
    costs["transferencia"] = {"eur": c.get("tasa_dgt_transferencia", 55.70) + c.get("gestoria", 0),
                              "nota": "tasa DGT 1.5 + gestoría"}
    costs["informes"] = {"eur": c.get("informe_dgt", 8.67) + c.get("informe_historial", 0),
                         "nota": "informe DGT completo (+ historial si lo usas)"}
    rep, rep_notes = repair_estimate(lst, cfg)
    costs["reparaciones"] = {"eur": rep, "nota": "; ".join(rep_notes)}
    costs["itv"] = {"eur": c.get("itv_previa_venta", 45), "nota": "ITV antes de vender"}
    costs["limpieza"] = {"eur": c.get("limpieza_detailing", 120), "nota": "limpieza / detailing"}
    costs["anuncio"] = {"eur": c.get("fotos_y_anuncio", 30), "nota": "destacar anuncio"}

    dist = road_km(cfg.get_path("yo.provincia"), lst.province)
    if dist is None:
        travel, tnote = 80.0, "provincia desconocida: estimación fija"
    else:
        travel = dist * 2 * c.get("coste_km_desplazamiento", 0.2)
        tnote = f"~{dist:.0f} km por carretera (ida y vuelta)"
        if dist > 150:
            travel += c.get("coste_retorno_si_lejos", 60)
            tnote += " + volver"
        if needs_ferry(cfg.get_path("yo.provincia"), lst.province):
            travel += 350
            tnote += " + ferry (aprox.)"
    costs["desplazamiento"] = {"eur": round(travel, 2), "nota": tnote, "km": dist}

    days = cfg.get_path("objetivos.dias_venta_estimados", 30)
    capital = buy * c.get("coste_capital_anual", 0.06) * days / 365 + days * c.get("seguro_dias_hasta_venta", 2)
    costs["dinero_parado"] = {"eur": round(capital, 2), "nota": f"{days} días de capital inmovilizado + seguro"}
    costs["imprevistos"] = {"eur": round(buy * c.get("colchon_imprevistos_pct", 0.03), 2),
                            "nota": "colchón para sorpresas"}
    if sale_price and c.get("provision_garantia_pct"):
        costs["garantia"] = {"eur": round(sale_price * c["provision_garantia_pct"], 2),
                             "nota": "provisión garantía 1 año (vendedor profesional)"}

    total = round(sum(v["eur"] for v in costs.values()), 2)
    if sale_price and cfg.get_path("yo.regimen") == "rebu":
        gross_margin = sale_price - buy - total
        iva = max(0.0, gross_margin) * cfg.get_path("rebu.iva", 0.21) / (1 + cfg.get_path("rebu.iva", 0.21))
        costs["iva_rebu"] = {"eur": round(iva, 2), "nota": "IVA REBU sobre el margen"}
        total = round(total + iva, 2)
    return costs, total, hv
