"""Carga de config.yaml y del archivo .env (secretos)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> None:
    """Lee .env sin dependencias externas. Nunca imprime los valores."""
    env_path = path or ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def secret(name: str) -> str | None:
    value = os.environ.get(name)
    return value or None


class Config(dict):
    """Diccionario con acceso por ruta: cfg.get_path('costes.gestoria')."""

    def get_path(self, dotted: str, default: Any = None) -> Any:
        node: Any = self
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def load_config(path: Path | str | None = None) -> Config:
    load_env()
    cfg_path = Path(path) if path else Path(os.environ.get("CAZACHOLLOS_CONFIG", ROOT / "config.yaml"))
    with open(cfg_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return Config(data)


def db_path() -> Path:
    return Path(os.environ.get("CAZACHOLLOS_DB", ROOT / "data" / "cazachollos.db"))
