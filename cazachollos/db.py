"""Base de datos SQLite: anuncios, histórico de precios, valoraciones y seguimiento."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import db_path
from .models import Evaluation, Listing, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    url TEXT, title TEXT, description TEXT,
    make TEXT, model TEXT, version TEXT,
    year INTEGER, km INTEGER, price REAL,
    fuel TEXT, transmission TEXT, power_cv INTEGER,
    province TEXT, postal_code TEXT, seller_type TEXT,
    phone_hash TEXT, images TEXT, image_hashes TEXT,
    published_at TEXT, dgt_label TEXT,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    group_id INTEGER,
    raw TEXT,
    UNIQUE(source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_listings_model ON listings(make, model, year);
CREATE INDEX IF NOT EXISTS idx_listings_group ON listings(group_id);

CREATE TABLE IF NOT EXISTS price_history (
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    price REAL NOT NULL,
    seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_history ON price_history(listing_id);

CREATE TABLE IF NOT EXISTS evaluations (
    listing_id INTEGER PRIMARY KEY REFERENCES listings(id),
    market_price REAL, sale_price REAL, comparables_n INTEGER, confidence REAL,
    hacienda_value REAL, costs TEXT, total_costs REAL, margin REAL, roi REAL,
    score INTEGER, flags TEXT, reasons TEXT, vision TEXT,
    evaluated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline (
    listing_id INTEGER PRIMARY KEY REFERENCES listings(id),
    stage TEXT NOT NULL DEFAULT 'visto',
    favorite INTEGER NOT NULL DEFAULT 0,
    notes TEXT DEFAULT '',
    buy_price REAL, sell_price REAL, extra_costs REAL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts_sent (
    listing_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    PRIMARY KEY (listing_id, channel)
);

CREATE TABLE IF NOT EXISTS connector_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    items INTEGER DEFAULT 0,
    ok INTEGER DEFAULT 1,
    error TEXT
);
"""

STAGES = ["visto", "contactado", "visitado", "comprado", "vendido", "descartado"]


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path) if path else db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def upsert_listing(conn: sqlite3.Connection, lst: Listing) -> tuple[int, bool, float | None]:
    """Guarda o actualiza un anuncio. Devuelve (id, es_nuevo, precio_anterior)."""
    ts = now_iso()
    row = conn.execute(
        "SELECT id, price FROM listings WHERE source=? AND source_id=?", (lst.source, lst.source_id)
    ).fetchone()
    fields = {
        "url": lst.url, "title": lst.title, "description": lst.description,
        "make": lst.make, "model": lst.model, "version": lst.version,
        "year": lst.year, "km": lst.km, "price": lst.price,
        "fuel": lst.fuel, "transmission": lst.transmission, "power_cv": lst.power_cv,
        "province": lst.province, "postal_code": lst.postal_code, "seller_type": lst.seller_type,
        "phone_hash": lst.phone_hash, "images": json.dumps(lst.images),
        "published_at": lst.published_at, "dgt_label": lst.dgt_label,
        "raw": json.dumps(lst.raw, ensure_ascii=False, default=str),
    }
    if row is None:
        cols = ", ".join(["source", "source_id", *fields, "first_seen", "last_seen"])
        marks = ", ".join("?" * (len(fields) + 4))
        cur = conn.execute(
            f"INSERT INTO listings ({cols}) VALUES ({marks})",
            (lst.source, lst.source_id, *fields.values(), ts, ts),
        )
        listing_id = cur.lastrowid
        if lst.price:
            conn.execute(
                "INSERT INTO price_history VALUES (?,?,?)", (listing_id, lst.price, ts)
            )
        conn.commit()
        return listing_id, True, None

    listing_id, old_price = row["id"], row["price"]
    # No pisamos datos buenos con vacíos que vengan de una fuente más pobre.
    updates = {k: v for k, v in fields.items() if v not in (None, "", "[]", "{}")}
    updates["last_seen"] = ts
    updates["active"] = 1
    sets = ", ".join(f"{k}=?" for k in updates)
    conn.execute(f"UPDATE listings SET {sets} WHERE id=?", (*updates.values(), listing_id))
    if lst.price and old_price and abs(lst.price - old_price) >= 1:
        conn.execute("INSERT INTO price_history VALUES (?,?,?)", (listing_id, lst.price, ts))
    conn.commit()
    return listing_id, False, old_price


