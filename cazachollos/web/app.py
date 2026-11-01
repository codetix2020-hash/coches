"""Aplicación Starlette: panel web local en 127.0.0.1:8765."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from ..config import Config
from .. import db
from ..db import STAGES, update_pipeline
from ..pipeline import evaluate, max_offer
from ..scoring import cargurus_label
from ..templates import inspection_checklist, seller_message

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def _env() -> Environment:
    e = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )

    def fmt_eur(value):
        if value is None:
            return "—"
        return f"{float(value):,.0f} €".replace(",", ".")

    def fmt_km(value):
        if value is None:
            return "—"
        return f"{int(value):,} km".replace(",", ".")

    e.filters["eur"] = fmt_eur
    e.filters["km"] = fmt_km
    return e


def create_app(cfg: Config) -> Starlette:
    env = _env()

    def _conn():
        return db.connect()

    # ── Rutas ─────────────────────────────────────────────────────────────────

    async def index(request: Request) -> HTMLResponse:
        conn = _conn()

        # Filtros de URL
        q_score = int(request.query_params.get("score_min", 0))
        q_stage = request.query_params.get("stage", "")
        q_label = request.query_params.get("label", "")
        q_fav = request.query_params.get("favoritos", "")
        q_search = request.query_params.get("q", "").strip()
        q_sort = request.query_params.get("sort", "score")

        sql = """
            SELECT l.*, e.score, e.market_price, e.sale_price, e.margin, e.roi,
                   e.flags, e.reasons, e.total_costs, e.comparables_n, e.confidence,
                   p.stage, p.favorite, p.notes, p.buy_price, p.sell_price
            FROM listings l
            LEFT JOIN evaluations e ON e.listing_id = l.id
            LEFT JOIN pipeline p ON p.listing_id = l.id
            WHERE l.active = 1
        """
        params: list = []
        if q_score:
            sql += " AND e.score >= ?"
            params.append(q_score)
        if q_stage:
            sql += " AND p.stage = ?"
            params.append(q_stage)
        if q_fav:
            sql += " AND p.favorite = 1"
        if q_search:
            sql += " AND (l.title LIKE ? OR l.make LIKE ? OR l.model LIKE ?)"
            like = f"%{q_search}%"
            params += [like, like, like]

        order = "e.score DESC" if q_sort == "score" else "l.first_seen DESC"
        sql += f" ORDER BY {order} LIMIT 200"

        rows = conn.execute(sql, params).fetchall()
        conn.close()

        listings = []
        for r in rows:
            flags = json.loads(r["flags"] or "[]")
            label = _ev_label(r)
            if q_label and label.lower() != q_label.lower():
                continue
            listings.append({
                "id": r["id"], "title": r["title"], "make": r["make"], "model": r["model"],
                "year": r["year"], "km": r["km"], "price": r["price"],
                "province": r["province"], "fuel": r["fuel"], "url": r["url"],
                "score": r["score"], "margin": r["margin"], "roi": r["roi"],
                "market_price": r["market_price"], "sale_price": r["sale_price"],
                "label": label,
                "stage": r["stage"] or "visto",
                "favorite": bool(r["favorite"]),
                "flags": flags,
                "graves": [f["message"] for f in flags if f.get("severity") == "grave"],
                "positivas": [f["message"] for f in flags if f.get("severity") == "positiva"],
                "source": r["source"],
            })

        tmpl = env.get_template("index.html")
        return HTMLResponse(tmpl.render(
            listings=listings, stages=STAGES, cfg=cfg,
            filters={"score_min": q_score, "stage": q_stage, "label": q_label,
                     "favoritos": q_fav, "q": q_search, "sort": q_sort},
            total=len(listings),
        ))

    async def detalle(request: Request) -> HTMLResponse:
        lid = int(request.path_params["id"])
        conn = _conn()
        row = conn.execute("""
            SELECT l.*, e.score, e.market_price, e.sale_price, e.margin, e.roi,
                   e.flags, e.reasons, e.total_costs, e.costs, e.comparables_n,
                   e.confidence, e.hacienda_value, e.vision,
                   p.stage, p.favorite, p.notes, p.buy_price, p.sell_price, p.extra_costs
            FROM listings l
            LEFT JOIN evaluations e ON e.listing_id = l.id
            LEFT JOIN pipeline p ON p.listing_id = l.id
            WHERE l.id = ?
        """, (lid,)).fetchone()

        price_hist = conn.execute(
            "SELECT price, seen_at FROM price_history WHERE listing_id=? ORDER BY seen_at",
            (lid,)).fetchall()
        conn.close()

        if not row:
            return HTMLResponse("<h1>Anuncio no encontrado</h1>", status_code=404)

        flags = json.loads(row["flags"] or "[]")
        reasons = json.loads(row["reasons"] or "[]")
        costs = json.loads(row["costs"] or "{}")
        images = json.loads(row["images"] or "[]")
        vision = json.loads(row["vision"] or "null")
        label = _ev_label(row)

        from ..models import Listing
        lst = db.row_to_listing(row)
        mo = None
        if row["sale_price"] and row["total_costs"]:
            class _FakeEv:
                sale_price = row["sale_price"]
                total_costs = row["total_costs"]
            mo = max_offer(_FakeEv(), cfg)

        msg = seller_message(lst, mo)
        checklist = inspection_checklist(lst)

        tmpl = env.get_template("detalle.html")
        return HTMLResponse(tmpl.render(
            r=row, flags=flags, reasons=reasons, costs=costs, images=images,
            vision=vision, label=label, stages=STAGES, cfg=cfg,
            max_offer=mo, seller_msg=msg, checklist=checklist,
            price_hist=[{"price": p["price"], "seen_at": p["seen_at"]} for p in price_hist],
        ))

    async def api_pipeline(request: Request) -> JSONResponse:
        """PATCH /api/pipeline/{id}  — actualiza etapa, favorito o notas."""
        lid = int(request.path_params["id"])
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "JSON inválido"}, status_code=400)
        allowed = {"stage", "favorite", "notes", "buy_price", "sell_price", "extra_costs"}
        data = {k: v for k, v in body.items() if k in allowed}
        if not data:
            return JSONResponse({"error": "sin campos válidos"}, status_code=400)
        conn = _conn()
        try:
            update_pipeline(conn, lid, **data)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        finally:
            conn.close()
        return JSONResponse({"ok": True})

    async def api_stats(request: Request) -> JSONResponse:
        conn = _conn()
        total = conn.execute("SELECT COUNT(*) FROM listings WHERE active=1").fetchone()[0]
        scored = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
        alerts = conn.execute(
            "SELECT COUNT(*) FROM evaluations WHERE score >= ?",
            (cfg.get_path("alertas.score_minimo", 70),)).fetchone()[0]
        by_stage = {s: 0 for s in STAGES}
        for r in conn.execute("SELECT stage, COUNT(*) n FROM pipeline GROUP BY stage"):
            by_stage[r["stage"]] = r["n"]
        conn.close()
        return JSONResponse({"total": total, "scored": scored, "alerts": alerts, "stages": by_stage})

    def _ev_label(row) -> str:
        if not row["market_price"] or not row["comparables_n"]:
            return "Sin valoración"
        score = row["score"] or 0
        for threshold, label in [(80, "Chollo"), (65, "Bueno"), (50, "Justo"), (35, "Caro"), (0, "Muy caro")]:
            if score >= threshold:
                return label
        return "Muy caro"

    routes = [
        Route("/", index),
        Route("/detalle/{id:int}", detalle),
        Route("/api/pipeline/{id:int}", api_pipeline, methods=["PATCH"]),
        Route("/api/stats", api_stats),
        Mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static"),
    ]
    return Starlette(routes=routes)
