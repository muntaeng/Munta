"""
Quality-bar test queries for the corpus retrieval pipeline.
Run after ingestion to verify the three required test queries pass.

Usage:
    python -m pytest backend/decarb/corpus/tests/test_retrieval.py -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Load .env
from dotenv import load_dotenv
for _p in Path(__file__).resolve().parents:
    _env = _p / ".env"
    if _env.exists():
        load_dotenv(_env)
        break

from backend.decarb.corpus.db import get_conn, test_retrieval
from backend.decarb.corpus.embed import embed_single, get_client


@pytest.fixture(scope="module")
def conn():
    c = get_conn()
    yield c
    c.close()


@pytest.fixture(scope="module")
def oai_client():
    return get_client()


def test_defra_2025_natural_gas(conn, oai_client):
    """Top-3 retrieved chunks include at least one from 01-defra-2025-*."""
    query = "What is the DEFRA 2025 emission factor for natural gas combustion?"
    emb = embed_single(query, client=oai_client)
    hits = test_retrieval(conn, emb, limit=5)
    top3 = hits[:3]
    doc_ids = [h["doc_id"] for h in top3]
    assert any(
        did.startswith("01-defra-2025") for did in doc_ids
    ), f"Expected 01-defra-2025-* in top 3, got: {doc_ids}"


def test_scop_en14825(conn, oai_client):
    """Top-3 includes EHPA air-water or brine-water HP testing doc."""
    query = (
        "How is the seasonal coefficient of performance (SCOP) "
        "defined for heat pump testing under EN 14825 / EN 14511?"
    )
    emb = embed_single(query, client=oai_client)
    hits = test_retrieval(conn, emb, limit=5)
    top3 = hits[:3]
    doc_ids = [h["doc_id"] for h in top3]
    target_ids = {"03-ehpa-airwater-hp-testing", "03-ehpa-brinewater-hp-testing"}
    assert any(
        did in target_ids for did in doc_ids
    ), f"Expected EHPA testing doc in top 3, got: {doc_ids}"


def test_ietf_food_drink_case_study(conn, oai_client):
    """Top-3 includes IETF doc with sector=food_and_drink."""
    query = "Show me a UK food-and-drink case study from the Industrial Energy Transformation Fund."
    emb = embed_single(query, client=oai_client)
    hits = test_retrieval(conn, emb, limit=5)
    top3 = hits[:3]
    found = any(
        h["doc_id"].startswith("05-ietf-") and h.get("sector") == "food_and_drink"
        for h in top3
    )
    doc_ids = [(h["doc_id"], h.get("sector")) for h in top3]
    assert found, (
        f"Expected 05-ietf-* with sector=food_and_drink in top 3, got: {doc_ids}. "
        "If all three fail, suspect schema/connection; if just one, suspect chunking on that doc."
    )
