"""Interfaz de línea de comandos de Cazachollos.

Uso:
  python -m cazachollos <comando> [opciones]

Comandos:
  init              Crea la base de datos y comprueba la configuración.
  run [--loop]      Lanza una búsqueda completa. Con --loop repite cada N minutos.
  demo              Carga 25 anuncios ficticios y muestra los resultados.
  valorar <url>     Valora un anuncio a partir de su URL (requiere enriquecer_paginas=true).
  chollos-hoy       Muestra los mejores chollos encontrados hoy.
  informe-semanal   Resumen de la semana: chollos, comprados, vendidos y beneficio.
  dashboard         Abre el panel web en http://127.0.0.1:8765
  itp <precio>      Calcula el ITP para un precio de compra dado.
  salud             Muestra el estado de cada conector de datos.
  buscar <texto>    Parsea una búsqueda en lenguaje natural y muestra los filtros.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("cazachollos")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_init(args, cfg) -> int:
    from . import db
    conn = db.connect()
    conn.close()
    print("✓ Base de datos lista.")
    print(f"  Provincia: {cfg.get_path('yo.provincia', '?')}")
    print(f"  Comunidad: {cfg.get_path('yo.comunidad_autonoma', '?')}")
    print(f"  Régimen:   {cfg.get_path('yo.regimen', 'particular')}")
    print(f"  Precio:    {cfg.get_path('busqueda.precio_min', 0):,}–{cfg.get_path('busqueda.precio_max', 0):,} €".replace(",", "."))
    print(f"  Radio:     {cfg.get_path('busqueda.radio_km', 300)} km")
    print(f"  Margen:    {cfg.get_path('objetivos.margen_minimo_eur', 1000):,} €".replace(",", "."))
    return 0


def _run_once(cfg) -> list:
    from . import db, pipeline
    from .notify.telegram import TelegramNotifier
    from .sources.demo import DemoConnector
    from .sources.email_alerts import EmailAlertsConnector
    from .sources.files_import import FilesImportConnector
    from .vision import analyze_photos

    conn = db.connect()
    notifier = TelegramNotifier(cfg)

    vision_fn = None
    if cfg.get_path("vision.activo", False):
        def vision_fn(lst):
            return analyze_photos(lst, cfg)

    all_listings = []
    connectors = [
        FilesImportConnector(cfg),
        EmailAlertsConnector(cfg),
        DemoConnector(cfg),
    ]
    from .sources.base import run_connector
    for c in connectors:
        if c.enabled():
            items = run_connector(conn, c)
            all_listings.extend(items)

    if not all_listings:
        log.info("Ninguna fuente activa aportó anuncios.")
        conn.close()
        return []

    results = pipeline.process(conn, all_listings, cfg,
                               notifier=notifier.send_alert,
                               vision=vision_fn)
    conn.close()
    return results


def cmd_run(args, cfg) -> int:
    if args.loop:
        interval = int(args.interval) if hasattr(args, "interval") and args.interval else 30
        print(f"▶ Modo loop cada {interval} min. Ctrl+C para parar.")
        while True:
            try:
                results = _run_once(cfg)
                alerts = [r for r in results if r.evaluation.score >= cfg.get_path("alertas.score_minimo", 70)]
                print(f"  [{datetime.now().strftime('%H:%M')}] {len(results)} anuncios, "
                      f"{alerts} alertas. Próxima ejecución en {interval} min.")
                time.sleep(interval * 60)
            except KeyboardInterrupt:
                print("\nParado.")
                return 0
    else:
        results = _run_once(cfg)
        _print_results_summary(results, cfg)
    return 0


def cmd_demo(args, cfg) -> int:
    from . import db, pipeline
    from .notify.telegram import TelegramNotifier
    from .sources.base import run_connector
    from .sources.demo import DemoConnector

    # Activar la fuente demo temporalmente
    cfg.setdefault("fuentes", {}).setdefault("demo", {})["activo"] = True

    conn = db.connect()
    connector = DemoConnector(cfg)
    listings = run_connector(conn, connector)
    notifier = TelegramNotifier(cfg)
    results = pipeline.process(conn, listings, cfg, notifier=notifier.send_alert)
    conn.close()

    print(f"\n{'='*60}")
    print(f"  DEMO — {len(results)} anuncios procesados")
    print(f"{'='*60}")
    _print_results_summary(results, cfg)
    return 0


def cmd_valorar(args, cfg) -> int:
    if not args.url:
        print("Uso: valorar <url>", file=sys.stderr)
        return 1

    from . import db, pipeline
    from .sources.page_parser import parse_page
    from .sources.polite_http import fetch_html

    html = fetch_html(args.url, cfg)
    if not html:
        print(f"No se pudo descargar {args.url}", file=sys.stderr)
        return 1

    lst = parse_page(args.url, html)
    if not lst:
        print("No se reconoció el anuncio en esa URL.", file=sys.stderr)
        return 1

    conn = db.connect()
    ev = pipeline.evaluate(conn, lst, cfg)
    conn.close()

    _print_evaluation(lst, ev, cfg)
    return 0


def cmd_chollos_hoy(args, cfg) -> int:
    from . import db

    conn = db.connect()
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    rows = conn.execute("""
        SELECT l.*, e.score, e.market_price, e.sale_price, e.margin, e.roi, e.flags, e.reasons
        FROM listings l
        JOIN evaluations e ON e.listing_id = l.id
        WHERE l.first_seen >= ?
          AND e.score >= ?
        ORDER BY e.score DESC
        LIMIT 20
    """, (since, cfg.get_path("alertas.score_minimo", 70))).fetchall()
    conn.close()

    if not rows:
        print("No hay chollos nuevos en las últimas 24 horas.")
        return 0

    print(f"\n{'─'*60}")
    print(f"  CHOLLOS DE HOY ({len(rows)} resultados)")
    print(f"{'─'*60}")
    for r in rows:
        import json
        flags = json.loads(r["flags"] or "[]")
        graves = [f["message"] for f in flags if f.get("severity") == "grave"]
        print(f"[{r['score']:3d}] {r['title'] or r['source_id']}")
        print(f"       {r['price']:,.0f} € · {r['province'] or '?'} · {r['year'] or '?'} · {(r['km'] or 0):,.0f} km".replace(",", "."))
        if r["margin"]:
            print(f"       margen ≈ {r['margin']:,.0f} €  ROI {(r['roi'] or 0):.0%}".replace(",", "."))
        if graves:
            print(f"       ⚠ {', '.join(graves[:2])}")
        print(f"       {r['url'] or ''}")
    return 0


def cmd_informe_semanal(args, cfg) -> int:
    from . import db
    import json

    conn = db.connect()
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    total = conn.execute("SELECT COUNT(*) FROM listings WHERE first_seen >= ?", (since,)).fetchone()[0]
    alertas = conn.execute(
        "SELECT COUNT(*) FROM evaluations e JOIN listings l ON l.id=e.listing_id "
        "WHERE l.first_seen >= ? AND e.score >= ?", (since, 70)).fetchone()[0]
    comprados = conn.execute(
        "SELECT COUNT(*) FROM pipeline p JOIN listings l ON l.id=p.listing_id "
        "WHERE p.stage='comprado' AND p.updated_at >= ?", (since,)).fetchone()[0]
    vendidos = conn.execute(
        "SELECT SUM(p.sell_price - p.buy_price - COALESCE(p.extra_costs,0)) as beneficio "
        "FROM pipeline p WHERE p.stage='vendido' AND p.updated_at >= ?", (since,)).fetchone()
    beneficio = vendidos["beneficio"] or 0 if vendidos else 0

    conn.close()

    print(f"\n{'='*60}")
    print(f"  INFORME SEMANAL (últimos 7 días)")
    print(f"{'='*60}")
    print(f"  Anuncios revisados:  {total:,}".replace(",", "."))
    print(f"  Chollos detectados:  {alertas}")
    print(f"  Coches comprados:    {comprados}")
    print(f"  Beneficio vendidos:  {beneficio:,.0f} €".replace(",", "."))
    return 0


def cmd_dashboard(args, cfg) -> int:
    host = cfg.get_path("panel.host", "127.0.0.1")
    port = cfg.get_path("panel.puerto", 8765)
    url = f"http://{host}:{port}"
    print(f"▶ Abriendo panel en {url}")
    webbrowser.open(url)

    from .web.app import create_app
    import uvicorn
    app = create_app(cfg)
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


def cmd_itp(args, cfg) -> int:
    if not args.precio:
        print("Uso: itp <precio>", file=sys.stderr)
        return 1
    try:
        precio = float(str(args.precio).replace(",", ".").replace(".", "", args.precio.count(".") - 1) if isinstance(args.precio, str) else args.precio)
    except ValueError:
        print(f"Precio no válido: {args.precio}", file=sys.stderr)
        return 1

    from .costs import itp_cost
    from .models import Listing

    lst = Listing(source="manual", source_id="itp_calc")
    itp, nota, hv = itp_cost(lst, precio, cfg)
    ccaa = cfg.get_path("yo.comunidad_autonoma", "?")
    print(f"\n  Precio de compra:    {precio:,.0f} €".replace(",", "."))
    if hv:
        print(f"  Valor Hacienda:      {hv:,.0f} €".replace(",", "."))
    print(f"  ITP ({ccaa}):         {itp:,.0f} €".replace(",", "."))
    print(f"  Nota:                {nota}")
    return 0


def cmd_salud(args, cfg) -> int:
    from . import db
    from .sources.base import health

    conn = db.connect()
    informe = health(conn)
    conn.close()

    if not informe:
        print("No hay ejecuciones registradas aún.")
        return 0

    print(f"\n  {'CONECTOR':<20} {'ÚLTIMA EJECUCIÓN':<22} {'ITEMS':>6}  ESTADO")
    print(f"  {'─'*20} {'─'*22} {'─'*6}  {'─'*20}")
    for h in informe:
        estado = "✓ OK" if h["ok"] else f"✗ {h['problem'] or 'error'}"
        print(f"  {h['connector']:<20} {h['last_run'] or '—':<22} {h['items']:>6}  {estado}")
    return 0


def cmd_buscar(args, cfg) -> int:
    if not args.texto:
        print("Uso: buscar <texto>", file=sys.stderr)
        return 1
    from .search import describe_filters, parse_query
    query = " ".join(args.texto)
    filters = parse_query(query)
    print(f"\n  Consulta: \"{query}\"")
    print(f"  Filtros:  {describe_filters(filters)}")
    if not filters:
        print("  (no se reconoció ningún filtro; prueba con marcas, precios o km)")
    return 0


# ── Helpers de presentación ───────────────────────────────────────────────────

def _print_results_summary(results: list, cfg) -> None:
    import json
    from .scoring import cargurus_label

    in_filters = [r for r in results if r.in_filters]
    alerts = [r for r in in_filters if r.evaluation.score >= cfg.get_path("alertas.score_minimo", 70)]

    print(f"\n  Total procesados:   {len(results)}")
    print(f"  Dentro de filtros:  {len(in_filters)}")
    print(f"  Chollos (score≥{cfg.get_path('alertas.score_minimo', 70)}): {len(alerts)}")

    if not alerts:
        print("\n  No hay chollos esta vez.")
        return

    print(f"\n  {'─'*60}")
    for r in sorted(alerts, key=lambda x: x.evaluation.score, reverse=True)[:10]:
        lst, ev = r.listing, r.evaluation
        label = cargurus_label(ev)
        flags_text = ""
        if ev.flags:
            graves = [f.message for f in ev.flags if f.severity == "grave"]
            if graves:
                flags_text = f"  ⚠ {graves[0]}"
        print(f"  [{ev.score:3d}] {lst.title or lst.source_id[:40]}")
        print(f"        {(lst.price or 0):,.0f} € · {lst.province or '?'} · "
              f"{lst.year or '?'} · {(lst.km or 0):,.0f} km  [{label}]".replace(",", "."))
        if ev.margin is not None:
            print(f"        margen {ev.margin:,.0f} € · ROI {(ev.roi or 0):.0%}{flags_text}".replace(",", "."))
        print(f"        {lst.url or '(sin URL)'}")


def _print_evaluation(lst, ev, cfg) -> None:
    from .pipeline import max_offer
    from .scoring import cargurus_label
    from .templates import inspection_checklist, seller_message

    label = cargurus_label(ev)
    mo = max_offer(ev, cfg)

    print(f"\n{'='*60}")
    print(f"  {lst.title or lst.source_id}")
    print(f"{'='*60}")
    print(f"  Precio anunciado: {(lst.price or 0):,.0f} €".replace(",", "."))
    if ev.market_price:
        print(f"  Precio mercado:   {ev.market_price:,.0f} €  ({ev.comparables_n} comparables, conf. {ev.confidence:.0%})".replace(",", "."))
        print(f"  Precio venta:     {(ev.sale_price or 0):,.0f} €".replace(",", "."))
    print(f"  Costes totales:   {ev.total_costs:,.0f} €".replace(",", "."))
    if ev.margin is not None:
        print(f"  Margen neto:      {ev.margin:,.0f} €  (ROI {(ev.roi or 0):.0%})".replace(",", "."))
    if mo is not None:
        print(f"  Oferta máxima:    {mo:,.0f} €".replace(",", "."))
    print(f"  Puntuación:       {ev.score}/100  [{label}]")

    if ev.flags:
        print("\n  Alarmas y señales:")
        for f in ev.flags:
            icon = "⚠" if f.severity in ("grave", "media") else ("✓" if f.severity == "positiva" else "·")
            print(f"    {icon} [{f.severity}] {f.message}")

    print("\n  Desglose de costes:")
    for nombre, info in ev.costs.items():
        print(f"    {nombre:<20} {info['eur']:>8,.0f} €  {info.get('nota', '')}".replace(",", "."))

    if mo is not None:
        msg = seller_message(lst, mo)
        print(f"\n{'─'*60}")
        print("  MENSAJE PARA EL VENDEDOR:")
        print(f"{'─'*60}")
        print(msg)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cazachollos",
        description="Buscador de coches de segunda mano infravalorados.",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Logging detallado")
    p.add_argument("--config", metavar="PATH", help="Ruta al config.yaml (defecto: config.yaml del proyecto)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Inicializa la base de datos y muestra la configuración")

    run_p = sub.add_parser("run", help="Lanza una búsqueda completa")
    run_p.add_argument("--loop", action="store_true", help="Repite cada N minutos")
    run_p.add_argument("--interval", type=int, default=30, metavar="MIN", help="Minutos entre ejecuciones (default: 30)")

    sub.add_parser("demo", help="Carga datos de demostración")

    val_p = sub.add_parser("valorar", help="Valora un anuncio por URL")
    val_p.add_argument("url", nargs="?", help="URL del anuncio")

    sub.add_parser("chollos-hoy", help="Chollos de las últimas 24 h")
    sub.add_parser("informe-semanal", help="Resumen de la semana")
    sub.add_parser("dashboard", help="Abre el panel web")

    itp_p = sub.add_parser("itp", help="Calcula el ITP para un precio dado")
    itp_p.add_argument("precio", nargs="?", help="Precio de compra en €")

    sub.add_parser("salud", help="Estado de los conectores")

    buscar_p = sub.add_parser("buscar", help="Parsea búsqueda en lenguaje natural")
    buscar_p.add_argument("texto", nargs="*", help="Texto de búsqueda")

    return p


def main(argv=None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    _setup_logging(args.verbose)

    from .config import load_config
    cfg = load_config(args.config if args.config else None)

    dispatch = {
        "init": cmd_init,
        "run": cmd_run,
        "demo": cmd_demo,
        "valorar": cmd_valorar,
        "chollos-hoy": cmd_chollos_hoy,
        "informe-semanal": cmd_informe_semanal,
        "dashboard": cmd_dashboard,
        "itp": cmd_itp,
        "salud": cmd_salud,
        "buscar": cmd_buscar,
    }
    fn = dispatch.get(args.cmd)
    if fn:
        return fn(args, cfg)
    p.print_help()
    return 1
