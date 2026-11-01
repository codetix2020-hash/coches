"""Tests de scoring.py y redflags.py."""

from cazachollos.models import Flag, Listing
from cazachollos.redflags import detect_flags, verify_km_vs_itv
from cazachollos.scoring import cargurus_label, passes_filters, score


def _ev(market=10000, sale=9400, margin=1500, roi=0.2, confidence=0.8,
        comparables=8, flags=None):
    class FakeEv:
        market_price = market
        sale_price = sale
        comparables_n = comparables
        score = 75
    ev = FakeEv()
    return ev


def _listing(**kw) -> Listing:
    defaults = dict(source="test", source_id="1", make="volkswagen", model="golf",
                    year=2016, km=90000, price=7500.0, fuel="diesel",
                    transmission="manual", province="Madrid", seller_type="particular",
                    images=["a.jpg","b.jpg","c.jpg"])
    defaults.update(kw)
    return Listing(**defaults)


def test_passes_filters_ok(cfg):
    lst = _listing()
    ok, reason = passes_filters(lst, cfg)
    assert ok
    assert reason == ""


def test_passes_filters_too_expensive(cfg):
    lst = _listing(price=99000.0)
    ok, reason = passes_filters(lst, cfg)
    assert not ok
    assert "presupuesto" in reason


def test_passes_filters_too_old(cfg):
    lst = _listing(year=2000)
    ok, reason = passes_filters(lst, cfg)
    assert not ok


def test_passes_filters_too_many_km(cfg):
    lst = _listing(km=300000)
    ok, reason = passes_filters(lst, cfg)
    assert not ok


def test_score_with_good_margin(cfg):
    lst = _listing()
    flags = []
    sc, reasons = score(lst, 10000, 1800, 0.25, 0.9, 10, flags, cfg)
    assert sc >= 70
    assert any("margen" in r for r in reasons)


def test_score_capped_on_grave_flag(cfg):
    lst = _listing()
    flags = [Flag("estafa", "grave", "posible estafa")]
    sc, reasons = score(lst, 10000, 2000, 0.30, 0.9, 10, flags, cfg)
    assert sc <= 30


def test_cargurus_label_chollo():
    ev = _ev()
    ev.score = 85
    assert cargurus_label(ev) == "Chollo"


def test_cargurus_label_sin_valoracion():
    ev = _ev(market=None)
    ev.market_price = None
    ev.comparables_n = 0
    assert cargurus_label(ev) == "Sin valoración"


def test_detect_flags_scam_text(cfg):
    lst = _listing(
        description="Estoy fuera de España por trabajo militar. Solo por WhatsApp. Pago por adelantado.",
        images=["a.jpg"],
    )
    flags = detect_flags(None, lst, None, 10000, cfg)
    codes = [f.code for f in flags]
    assert "estafa_texto" in codes
    graves = [f for f in flags if f.severity == "grave"]
    assert graves


def test_detect_flags_km_bajos(cfg):
    # Coche de 2010 con solo 20000 km → sospechoso
    lst = _listing(year=2010, km=20000, description="poco uso")
    flags = detect_flags(None, lst, None, 10000, cfg)
    assert any(f.code == "km_bajos" for f in flags)


def test_detect_flags_positive(cfg):
    lst = _listing(description="urge vender por traslado, precio negociable")
    flags = detect_flags(None, lst, None, 10000, cfg)
    assert any(f.severity == "positiva" for f in flags)


def test_verify_km_vs_itv_manipulated():
    lst = _listing(km=50000)
    flag = verify_km_vs_itv(lst, itv_km=80000, itv_year=2023)
    assert flag is not None
    assert flag.severity == "grave"
    assert "manipulación" in flag.message


def test_verify_km_vs_itv_ok():
    lst = _listing(km=100000)
    flag = verify_km_vs_itv(lst, itv_km=95000, itv_year=2023)
    assert flag is None
