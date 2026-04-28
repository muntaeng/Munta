"""Shared test fixtures for engine tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


SITES_DIR = Path(__file__).parent.parent.parent / "tests" / "sites"


def _load_site(filename: str) -> dict[str, Any]:
    return json.loads((SITES_DIR / filename).read_text())


@pytest.fixture
def dairy_5mw():
    return _load_site("dairy_5mw.json")


@pytest.fixture
def brewery_8mw():
    return _load_site("brewery_8mw.json")


@pytest.fixture
def soft_drinks_12mw():
    return _load_site("soft_drinks_12mw.json")


@pytest.fixture
def all_sites(dairy_5mw, brewery_8mw, soft_drinks_12mw):
    return [dairy_5mw, brewery_8mw, soft_drinks_12mw]
