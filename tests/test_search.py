"""Tests del módulo search.py (búsqueda en lenguaje natural)."""

from cazachollos.search import parse_query, describe_filters


def test_parse_make_and_model():
    f = parse_query("Seat León 2017")
    assert "seat" in f.get("busqueda.marcas_incluir", [])


def test_parse_price_range():
    f = parse_query("máximo 12000 euros mínimo 3000")
    assert f["busqueda.precio_max"] == 12000
    assert f["busqueda.precio_min"] == 3000


def test_parse_km():
    f = parse_query("menos de 150000 km")
    assert f["busqueda.km_max"] == 150000


def test_parse_electric():
    f = parse_query("coche eléctrico hasta 20000")
    assert f.get("busqueda.combustibles") == ["electrico"]
    assert f["busqueda.precio_max"] == 20000


def test_parse_radio():
    f = parse_query("Renault a 50 km")
    assert f.get("busqueda.radio_km") == 50
    assert "renault" in f.get("busqueda.marcas_incluir", [])


def test_empty_query():
    f = parse_query("")
    assert f == {}


def test_describe_all_fields():
    f = {
        "busqueda.marcas_incluir": ["seat", "volkswagen"],
        "busqueda.combustibles": ["diesel"],
        "busqueda.cambios": ["manual"],
        "busqueda.precio_min": 3000,
        "busqueda.precio_max": 9000,
        "busqueda.km_max": 150000,
        "busqueda.anio_min": 2015,
        "busqueda.radio_km": 200,
    }
    desc = describe_filters(f)
    for keyword in ["seat", "volkswagen", "diesel", "manual", "9.000", "150.000", "2015", "200"]:
        assert keyword in desc, f"'{keyword}' no está en '{desc}'"
