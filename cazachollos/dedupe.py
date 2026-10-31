"""Detecta el mismo coche publicado en varias webs (o republicado)."""

from __future__ import annotations

import difflib
import io
import json
import sqlite3

from .config import Config
from .normalize import norm_text


def dhash_bytes(data: bytes, size: int = 8) -> str | None:
    """Huella perceptual de una foto (dHash) para detectar fotos repetidas o robadas."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("L").resize((size + 1, size))
    except Exception:
        return None
    px = list(img.getdata())
    bits = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:0{size * size // 4}x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def text_similarity(a: str | None, b: str | None) -> float:
    ta, tb = norm_text(a)[:600], norm_text(b)[:600]
    if len(ta) < 40 or len(tb) < 40:
        return 0.0
    return difflib.SequenceMatcher(None, ta, tb).ratio()


def same_car(a: sqlite3.Row, b: sqlite3.Row, cfg: Config) -> tuple[bool, str]:
    d = cfg.get("duplicados", {})
    if a["phone_hash"] and a["phone_hash"] == b["phone_hash"] and a["model"] == b["model"]:
        return True, "mismo teléfono y modelo"
    ha, hb = json.loads(a["image_hashes"] or "[]"), json.loads(b["image_hashes"] or "[]")
    for x in ha:
        for y in hb:
            if hamming(x, y) <= d.get("distancia_hash_foto", 6):
                return True, "misma foto"
    if a["make"] != b["make"] or a["model"] != b["model"]:
        return False, ""
    if a["year"] and b["year"] and a["year"] != b["year"]:
        return False, ""
    if a["km"] is None or b["km"] is None:
        return False, ""
    km_close = abs(a["km"] - b["km"]) <= d.get("km_tolerancia", 2500)
    if not km_close:
        return False, ""
    if text_similarity(a["description"], b["description"]) >= d.get("similitud_texto", 0.85):
        return True, "mismo texto, km y modelo"
    if a["price"] and b["price"]:
        diff = abs(a["price"] - b["price"]) / max(a["price"], b["price"])
        same_place = (a["province"] or "") == (b["province"] or "") and a["province"]
        if diff <= d.get("precio_tolerancia_pct", 0.15) and same_place and a["source"] != b["source"]:
            return True, "mismo modelo, año, km y provincia en otra web"
    return False, ""


def assign_group(conn: sqlite3.Connection, listing_id: int, cfg: Config) -> tuple[int, list[str]]:
    """Asigna group_id al anuncio. Devuelve (group_id, motivos de coincidencia)."""
    me = conn.execute("SELECT * FROM listings WHERE id=?", (listing_id,)).fetchone()
    if me["group_id"]:
        return me["group_id"], []
    candidates = conn.execute(
        """SELECT * FROM listings WHERE id != ? AND active = 1 AND (
               (make = ? AND model = ?) OR (phone_hash IS NOT NULL AND phone_hash = ?)
               OR image_hashes != '[]')""",
        (listing_id, me["make"], me["model"], me["phone_hash"]),
    ).fetchall()
    reasons = []
    group = listing_id
    for other in candidates:
        ok, why = same_car(me, other, cfg)
        if ok:
            group = other["group_id"] or other["id"]
            reasons.append(f"{why} ({other['source']})")
            break
    conn.execute("UPDATE listings SET group_id=? WHERE id=?", (group, listing_id))
    conn.commit()
    return group, reasons


def reused_photos(conn: sqlite3.Connection, listing_id: int, cfg: Config) -> list[int]:
    """Anuncios de OTRO grupo que usan una foto casi idéntica (posible foto robada)."""
    me = conn.execute("SELECT id, group_id, image_hashes FROM listings WHERE id=?", (listing_id,)).fetchone()
    mine = json.loads(me["image_hashes"] or "[]")
    if not mine:
        return []
    hits = []
    for row in conn.execute(
        "SELECT id, group_id, image_hashes FROM listings WHERE id != ? AND image_hashes != '[]'", (listing_id,)
    ):
        if row["group_id"] == me["group_id"]:
            continue
        for x in mine:
            if any(hamming(x, y) <= cfg.get_path("duplicados.distancia_hash_foto", 6)
                   for y in json.loads(row["image_hashes"])):
                hits.append(row["id"])
                break
    return hits
