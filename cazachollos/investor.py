"""Perspectiva del inversor: ¿vale la pena hacer el viaje?

Calcula si un coche merece el desplazamiento desde la base del inversor.
Configuración en config.yaml → inversor:
  base: "Barcelona"          # ciudad/provincia de origen
  coste_km: 0.19             # €/km (combustible + desgaste)
  valor_hora: 25             # €/hora (coste de oportunidad)
  margen_minimo_viaje: 1500  # € de margen mínimo para que el viaje valga
  max_km_sin_hotel: 400      # km máximos sin necesitar hotel
  coste_hotel: 80            # € por noche de hotel
  presupuesto_max: 15000     # € máximo a pagar por un coche
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

    # Para Alemania: coste fijo aproximado del viaje
    if destination_country == "DE":
        return _german_trip_analysis(base, destination_province, margin, inv_cfg)

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


def _german_trip_analysis(
    base: str,
    city: str | None,
    margin: float | None,
    inv_cfg: dict,
) -> TripAnalysis:
    """Análisis simplificado para coches en Alemania."""
    # Coste aproximado de importar un coche de Alemania
    # Vuelo + tren + gestión: ~€300-500
    # Reregistro + ITV: ~€300
    # Transporte en barco/camión si no lo traes tú: ~€800-1500
    import_cost = float(inv_cfg.get("coste_importacion_de", 1800.0))
    margen_min = float(inv_cfg.get("margen_minimo_viaje", 1500.0))

    net_margin = (margin or 0.0) - import_cost
    worth = net_margin >= margen_min

    verdict = (
        f"{'VALE' if worth else 'NO vale'} la pena importar de Alemania: "
        f"margen neto {net_margin:.0f} € tras costes de importación ~{import_cost:.0f} €"
    )

    return TripAnalysis(
        base=base,
        destination=city or "Alemania",
        country="DE",
        distance_km=1800.0,
        duration_min=1200.0,
        fuel_cost=import_cost,
        time_cost=0,
        hotel_cost=0,
        total_trip_cost=import_cost,
        net_margin=net_margin,
        worth_trip=worth,
        score_penalty=15,
        verdict=verdict,
        flags=["Importación DE: homologación ITV", "Homologar luces y km"],
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
