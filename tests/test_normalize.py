"""Tests del módulo normalize.py."""

from cazachollos.normalize import (
    normalize_make, normalize_fuel, normalize_transmission,
    parse_price, parse_km, parse_year, hash_phone, slug,
    estimate_dgt_label, normalize_listing,
)
from cazachollos.models import Listing


def test_normalize_make_basic():
    assert normalize_make("Volkswagen") == "volkswagen"
    assert normalize_make("VW") == "volkswagen"
    assert normalize_make("Mercedes-Benz") == "mercedes-benz"
    assert normalize_make("Mercedes") == "mercedes-benz"
    assert normalize_make("Alfa Romeo") == "alfa-romeo"


def test_normalize_make_from_title():
    assert normalize_make(None, "Golf TDI de Volkswagen") == "volkswagen"


def test_normalize_fuel():
    assert normalize_fuel("TDI") == "diesel"
    assert normalize_fuel("gasolina TSI") == "gasolina"
    assert normalize_fuel("PHEV") == "hibrido_enchufable"
    assert normalize_fuel("eléctrico") == "electrico"
    assert normalize_fuel("GLP") == "glp"


def test_normalize_transmission():
    assert normalize_transmission("caja automática DSG") == "automatico"
    assert normalize_transmission("manual 6 velocidades") == "manual"
    assert normalize_transmission("texto sin cambio") is None


def test_parse_price():
    assert parse_price("8.500 €") == 8500.0
    assert parse_price("12.900 €") == 12900.0  # punto como separador de miles (España)
    assert parse_price(9000) == 9000.0
    assert parse_price(None) is None


def test_parse_km():
    assert parse_km("98.000 km") == 98000
    assert parse_km("150000 kms") == 150000
    assert parse_km(None) is None


def test_parse_year():
    assert parse_year("Matriculado en 2015") == 2015
    assert parse_year("2019") == 2019
    assert parse_year("abc") is None


def test_hash_phone_consistency():
    h1 = hash_phone("666 123 456")
    h2 = hash_phone("666123456")
    h3 = hash_phone("+34 666 123 456")
    assert h1 == h2 == h3
    assert len(h1) == 16


def test_hash_phone_none():
    assert hash_phone(None) is None
    assert hash_phone("123") is None  # muy corto


def test_dgt_label():
    assert estimate_dgt_label("electrico", 2020) == "CERO"
    assert estimate_dgt_label("diesel", 2018) == "C"
    assert estimate_dgt_label("diesel", 2007) == "B"
    assert estimate_dgt_label("diesel", 2005) == "SIN"
    assert estimate_dgt_label("gasolina", 2010) == "C"


def test_normalize_listing_full():
    lst = Listing(
        source="test", source_id="1",
        title="Volkswagen Golf 1.6 TDI 105cv 2015",
        description="Coche diésel manual con 98.000 km. Precio: 8.500 €. Tel: 666 123 456",
        make="Volkswagen", model="Golf",
        year=None, km=None, price=None,
    )
    normalize_listing(lst)
    assert lst.make == "volkswagen"
    assert lst.model == "golf"
    assert lst.fuel == "diesel"
    assert lst.transmission == "manual"
    assert lst.year == 2015
    assert lst.km == 98000
    assert lst.phone_hash is not None
    assert lst.dgt_label == "B"  # diesel 2015 → etiqueta B (C requiere ≥ 2016)
