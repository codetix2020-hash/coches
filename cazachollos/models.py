"""Modelo común de anuncio: todas las fuentes se convierten a esto."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Listing:
    source: str
    source_id: str
    url: str = ""
    title: str = ""
    description: str = ""
    make: str | None = None
    model: str | None = None
    version: str | None = None
    year: int | None = None
    km: int | None = None
    price: float | None = None
    fuel: str | None = (
        None  # diesel | gasolina | hibrido | hibrido_enchufable | electrico | glp | gnc
    )
    transmission: str | None = None  # manual | automatico
    power_cv: int | None = None
    province: str | None = None
    postal_code: str | None = None
    seller_type: str = "desconocido"  # particular | profesional | desconocido
    phone_hash: str | None = None  # nunca guardamos el teléfono en claro (RGPD)
    images: list[str] = field(default_factory=list)
    published_at: str | None = None
    dgt_label: str | None = None
    co2_g_km: int | None = None  # gramos CO2/km (para impuesto de matriculación)
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Flag:
    code: str
    severity: str  # grave | media | leve | positiva
    message: str


@dataclass
class Evaluation:
    market_price: float | None
    sale_price: float | None
    comparables_n: int
    confidence: float  # 0-1
    costs: dict
    total_costs: float
    margin: float | None
    roi: float | None
    score: int
    flags: list[Flag]
    reasons: list[str]
    hacienda_value: float | None = None
    spread: float | None = None  # dispersión relativa de comparables (IQR/mediana)
