"""25 anuncios ficticios realistas para probar el sistema sin datos reales.

Todos llevan source='demo' y raw['_demo']=True para poder borrarlos fácilmente.
Incluyen una variedad de casos: chollos, coches caros, alarmas de estafa, km sospechosos…
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from ..models import Listing, now_iso
from .base import Connector


def _ago(days: float, hours: float = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days, hours=hours)
    return dt.replace(microsecond=0).isoformat()


_LISTINGS: list[dict] = [
    # ── Chollos claros ─────────────────────────────────────────────────────────
    dict(source_id="D001", title="Volkswagen Golf 1.6 TDI Highline",
         description="Único propietario, libro de mantenimiento completo, revisiones en concesionario oficial. "
                     "Vendo por traslado de trabajo, necesito vender rápido. Precio negociable.",
         make="volkswagen", model="golf", year=2015, km=98000, price=8500,
         fuel="diesel", transmission="manual", power_cv=105,
         province="Madrid", seller_type="particular", images=["a.jpg","b.jpg","c.jpg","d.jpg","e.jpg"],
         published_at=_ago(0.5)),
    dict(source_id="D002", title="Seat León 2.0 TDI FR 150cv DSG",
         description="Distribución recién cambiada, embrague hecho hace 10.000 km. Dormido en garaje toda la vida.",
         make="seat", model="leon", year=2016, km=115000, price=9200,
         fuel="diesel", transmission="automatico", power_cv=150,
         province="Toledo", seller_type="particular", images=["a.jpg","b.jpg","c.jpg"],
         published_at=_ago(1)),
    dict(source_id="D003", title="Renault Mégane 1.5 dCi 110cv",
         description="Urge venta, por herencia. ITV pasada este año. Precio sin regateo.",
         make="renault", model="megane", year=2013, km=87000, price=5500,
         fuel="diesel", transmission="manual", power_cv=110,
         province="Madrid", seller_type="particular", images=["a.jpg","b.jpg","c.jpg","d.jpg"],
         published_at=_ago(0.1)),
    dict(source_id="D004", title="Toyota Yaris 1.0 VVT-i Active",
         description="Señora mayor, poco uso. Único propietario, garaje privado, todas las revisiones Toyota.",
         make="toyota", model="yaris", year=2017, km=42000, price=7800,
         fuel="gasolina", transmission="manual", power_cv=69,
         province="Madrid", seller_type="particular", images=["a.jpg","b.jpg","c.jpg","d.jpg","e.jpg"],
         published_at=_ago(2)),
    dict(source_id="D005", title="Peugeot 308 1.6 BlueHDi 120cv",
         description="FAP/DPF nuevo, correa de distribución cambiada hace 15.000 km. Precio negociable. Acepto ofertas.",
         make="peugeot", model="308", year=2014, km=143000, price=5900,
         fuel="diesel", transmission="manual", power_cv=120,
         province="Guadalajara", seller_type="particular", images=["a.jpg","b.jpg","c.jpg"],
         published_at=_ago(3)),
    # ── Precio justo / mercado ────────────────────────────────────────────────
    dict(source_id="D006", title="Ford Focus 1.0 EcoBoost 100cv",
         description="Bien conservado, revisión reciente. Segundo propietario.",
         make="ford", model="focus", year=2016, km=102000, price=7400,
         fuel="gasolina", transmission="manual", power_cv=100,
         province="Segovia", seller_type="particular", images=["a.jpg","b.jpg","c.jpg"],
         published_at=_ago(5)),
    dict(source_id="D007", title="Nissan Qashqai 1.5 dCi 110cv",
         description="Dos llaves, sensor aparcamiento, navegador. Sin golpes ni accidentes.",
         make="nissan", model="qashqai", year=2015, km=130000, price=9800,
         fuel="diesel", transmission="manual", power_cv=110,
         province="Madrid", seller_type="profesional", images=["a.jpg","b.jpg","c.jpg","d.jpg"],
         published_at=_ago(7)),
    dict(source_id="D008", title="Kia Sportage 1.7 CRDi 115cv",
         description="Garantía 1 año incluida. Revisado a fondo.",
         make="kia", model="sportage", year=2014, km=119000, price=10500,
         fuel="diesel", transmission="manual", power_cv=115,
         province="Madrid", seller_type="profesional", images=["a.jpg","b.jpg","c.jpg","d.jpg","e.jpg"],
         published_at=_ago(4)),
    dict(source_id="D009", title="Hyundai Tucson 1.6 T-GDI 177cv",
         description="Full equipo, techo panorámico. Dos propietarios.",
         make="hyundai", model="tucson", year=2018, km=74000, price=15000,
         fuel="gasolina", transmission="automatico", power_cv=177,
         province="Valladolid", seller_type="particular", images=["a.jpg","b.jpg","c.jpg"],
         published_at=_ago(6)),
    # ── Alarmas de posible estafa ──────────────────────────────────────────────
    dict(source_id="D010", title="BMW Serie 3 320d 190cv muy barato",
         description="Estoy fuera de España por trabajo militar. Te lo envío por agencia de transporte. "
                     "Solo por WhatsApp. Pago por adelantado mediante Bizum reserva.",
         make="bmw", model="serie-3", year=2018, km=95000, price=4500,
         fuel="diesel", transmission="automatico", power_cv=190,
         province="Barcelona", seller_type="desconocido", images=["a.jpg"],
         published_at=_ago(0.3)),
    dict(source_id="D011", title="Audi A4 2.0 TDI sin papeles",
         description="Sin papeles, para exportación únicamente. Motor perfecto.",
         make="audi", model="a4", year=2016, km=87000, price=3900,
         fuel="diesel", transmission="manual", power_cv=150,
         province="Murcia", seller_type="desconocido", images=["a.jpg","b.jpg"],
         published_at=_ago(1.5)),
    # ── Km sospechosamente bajos ──────────────────────────────────────────────
    dict(source_id="D012", title="Mercedes-Benz Clase C 220d",
         description="Coche de empresa, poca ciudad. Kilómetros verificables.",
         make="mercedes-benz", model="clase-c", year=2012, km=38000, price=11000,
         fuel="diesel", transmission="automatico", power_cv=170,
         province="Madrid", seller_type="particular", images=["a.jpg","b.jpg","c.jpg"],
         published_at=_ago(2)),
    # ── Problemas mecánicos conocidos ─────────────────────────────────────────
    dict(source_id="D013", title="Volkswagen Passat 2.0 TDI Avería motor",
         description="No arranca, biela rota. Para despiece o reparar. Sin ITV.",
         make="volkswagen", model="passat", year=2014, km=220000, price=1800,
         fuel="diesel", transmission="manual", power_cv=150,
         province="Madrid", seller_type="particular", images=["a.jpg","b.jpg"],
         published_at=_ago(10)),
    dict(source_id="D014", title="Opel Astra 1.6 CDTI a reparar",
         description="Golpe lateral, chapa dañada, necesita reparar. EGR averiado. Sin ITV.",
         make="opel", model="astra", year=2013, km=178000, price=2200,
         fuel="diesel", transmission="manual", power_cv=110,
         province="Toledo", seller_type="particular", images=["a.jpg","b.jpg","c.jpg"],
         published_at=_ago(8)),
    # ── Subidas y bajadas de precio (generamos historial) ────────────────────
    dict(source_id="D015", title="Skoda Octavia 1.6 TDI Ambition",
         description="Precio reducido por mudanza. Coche muy cuidado, segunda mano única propietaria.",
         make="skoda", model="octavia", year=2015, km=109000, price=7200,
         fuel="diesel", transmission="manual", power_cv=105,
         province="Madrid", seller_type="particular", images=["a.jpg","b.jpg","c.jpg","d.jpg"],
         published_at=_ago(14)),
    # ── Filtros fuera de rango (para comprobar que los filtros funcionan) ─────
    dict(source_id="D016", title="Ferrari 458 Italia",
         description="Coche de colección en perfecto estado.",
         make="ferrari", model="458-italia", year=2012, km=18000, price=180000,
         fuel="gasolina", transmission="automatico", power_cv=570,
         province="Madrid", seller_type="profesional", images=["a.jpg","b.jpg","c.jpg"],
         published_at=_ago(1)),
    dict(source_id="D017", title="Renault Twingo 1.2 muy antiguo",
         description="Primer coche, funciona bien.",
         make="renault", model="twingo", year=2001, km=195000, price=900,
         fuel="gasolina", transmission="manual", power_cv=60,
         province="Cuenca", seller_type="particular", images=["a.jpg"],
         published_at=_ago(20)),
    # ── Coches eléctricos e híbridos ─────────────────────────────────────────
    dict(source_id="D018", title="Renault Zoe 50 kWh R135",
         description="Batería propia (no alquiler). Cargador rápido CCS. 1 propietaria.",
         make="renault", model="zoe", year=2020, km=55000, price=12500,
         fuel="electrico", transmission="automatico", power_cv=135,
         province="Madrid", seller_type="particular", images=["a.jpg","b.jpg","c.jpg","d.jpg"],
         published_at=_ago(3)),
    dict(source_id="D019", title="Toyota Prius 1.8 Hybrid Executive",
         description="Dos propietarios, siempre revisado en Toyota. Batería revisada.",
         make="toyota", model="prius", year=2016, km=118000, price=8800,
         fuel="hibrido", transmission="automatico", power_cv=122,
         province="Madrid", seller_type="particular", images=["a.jpg","b.jpg","c.jpg"],
         published_at=_ago(6)),
    # ── Duplicado simulado (mismo coche en otra fuente) ───────────────────────
    dict(source_id="D020", title="VW Golf 1.6 TDI Highline 2015",
         description="Único propietario, revisado, traslado de trabajo urgente.",
         make="volkswagen", model="golf", year=2015, km=98500, price=8600,
         fuel="diesel", transmission="manual", power_cv=105,
         province="Madrid", seller_type="particular", images=["a.jpg","b.jpg","c.jpg","d.jpg","e.jpg"],
         published_at=_ago(0.5)),
    # ── Furgonetas / comerciales ─────────────────────────────────────────────
    dict(source_id="D021", title="Ford Transit Custom 2.0 TDCi 130cv",
         description="Furgoneta empresa, mantenimiento al día. 2 plazas.",
         make="ford", model="transit-custom", year=2018, km=132000, price=14500,
         fuel="diesel", transmission="manual", power_cv=130,
         province="Madrid", seller_type="profesional", images=["a.jpg","b.jpg","c.jpg"],
         published_at=_ago(4)),
    # ── Más comparables para valoración ─────────────────────────────────────
    dict(source_id="D022", title="Volkswagen Golf 1.6 TDI Trendline 2015",
         description="Dos propietarios, bien conservado.",
         make="volkswagen", model="golf", year=2015, km=105000, price=8100,
         fuel="diesel", transmission="manual", power_cv=105,
         province="Alcalá de Henares", seller_type="particular", images=["a.jpg","b.jpg","c.jpg"],
         published_at=_ago(30)),
    dict(source_id="D023", title="Volkswagen Golf 1.6 TDI Style 2015",
         description="Concesionario oficial, revisado, garantía 6 meses.",
         make="volkswagen", model="golf", year=2015, km=89000, price=9400,
         fuel="diesel", transmission="manual", power_cv=105,
         province="Madrid", seller_type="profesional", images=["a.jpg","b.jpg","c.jpg","d.jpg"],
         published_at=_ago(45)),
    dict(source_id="D024", title="VW Golf VII 1.6 TDI 2016",
         description="Buen estado general. Precio ajustado.",
         make="volkswagen", model="golf", year=2016, km=112000, price=9000,
         fuel="diesel", transmission="manual", power_cv=115,
         province="Getafe", seller_type="particular", images=["a.jpg","b.jpg"],
         published_at=_ago(60)),
    dict(source_id="D025", title="Seat León 2.0 TDI 2016 FR DSG 150cv ocasión",
         description="Bien mantenido. Distribución en buen estado.",
         make="seat", model="leon", year=2016, km=108000, price=9800,
         fuel="diesel", transmission="automatico", power_cv=150,
         province="Madrid", seller_type="particular", images=["a.jpg","b.jpg","c.jpg"],
         published_at=_ago(21)),
]


class DemoConnector(Connector):
    name = "demo"

    def enabled(self) -> bool:
        return bool(self.cfg.get_path("fuentes.demo.activo", False))

    def fetch(self) -> Iterable[Listing]:
        for d in _LISTINGS:
            yield Listing(
                source="demo",
                source_id=d["source_id"],
                url=d.get("url", f"https://demo.local/{d['source_id']}"),
                title=d.get("title", ""),
                description=d.get("description", ""),
                make=d.get("make"),
                model=d.get("model"),
                year=d.get("year"),
                km=d.get("km"),
                price=d.get("price"),
                fuel=d.get("fuel"),
                transmission=d.get("transmission"),
                power_cv=d.get("power_cv"),
                province=d.get("province"),
                seller_type=d.get("seller_type", "desconocido"),
                images=d.get("images", []),
                published_at=d.get("published_at"),
                raw={"_demo": True, **d},
            )