def row_to_listing(row: sqlite3.Row) -> Listing:
    return Listing(
        source=row["source"], source_id=row["source_id"], url=row["url"] or "",
        title=row["title"] or "", description=row["description"] or "",
        make=row["make"], model=row["model"], version=row["version"],
        year=row["year"], km=row["km"], price=row["price"], fuel=row["fuel"],
        transmission=row["transmission"], power_cv=row["power_cv"],
        province=row["province"], postal_code=row["postal_code"],
        seller_type=row["seller_type"] or "desconocido", phone_hash=row["phone_hash"],
        images=json.loads(row["images"] or "[]"), published_at=row["published_at"],
        dgt_label=row["dgt_label"], raw=json.loads(row["raw"] or "{}"),
    )


def save_evaluation(conn: sqlite3.Connection, listing_id: int, ev: Evaluation) -> None:
    conn.execute(
        """INSERT INTO evaluations (listing_id, market_price, sale_price, comparables_n, confidence,
               hacienda_value, costs, total_costs, margin, roi, score, flags, reasons, evaluated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(listing_id) DO UPDATE SET
               market_price=excluded.market_price, sale_price=excluded.sale_price,
               comparables_n=excluded.comparables_n, confidence=excluded.confidence,
               hacienda_value=excluded.hacienda_value, costs=excluded.costs,
               total_costs=excluded.total_costs, margin=excluded.margin, roi=excluded.roi,
               score=excluded.score, flags=excluded.flags, reasons=excluded.reasons,
               evaluated_at=excluded.evaluated_at""",
        (
            listing_id, ev.market_price, ev.sale_price, ev.comparables_n, ev.confidence,
            ev.hacienda_value, json.dumps(ev.costs), ev.total_costs, ev.margin, ev.roi, ev.score,
            json.dumps([f.__dict__ for f in ev.flags], ensure_ascii=False),
            json.dumps(ev.reasons, ensure_ascii=False), now_iso(),
        ),
    )
    conn.execute(
        "INSERT OR IGNORE INTO pipeline (listing_id, stage, updated_at) VALUES (?, 'visto', ?)",
        (listing_id, now_iso()),
    )
    conn.commit()


def save_vision(conn: sqlite3.Connection, listing_id: int, result: dict) -> None:
    conn.execute(
        "UPDATE evaluations SET vision=? WHERE listing_id=?",
        (json.dumps(result, ensure_ascii=False), listing_id),
    )
    conn.commit()


def update_pipeline(conn: sqlite3.Connection, listing_id: int, **kw) -> None:
    allowed = {"stage", "favorite", "notes", "buy_price", "sell_price", "extra_costs"}
    data = {k: v for k, v in kw.items() if k in allowed}
    if "stage" in data and data["stage"] not in STAGES:
        raise ValueError(f"Etapa no válida: {data['stage']}")
    conn.execute(
        "INSERT OR IGNORE INTO pipeline (listing_id, stage, updated_at) VALUES (?, 'visto', ?)",
        (listing_id, now_iso()),
    )
    if data:
        sets = ", ".join(f"{k}=?" for k in data)
        conn.execute(
            f"UPDATE pipeline SET {sets}, updated_at=? WHERE listing_id=?",
            (*data.values(), now_iso(), listing_id),
        )
    conn.commit()


def alert_already_sent(conn: sqlite3.Connection, listing_id: int, channel: str) -> bool:
    group = conn.execute("SELECT group_id FROM listings WHERE id=?", (listing_id,)).fetchone()
    ids = [listing_id]
    if group and group["group_id"]:
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM listings WHERE group_id=?", (group["group_id"],))]
    marks = ",".join("?" * len(ids))
    return conn.execute(
        f"SELECT 1 FROM alerts_sent WHERE channel=? AND listing_id IN ({marks})", (channel, *ids)
    ).fetchone() is not None


def mark_alert_sent(conn: sqlite3.Connection, listing_id: int, channel: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO alerts_sent VALUES (?,?,?)", (listing_id, channel, now_iso())
    )
    conn.commit()
