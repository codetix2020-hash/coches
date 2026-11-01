"""Tests de integración real con AutoScout24 y OSRM.

Estos tests hacen peticiones REALES a internet.
- NO se ejecutan por defecto (pytest.ini → addopts = -m "not integration")
- Para ejecutarlos manualmente: pytest -m integration
- Útiles para verificar que los conectores siguen funcionando.
"""

import pytest

# Mark all tests in this module as integration (not run by default)
pytestmark = pytest.mark.integration


def test_autoscout24_es_returns_listings(cfg):
    """Verifica que AutoScout24.es devuelve anuncios reales."""
    cfg.setdefault("fuentes", {})["autoscout24"] = {
        "activo": True,
        "paises": ["ES"],
        "marcas": ["volkswagen"],
        "precio_max": 12000,
        "km_max": 200000,
        "anio_min": 2015,
        "paginas": 1,
        "delay_segundos": 0,
    }
    from cazachollos.sources.autoscout24 import AutoScout24Connector

    connector = AutoScout24Connector(cfg)
    assert connector.enabled()

    listings = list(connector.fetch())
    assert len(listings) >= 10, f"Expected >=10 listings, got {len(listings)}"

    # Verify data quality
    first = listings[0]
    assert first.price is not None and first.price > 0, "Price should be set"
    assert first.make is not None and len(first.make) > 0, "Make should be set"
    assert first.model is not None and len(first.model) > 0, "Model should be set"
    assert first.url and first.url.startswith("https://"), "URL should be valid"
    assert first.source == "autoscout24_es"

    # At least some listings should have year
    with_year = [l for l in listings if l.year is not None]
    assert len(with_year) > 5, f"Only {len(with_year)} listings have year, expected >5"

    # At least some should have images
    with_images = [l for l in listings if l.images]
    assert len(with_images) > 5, f"Only {len(with_images)} listings have images"


def test_autoscout24_de_returns_listings(cfg):
    """Verifica que AutoScout24.de (mercado alemán) devuelve anuncios reales."""
    cfg.setdefault("fuentes", {})["autoscout24"] = {
        "activo": True,
        "paises": ["DE"],
        "marcas": ["volkswagen"],
        "precio_max": 10000,
        "km_max": 200000,
        "anio_min": 2015,
        "paginas": 1,
        "delay_segundos": 0,
    }
    from cazachollos.sources.autoscout24 import AutoScout24Connector

    connector = AutoScout24Connector(cfg)
    listings = list(connector.fetch())
    assert len(listings) >= 10, f"Expected >=10 German listings, got {len(listings)}"

    # All German listings should have source autoscout24_de
    assert all(l.source == "autoscout24_de" for l in listings)


def test_autoscout24_year_extraction(cfg):
    """Verifica que el año se extrae correctamente de vehicleDetails."""
    cfg.setdefault("fuentes", {})["autoscout24"] = {
        "activo": True,
        "paises": ["ES"],
        "marcas": ["volkswagen"],
        "precio_max": 15000,
        "km_max": 200000,
        "anio_min": 2015,
        "paginas": 1,
        "delay_segundos": 0,
    }
    from cazachollos.sources.autoscout24 import AutoScout24Connector

    connector = AutoScout24Connector(cfg)
    listings = list(connector.fetch())

    # At least 80% should have year
    with_year = [l for l in listings if l.year is not None]
    pct = len(with_year) / len(listings) if listings else 0
    assert pct >= 0.8, f"Only {pct:.0%} of listings have year. Expected >=80%"

    # Years should be reasonable (2015-2026)
    for l in with_year:
        assert 2015 <= l.year <= 2026, f"Unreasonable year {l.year} for {l.title}"


def test_osrm_barcelona_to_madrid(cfg):
    """Verifica la distancia real Barcelona → Madrid via OSRM."""
    from cazachollos.geo import road_km_real

    result = road_km_real(41.3851, 2.1734, 40.4168, -3.7038)
    assert result is not None, "OSRM should return a result"
    km, minutes = result
    # Barcelona to Madrid is ~600-650 km
    assert 550 <= km <= 700, f"Expected 550-700 km, got {km}"
    # Should take 5-8 hours
    assert 250 <= minutes <= 500, f"Expected 250-500 min, got {minutes}"


def test_osrm_barcelona_to_granollers(cfg):
    """Verifica la distancia Barcelona → Granollers (misma provincia)."""
    from cazachollos.geo import road_km_real

    # Granollers: 41.6069, 2.2869
    result = road_km_real(41.3851, 2.1734, 41.6069, 2.2869)
    assert result is not None
    km, minutes = result
    # Granollers is ~30 km from Barcelona
    assert 20 <= km <= 50, f"Expected 20-50 km, got {km}"


def test_trip_analysis_granollers(cfg):
    """Verifica el análisis del viaje Barcelona → Granollers."""
    cfg.setdefault("inversor", {})["base"] = "Barcelona"

    from cazachollos.investor import trip_analysis

    # Granollers es en la provincia de Barcelona → province_key = "barcelona"
    trip = trip_analysis("barcelona", margin=2500, cfg=cfg)
    assert trip is not None
    assert trip.worth_trip  # margen 2500 € > margen_minimo 1500 €
    assert trip.distance_km <= 100  # Barcelona es corto
    assert trip.score_penalty == 0  # sin penalización


def test_trip_analysis_sevilla_far(cfg):
    """Verifica que un coche lejano (Sevilla) tiene penalización."""
    cfg.setdefault("inversor", {})["base"] = "Barcelona"

    from cazachollos.investor import trip_analysis

    trip = trip_analysis("sevilla", margin=2000, cfg=cfg)
    assert trip is not None
    # Sevilla es ~1000km de Barcelona
    assert trip.distance_km >= 900
    assert trip.score_penalty >= 10
    # Con solo 2000€ de margen y viaje tan caro, probablemente no vale
    # (depende de los costes configurados, pero el viaje tiene que ser caro)
    assert trip.total_trip_cost >= 300


def test_trip_analysis_germany(cfg):
    """Verifica el análisis de importación desde Alemania."""
    from cazachollos.investor import trip_analysis

    trip = trip_analysis("Munich", margin=4000, cfg=cfg, destination_country="DE")
    assert trip is not None
    assert trip.country == "DE"
    assert trip.score_penalty == 15
    # Coste de importación configurado por defecto en 1800 €
    assert trip.total_trip_cost >= 1000


def test_province_from_zip(cfg):
    """Verifica el mapeo de código postal a provincia."""
    from cazachollos.geo import province_from_zip

    assert province_from_zip("08403") == "barcelona"
    assert province_from_zip("28001") == "madrid"
    assert province_from_zip("41001") == "sevilla"
    assert province_from_zip("8400") == "barcelona"   # short zip
    assert province_from_zip(None) is None
    assert province_from_zip("99999") is None  # invalid
