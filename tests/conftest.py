"""Fixtures compartidas para todos los tests."""

import pytest
from cazachollos.config import Config, load_config
from cazachollos import db


@pytest.fixture
def cfg():
    """Config con valores de test (Madrid, particular, márgenes típicos)."""
    return load_config()


@pytest.fixture
def conn(tmp_path):
    """Base de datos SQLite en memoria para tests aislados."""
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()
