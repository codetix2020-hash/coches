"""Tests de costs.py: ITP, reparaciones, costes completos."""

from cazachollos.costs import compute_costs, itp_cost, repair_estimate
from cazachollos.models import Listing


def _listing(**kw) -> Listing:
    defaults = dict(source="test", source_id="x", make="volkswagen", model="golf",
                    year=2015, km=100000, price=8000.0, fuel="diesel",
                    transmission="manual", province="Madrid")
    defaults.update(kw)
    return Listing(**defaults)


def test_itp_particular(cfg):
    lst = _listing()
    itp, nota, hv = itp_cost(lst, 8000, cfg)
    assert itp > 0
    assert "%" in nota


def test_itp_rebu_exento(cfg):
    cfg["yo"]["regimen"] = "rebu"
    cfg["itp"]["exento_si_profesional"] = True
    lst = _listing()
    itp, nota, _ = itp_cost(lst, 8000, cfg)
    assert itp == 0.0
    assert "exento" in nota.lower()


def test_repair_old_car(cfg):
    lst = _listing(year=2010, km=180000)
    total, notes = repair_estimate(lst, cfg)
    assert total >= 450 + 250  # base 10-14 años + extra >150k km
    assert any("150.000" in n for n in notes)


def test_repair_keyword_averia(cfg):
    lst = _listing(title="Golf averiado no arranca", description="avería grave")
    total_with, _ = repair_estimate(lst, cfg)
    lst2 = _listing()
    total_without, _ = repair_estimate(lst2, cfg)
    assert total_with > total_without


def test_repair_keyword_already_done(cfg):
    """Si el anuncio dice 'distribución recién cambiada', no se suma ese coste."""
    lst = _listing(description="distribución recién cambiada hace 5000 km")
    total_with, notes = repair_estimate(lst, cfg)
    lst2 = _listing(description="distribución deteriorada")
    total_without, _ = repair_estimate(lst2, cfg)
    assert total_with <= total_without


def test_compute_costs_returns_dict(cfg):
    lst = _listing()
    costs, total, hv = compute_costs(lst, 10000.0, cfg)
    assert isinstance(costs, dict)
    assert total > 0
    assert "itp" in costs
    assert "transferencia" in costs
    assert "reparaciones" in costs
    assert abs(sum(v["eur"] for v in costs.values()) - total) < 0.1


def test_compute_costs_desplazamiento_lejos(cfg):
    lst = _listing(province="Sevilla")
    costs, total, _ = compute_costs(lst, 10000.0, cfg)
    # Sevilla a Madrid > 500 km → desplazamiento debe ser significativo
    assert costs["desplazamiento"]["eur"] > 100


def test_rebu_iva_applied(cfg):
    cfg["yo"]["regimen"] = "rebu"
    cfg["itp"]["exento_si_profesional"] = True
    lst = _listing(price=5000.0)
    costs, total, _ = compute_costs(lst, 8000.0, cfg)
    assert "iva_rebu" in costs
    assert costs["iva_rebu"]["eur"] > 0
