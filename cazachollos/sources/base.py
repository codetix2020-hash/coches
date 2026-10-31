"""Interfaz común de conectores y registro de salud (avisa si una fuente deja de dar datos)."""

from __future__ import annotations

import logging
import sqlite3
import traceback
from typing import Callable, Iterable

from ..models import Listing, now_iso

log = logging.getLogger("cazachollos")


class Connector:
    name = "base"

    def __init__(self, cfg):
        self.cfg = cfg

    def enabled(self) -> bool:
        return True

    def fetch(self) -> Iterable[Listing]:  # pragma: no cover - interfaz
        raise NotImplementedError


def run_connector(conn: sqlite3.Connection, connector: Connector) -> list[Listing]:
    started = now_iso()
    cur = conn.execute("INSERT INTO connector_runs (connector, started_at) VALUES (?,?)",
                       (connector.name, started))
    run_id = cur.lastrowid
    conn.commit()
    try:
        items = list(connector.fetch())
        conn.execute("UPDATE connector_runs SET finished_at=?, items=?, ok=1 WHERE id=?",
                     (now_iso(), len(items), run_id))
        conn.commit()
        log.info("%s: %d anuncios", connector.name, len(items))
        return items
    except Exception as exc:  # un conector roto no debe tumbar a los demás
        conn.execute("UPDATE connector_runs SET finished_at=?, ok=0, error=? WHERE id=?",
                     (now_iso(), f"{exc}\n{traceback.format_exc()[-800:]}", run_id))
        conn.commit()
        log.error("%s falló: %s", connector.name, exc)
        return []


def health(conn: sqlite3.Connection, empty_runs_alert: int = 5) -> list[dict]:
    """Estado de cada conector y si hay que avisar (errores o N ejecuciones seguidas vacías)."""
    out = []
    names = [r["connector"] for r in conn.execute("SELECT DISTINCT connector FROM connector_runs")]
    for name in names:
        runs = conn.execute(
            "SELECT * FROM connector_runs WHERE connector=? ORDER BY id DESC LIMIT ?", (name, empty_runs_alert)
        ).fetchall()
        last = runs[0]
        problem = None
        if not last["ok"]:
            problem = f"error en la última ejecución: {(last['error'] or '').splitlines()[0][:160]}"
        elif len(runs) >= empty_runs_alert and all(r["items"] == 0 for r in runs):
            problem = f"{empty_runs_alert} ejecuciones seguidas sin datos: puede que la fuente haya cambiado"
        out.append({"connector": name, "last_run": last["started_at"], "items": last["items"],
                    "ok": bool(last["ok"]) and problem is None, "problem": problem})
    return out


def notify_health(conn: sqlite3.Connection, send: Callable[[str], bool]) -> None:
    for h in health(conn):
        if h["problem"]:
            send(f"🔧 Conector <b>{h['connector']}</b>: {h['problem']}")
