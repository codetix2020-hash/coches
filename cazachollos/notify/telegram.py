"""Notificaciones por Telegram.

Sin token → modo simulación: el mensaje se imprime en consola con prefijo [SIM].
Con token  → envía por la Bot API de Telegram al chat_id configurado.

Nunca lanza excepciones: si falla, registra el error y devuelve False.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ..config import secret
from ..models import Listing
from ..scoring import PENALTY

log = logging.getLogger("cazachollos")

_CARGURUS_EMOJI = {
    "chollo": "🔥",
    "bueno": "✅",
    "justo": "➡️",
    "caro": "⚠️",
    "muy caro": "🚫",
    "sin valoración": "❓",
}


def _label_emoji(label: str | None) -> str:
    return _CARGURUS_EMOJI.get((label or "").lower(), "")


def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_message(res) -> str:
    """Genera el texto HTML para Telegram a partir de un pipeline.Result."""
    lst: Listing = res.listing
    ev = res.evaluation
    from ..scoring import cargurus_label  # evitar importación circular

    label = cargurus_label(ev)
    emoji = _label_emoji(label)

    lines = [
        f"{emoji} <b>{_html_escape(lst.title or 'Sin título')}</b>",
        f"📍 {_html_escape(lst.province or '?')}  ·  "
        f"🗓 {lst.year or '?'}  ·  {(lst.km or 0):,.0f} km".replace(",", "."),
    ]

    if lst.price:
        lines.append(f"💶 Precio: <b>{lst.price:,.0f} €</b>".replace(",", "."))
    if ev.market_price:
        lines.append(f"📊 Mercado: {ev.market_price:,.0f} € · Venta realista: {(ev.sale_price or 0):,.0f} €".replace(",", "."))
    if ev.margin is not None:
        lines.append(f"💰 Margen neto: <b>{ev.margin:,.0f} €</b>  (ROI {(ev.roi or 0):.0%})".replace(",", "."))

    max_price = _max_offer(lst, ev)
    if max_price is not None:
        lines.append(f"🎯 Oferta máxima: <b>{max_price:,.0f} €</b>".replace(",", "."))

    lines.append(f"⭐ Puntuación: {ev.score}/100  [{label}]")

    graves = [f for f in ev.flags if f.severity == "grave"]
    if graves:
        lines.append("🚨 " + " · ".join(f.message for f in graves))

    if lst.url:
        lines.append(f'\n🔗 <a href="{lst.url}">Ver anuncio</a>')

    return "\n".join(lines)


def _max_offer(lst: Listing, ev) -> float | None:
    """Precio máximo a pagar = venta realista − costes − margen mínimo."""
    if ev.sale_price is None or ev.total_costs is None:
        return None
    from ..config import load_config
    try:
        cfg = load_config()
    except Exception:
        return None
    min_margin = cfg.get_path("objetivos.margen_minimo_eur", 1000)
    result = ev.sale_price - ev.total_costs - min_margin
    return round(max(0.0, result), -1) if result > 0 else None


class TelegramNotifier:
    """Notificador Telegram con fallback a simulación en consola."""

    def __init__(self, cfg=None):
        self.token = secret("TELEGRAM_TOKEN")
        self.chat_id = secret("TELEGRAM_CHAT_ID")
        self.sim = not (self.token and self.chat_id)
        if self.sim:
            log.info("Telegram: sin token/chat_id → modo simulación (los mensajes se imprimen en consola)")

    def _send_raw(self, text: str) -> bool:
        if self.sim:
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            print(f"\n[SIM Telegram {ts}]\n{text}\n{'─'*60}")
            return True
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = json.dumps({
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            log.error("Telegram error: %s", exc)
            return False

    def send_alert(self, channel: str, res) -> bool:
        """Interfaz que usa pipeline.process(notifier=callable)."""
        if channel != "telegram":
            return False
        text = _format_message(res)
        ok = self._send_raw(text)
        if ok:
            log.info("Telegram: alerta enviada para listing %d", res.listing_id)
        return ok

    def send_text(self, text: str) -> bool:
        """Envía texto libre (para resúmenes y salud)."""
        return self._send_raw(text)

    def send_summary(self, results: list) -> bool:
        """Resumen diario: cuántos chollos encontrados."""
        alerts = [r for r in results if r.evaluation.score >= 70]
        if not alerts:
            return self._send_raw("📋 <b>Resumen diario</b>\nHoy no hubo chollos nuevos.")
        lines = [f"📋 <b>Resumen diario — {len(alerts)} chollo(s):</b>"]
        for r in alerts[:10]:
            lst = r.listing
            ev = r.evaluation
            lines.append(
                f"• {lst.title or lst.source_id}  {lst.price:,.0f} € → margen {(ev.margin or 0):,.0f} €  (score {ev.score})".replace(",", ".")
            )
        if len(alerts) > 10:
            lines.append(f"…y {len(alerts) - 10} más en el panel.")
        return self._send_raw("\n".join(lines))
