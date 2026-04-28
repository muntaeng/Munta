"""
Tests for the real retrieve_reference_docs tool.
Requires a running pgvector DB with ingested corpus and an OpenAI API key.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure repo root is on path for dotenv and imports
_repo_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_repo_root / "backend"))
from dotenv import load_dotenv
for _p in Path(__file__).resolve().parents:
    _env = _p / ".env"
    if _env.exists():
        load_dotenv(_env)
        break

from decarb.tools import dispatch, _embed_call_count, _cached_embed


@pytest.fixture(autouse=True)
def _clear_embed_cache():
    """Clear the LRU cache between tests so cache-hit test is deterministic."""
    _cached_embed.cache_clear()
    yield


def test_dispatch_returns_real_hits():
    """retrieve_reference_docs returns real hits, not a stub."""
    result = dispatch("retrieve_reference_docs", {
        "query": "DEFRA 2025 natural gas emission factor",
    })
    assert "n" in result
    assert result["n"] >= 1
    assert "_stub" not in result
    assert result["hits"][0]["doc_id"].startswith("01-defra-2025")


def test_source_type_filter():
    """source_type_filter restricts hits to that type only."""
    result = dispatch("retrieve_reference_docs", {
        "query": "industrial heat pump COP",
        "source_type_filter": "standard",
    })
    assert result["n"] >= 1
    for hit in result["hits"]:
        assert hit["source_type"] == "standard"


def test_sector_filter():
    """sector filter restricts hits to food_and_drink only."""
    result = dispatch("retrieve_reference_docs", {
        "query": "case study",
        "sector": "food_and_drink",
    })
    assert result["n"] >= 1
    for hit in result["hits"]:
        assert hit["sector"] == "food_and_drink"


def test_truncation_safety():
    """JSON-serialised result truncated to 800 chars still contains a full doc_id."""
    result = dispatch("retrieve_reference_docs", {
        "query": "DEFRA 2025 natural gas emission factor",
    })
    result_json = json.dumps(result)
    truncated = result_json[:800]
    # At least one full doc_id must survive truncation
    found = any(hit["doc_id"] in truncated for hit in result["hits"])
    assert found, f"No complete doc_id found in first 800 chars: {truncated[:200]}..."


def test_lru_cache_hits():
    """Second call with same query does not re-invoke embed_single."""
    import decarb.tools as tools_mod

    # Clear cache and reset counter
    _cached_embed.cache_clear()
    before = tools_mod._embed_call_count

    dispatch("retrieve_reference_docs", {
        "query": "seasonal coefficient of performance SCOP",
    })
    after_first = tools_mod._embed_call_count
    assert after_first == before + 1, "First call should invoke embed once"

    dispatch("retrieve_reference_docs", {
        "query": "seasonal coefficient of performance SCOP",
    })
    after_second = tools_mod._embed_call_count
    assert after_second == after_first, "Second call should hit cache, not re-embed"
