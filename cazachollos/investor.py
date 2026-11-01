"""Perspectiva del inversor: ¿vale la pena hacer el viaje?

Calcula si un coche merece el desplazamiento desde la base del inversor.
Configuración en config.yaml → inversor:
  base: "Barcelona"                # ciudad/provincia de origen
  coste_km: 0.19                   # €/km (combustible + desgaste)
  valor_hora: 25                   # €/hora (coste de oportunidad)
  margen_minimo_viaje: 1500        # € de margen mínimo para que el viaje valga
  max_km_sin_hotel: 400            # km máximos sin necesitar hotel
  coste_hotel: 80                  # € por noche de hotel
  presupuesto_max: 15000           # € máximo a pagar por un coche

  # Alemania (costes calculados por coche, no fijos):
  coste_transporte_de: 650         # transporte DEfault (vuelo+tren de regreso o camión)
  coste_itv_importacion: 350       # ITV de importación + homologación
  coste_gestoria_importacion: 300  # gestoría (extra por importación vs transferencia normal)
  # Impuesto de matriculación: se calcula según CO2 g/km (Ley 38/1992)
  # ITP: se usa itp.tipo_por_defecto de config.yaml (Catalunya = 5%)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .geo import PROVINCES, province_key, road_km_provinces

log = logging.getLogger("cazachollos")

# Coordenadas de Barcelona como base por defecto
_DEFAULT_BASE = "Barcelona"
_BCN_COORDS = (41.3851, 2.1734)


@dataclass
class TripAnalysis:
    """Análisis completo del viaje para adquirir un coche."""

    # Identificación
    base: str = "Barcelona"
    destination: str = ""
    country: str = "ES"

    # Distancia
    distance_km: float = 0.0
    duration_min: float = 0.0

    # Costes del viaje
    fuel_cost: float = 0.0       # coste de combustible/transporte
    time_cost: float = 0.0       # coste del tiempo invertido
    hotel_cost: float = 0.0      # hotel si necesario (noche)
    total_trip_cost: float = 0.0 # suma total

    # Decisión
    net_margin: float = 0.0      # margen neto del coche - coste viaje
    worth_trip: bool = False     # ¿vale la pena?
    score_penalty: float = 0.0  # penalización en el score por distancia

    # Mensaje para el inversor
    verdict: str = ""
    flags: list[str] = field(default_factory=list)


def trip_analysis(
    destination_province: str | None,
    margin: float | None,
    cfg,
    destination_country: str = "ES",
    listing=None,
) -> TripAnalysis | None:
    """Calcula el análisis del viaje para ir a comprar un coche.

    Args:
        destination_province: provincia/ciudad donde está el coche
        margin: margen neto esperado del coche (€)
        cfg: Config del sistema
        destination_country: 'ES' o 'DE'

    Returns:
        TripAnalysis o None si no se puede calcular
    """
    inv_cfg = cfg.get_path("inversor", {})
    base = inv_cfg.get("base", _DEFAULT_BASE)
    coste_km = float(inv_cfg.get("coste_km", 0.19))
    valor_hora = float(inv_cfg.get("valor_hora", 25.0))
    margen_min = float(inv_cfg.get("margen_minimo_viaje", 1500.0))
    max_km_hotel = float(inv_cfg.get("max_km_sin_hotel", 400.0))
    coste_hotel = float(inv_cfg.get("coste_hotel", 80.0))

    # Para Alemania: costes calculados por coche
    if destination_country == "DE":
        return _german_trip_analysis(base, destination_province, margin, inv_cfg, listing, cfg=cfg)

    if not destination_province:
        return None

    # Obtener distancia real
    route = road_km_provinces(base, destination_province)
    if not route:
        log.debug("investor: no route for %s → %s", base, destination_province)
        return None

    distance_km, duration_min = route

    # Costes
    fuel_cost = round(distance_km * 2 * coste_km, 0)  # ida y vuelta
    time_cost = round((duration_min * 2 / 60) * valor_hora, 0)  # ida y vuelta
    hotel_cost = coste_hotel if distance_km > max_km_hotel else 0.0
    total_trip = fuel_cost + time_cost + hotel_cost

    net_margin = (margin or 0.0) - total_trip

    # ¿Vale la pena?
    worth = net_margin >= margen_min

    # Penalización en score basada en distancia
    # 0-100km: 0 pts, 100-300km: -5 pts, 300-500km: -10 pts, >500km: -20 pts
    if distance_km <= 100:
        score_penalty = 0
    elif distance_km <= 300:
        score_penalty = 5
    elif distance_km <= 500:
        score_penalty = 10
    else:
        score_penalty = 20

    flags = []
    if hotel_cost > 0:
        flags.append(f"Necesita hotel ({distance_km:.0f} km)")
    if destination_province.lower() in ("las palmas", "santa cruz de tenerife", "illes balears"):
        flags.append("Isla: sumar ferry/avión")

    # Veredicto
    if not worth:
        deficit = margen_min - net_margin
        verdict = (
            f"NO vale la pena: margen neto {net_margin:.0f} € "
            f"(faltan {deficit:.0f} € para cubrir viaje de {total_trip:.0f} €)"
        )
    else:
        verdict = (
            f"VALE la pena: margen neto {net_margin:.0f} € "
            f"tras descontar {total_trip:.0f} € del viaje desde {base} "
            f"({distance_km:.0f} km, {duration_min:.0f} min)"
        )

    return TripAnalysis(
        base=base,
        destination=destination_province,
        country="ES",
        distance_km=distance_km,
        duration_min=duration_min,
        fuel_cost=fuel_cost,
        time_cost=time_cost,
        hotel_cost=hotel_cost,
        total_trip_cost=total_trip,
        net_margin=net_margin,
        worth_trip=worth,
        score_penalty=score_penalty,
        verdict=verdict,
        flags=flags,
    )


def _matriculacion_rate(co2_g_km: int) -> float:
    """Tipo del impuesto de matriculación según Ley 38/1992 (Art. 70 bis).

    Fuente: Ley 38/1992, de 28 de diciembre, de Impuestos Especiales.
    Tramos vigentes para turismos desde 2008:
      ≤ 120 g/km  → 0 %
      121-160 g/km → 4,75 %
      161-200 g/km → 9,75 %
      > 200 g/km  → 14,75 %
    """
    if co2_g_km <= 120:
        return 0.0
    elif co2_g_km <= 160:
        return 0.0475
    elif co2_g_km <= 200:
        return 0.0975
    else:
        return 0.1475


def _estimate_co2(fuel: str | None, power_cv: int | None) -> int:
    """Estima g/km de CO2 cuando el dato no está disponible en el anuncio."""
    cv = power_cv or 90
    if fuel in ("electrico",):
        return 0
    if fuel in ("hibrido", "hibrido_enchufable"):
        return 60
    if cv <= 90:
        return 125
    elif cv <= 130:
        return 140
    elif cv <= 180:
        return 160
    else:
        return 185


def _german_trip_analysis(
    base: str,
    city: str | None,
    margin: float | None,
    inv_cfg: dict,
    listing=None,
    itp_rate: float = 0.05,
    cfg=None,
) -> TripAnalysis:
    """Análisis de importación desde Alemania con costes calculados por coche.

    Desglose:
    1. Transporte: vuelo+tren de regreso (conduces tú) o camión portacoches
    2. ITV de importación + homologación (ajuste de luces, km a unidades SI...)
    3. Impuesto de matriculación (Ley 38/1992): depende de CO2 del coche
    4. ITP: tipo de la comunidad autónoma sobre el valor de compra
    5. Gestoría especial de importación
    Además: si el vendedor es un concesionario (profesional), el precio alemán
    incluye MwSt (IVA alemán 19%). Para exportación a otro estado UE, algunos
    concesionarios aplican exención (steuerfreie Ausfuhrlieferung) → precio neto
    ~16% inferior. Avisamos si el vendedor es profesional.
    """
    margen_min = float(inv_cfg.get("margen_minimo_viaje", 1500.0))

    # 1. Transporte: vuelo BCN→ciudad DE (~150€) + tren desde ciudad (~80€) + gasolina retorno
    transport = float(inv_cfg.get("coste_transporte_de", 650.0))

    # 2. ITV de importación + homologación
    itv_import = float(inv_cfg.get("coste_itv_importacion", 350.0))

    # 3. Impuesto de matriculación (Ley 38/1992) — basado en CO2
    purchase_price = (listing.price if listing else None) or 0.0
    if listing and listing.co2_g_km:
        co2 = listing.co2_g_km
        co2_source = f"{co2} g/km (dato del anuncio)"
    elif listing:
        co2 = _estimate_co2(listing.fuel, listing.power_cv)
        co2_source = f"~{co2} g/km (estimado según motor)"
    else:
        co2 = 140
        co2_source = f"~{co2} g/km (estimado por defecto)"
    mat_rate = _matriculacion_rate(co2)
    impuesto_mat = round(purchase_price * mat_rate, 0)

    # 4. ITP (Comunidad Autónoma del comprador — Catalunya = 5%)
    if cfg is not None:
        itp_rate = float(cfg.get_path("itp.tipo_por_defecto", 0.05))
    itp = round(purchase_price * itp_rate, 0)

    # 5. Gestoría (trámites de importación, más compleja que una transferencia normal)
    gestoria = float(inv_cfg.get("coste_gestoria_importacion", 300.0))

    total_import = transport + itv_import + impuesto_mat + itp + gestoria

    net_margin = (margin or 0.0) - total_import
    worth = net_margin >= margen_min

    # Flags informativos
    flags = [
        f"Impuesto matriculación: {mat_rate:.2%} sobre {purchase_price:,.0f} € = {impuesto_mat:,.0f} € (CO2 {co2_source})".replace(",", "."),
        f"ITP {itp_rate:.0%}: {itp:,.0f} €".replace(",", "."),
        f"Transporte+ITV+gestoría: {transport + itv_import + gestoria:,.0f} €".replace(",", "."),
    ]
    if listing and getattr(listing, "seller_type", "") == "profesional":
        flags.append(
            "Vendedor profesional: precio podría ser brutto (con MwSt 19%). "
            "Pregunta si aplica steuerfreie Ausfuhrlieferung (exportación sin IVA)"
        )

    verdict = (
        f"{'VALE' if worth else 'NO vale'} la pena importar de Alemania: "
        f"margen neto {net_margin:.0f} € tras costes de importación {total_import:.0f} € "
        f"(transporte {transport:.0f} + ITV {itv_import:.0f} + matric. {impuesto_mat:.0f} + ITP {itp:.0f} + gestoria {gestoria:.0f})"
    )

    return TripAnalysis(
        base=base,
        destination=city or "Alemania",
        country="DE",
        distance_km=1800.0,
        duration_min=1200.0,
        fuel_cost=transport,
        time_cost=itv_import + gestoria,
        hotel_cost=impuesto_mat + itp,
        total_trip_cost=total_import,
        net_margin=net_margin,
        worth_trip=worth,
        score_penalty=15,
        verdict=verdict,
        flags=flags,
    )


def format_trip_card(analysis: TripAnalysis) -> str:
    """Formatea el análisis del viaje para mostrar en consola/panel."""
    icon = "✈" if analysis.country == "DE" else ("🚗" if analysis.worth_trip else "❌")
    lines = [
        f"{icon} Viaje desde {analysis.base} → {analysis.destination}",
        f"   Distancia: {analysis.distance_km:.0f} km · {analysis.duration_min:.0f} min",
        f"   Combustible: {analysis.fuel_cost:.0f} € · Tiempo: {analysis.time_cost:.0f} €",
    ]
    if analysis.hotel_cost:
        lines.append(f"   Hotel: {analysis.hotel_cost:.0f} €")
    lines.append(f"   Total viaje: {analysis.total_trip_cost:.0f} €")
    lines.append(f"   Margen neto: {analysis.net_margin:.0f} €")
    lines.append(f"   → {analysis.verdict}")
    return "\n".join(lines)
