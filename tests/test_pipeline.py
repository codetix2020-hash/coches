"""Tests end-to-end: demo → pipeline → evaluación → BD."""

import json

import pytest
from cazachollos import db, pipeline
from cazachollos.models import Listing
from cazachollos.sources.demo import DemoConnector
from cazachollos.pipeline import max_offer
from cazachollos.search import describe_filters, parse_query
from cazachollos.templates import seller_message, inspection_checklist


def _listing(**kw) -> Listing:
    defaults = dict(source="test", source_id="T1", title="Golf TDI test",
                    make="volkswagen", model="golf", year=2015, km=100000,
                    price=7000.0, fuel="diesel", transmission="manual",
                    province="Madrid", seller_type="particular",
                    images=["a.jpg","b.jpg","c.jpg"])
    defaults.update(kw)
    return Listing(**defaults)


# ── Pipeline básico ─────────────────────────────────────────────────────────

def test_process_single_listing(conn, cfg):
    lst = _listing()
    results = pipeline.process(conn, [lst], cfg)
    assert len(results) == 1
    r = results[0]
    assert r.is_new
    assert r.evaluation.total_costs > 0
    assert r.evaluation.score >= 0


def test_process_upsert_existing(conn, cfg):
    lst = _listing()
    pipeline.process(conn, [lst], cfg)
    lst2 = _listing(price=6800.0)  # precio bajado
    results = pipeline.process(conn, [lst2], cfg)
    assert not results[0].is_new
    hist = conn.execute("SELECT * FROM price_history WHERE listing_id=1").fetchall()
    assert len(hist) == 2


def test_process_demo_data(conn, cfg):
    cfg.setdefault("fuentes", {}).setdefault("demo", {})["activo"] = True
    connector = DemoConnector(cfg)
    listings = list(connector.fetch())
    assert len(listings) == 25

    alerts_sent = []
    def fake_notifier(channel, res):
        alerts_sent.append(res)
        return True

    results = pipeline.process(conn, listings, cfg, notifier=fake_notifier)
    assert len(results) == 25

    # Todos los resultados tienen evaluación
    for r in results:
        assert r.evaluation is not None
        assert 0 <= r.evaluation.score <= 100

    # Debe haber al menos 1 coche en filtros (Madrid, precio razonable)
    in_filters = [r for r in results if r.in_filters]
    assert len(in_filters) > 0

    # Los anuncios de estafa (D010) deben tener score bajo o alarma grave
    scam = next((r for r in results if r.listing.source_id == "D010"), None)
    assert scam is not None
    assert any(f.severity == "grave" for f in scam.evaluation.flags)


def test_evaluation_saved_in_db(conn, cfg):
    lst = _listing()
    pipeline.process(conn, [lst], cfg)
    ev_row = conn.execute("SELECT * FROM evaluations WHERE listing_id=1").fetchone()
    assert ev_row is not None
    assert ev_row["total_costs"] > 0


def test_no_duplicate_alerts(conn, cfg):
    lst = _listing()
    sent = []
    def notifier(ch, res):
        sent.append(ch)
        return True

    # Primera vez: si el score es alto y no hay alarmas graves, debe enviar
    results = pipeline.process(conn, [lst], cfg, notifier=notifier)
    first_count = len(sent)

    # Segunda vez con el mismo anuncio: NO debe volver a alertar
    sent.clear()
    pipeline.process(conn, [lst], cfg, notifier=notifier)
    assert len(sent) == 0  # ya está marcado como enviado


# ── max_offer ───────────────────────────────────────────────────────────────

def test_max_offer_positive(cfg):
    class FakeEv:
        sale_price = 10000
        total_costs = 1500
    result = max_offer(FakeEv(), cfg)
    # 10000 - 1500 - 1000 (margen mínimo) = 7500
    assert result == 7500


def test_max_offer_too_tight(cfg):
    class FakeEv:
        sale_price = 5000
        total_costs = 4500
    result = max_offer(FakeEv(), cfg)
    assert result == 0 or result is None


def test_max_offer_none_when_no_sale(cfg):
    class FakeEv:
        sale_price = None
        total_costs = 1500
    assert max_offer(FakeEv(), cfg) is None


# ── search.py ───────────────────────────────────────────────────────────────

def test_parse_query_full():
    f = parse_query("Volkswagen Golf diésel manual menos de 8000 euros a 100 km desde 2015")
    assert "volkswagen" in f.get("busqueda.marcas_incluir", [])
    assert f.get("busqueda.combustibles") == ["diesel"]
    assert f.get("busqueda.cambios") == ["manual"]
    assert f.get("busqueda.precio_max") == 8000
    assert f.get("busqueda.radio_km") == 100
    assert f.get("busqueda.anio_min") == 2015


def test_parse_query_suv():
    f = parse_query("Nissan Qashqai SUV automático gasolina hasta 15000")
    assert "nissan" in f.get("busqueda.marcas_incluir", [])
    assert f.get("busqueda.precio_max") == 15000


def test_describe_filters_non_empty():
    f = {"busqueda.marcas_incluir": ["seat"], "busqueda.precio_max": 9000}
    desc = describe_filters(f)
    assert "seat" in desc.lower()
    assert "9.000" in desc or "9000" in desc


# ── templates.py ────────────────────────────────────────────────────────────

def test_seller_message_contains_questions():
    lst = _listing()
    msg = seller_message(lst, max_offer=7000)
    assert "ITV" in msg
    assert "7.000 €" in msg or "7000 €" in msg.replace(".", "").replace(",", "")


def test_inspection_checklist_diesel():
    lst = _listing(fuel="diesel", km=160000)
    items = inspection_checklist(lst)
    assert any("FAP" in i or "DPF" in i for i in items)
    assert any("embrague" in i.lower() or "distribución" in i.lower() or "alta km" in i.lower() for i in items)


def test_inspection_checklist_electric():
    lst = _listing(fuel="electrico")
    items = inspection_checklist(lst)
    assert any("batería" in i.lower() for i in items)
