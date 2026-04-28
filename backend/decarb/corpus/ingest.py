#!/usr/bin/env python3
"""
Corpus ingestion pipeline: convert → chunk → embed → upsert into pgvector.

Usage:
    python -m backend.decarb.corpus.ingest                   # process all new docs
    python -m backend.decarb.corpus.ingest --reembed          # force reprocess all
    python -m backend.decarb.corpus.ingest --doc-id <id>      # process one doc
    python -m backend.decarb.corpus.ingest --dry-run           # no embed/DB, just counts
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Walk up to find .env at repo root
_here = Path(__file__).resolve()
for _p in _here.parents:
    _env = _p / ".env"
    if _env.exists():
        load_dotenv(_env)
        break

from ruamel.yaml import YAML

from backend.decarb.corpus.convert import convert_file
from backend.decarb.corpus.chunk import chunk_document
from backend.decarb.corpus.embed import embed_texts, embed_single, EmbeddingMeter, get_client
from backend.decarb.corpus.db import get_conn, count_chunks_for_doc, upsert_chunks, test_retrieval

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("corpus.ingest")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
RAW_DIR = CORPUS_DIR / "raw"
MARKDOWN_DIR = CORPUS_DIR / "markdown"
MANIFEST_PATH = CORPUS_DIR / "manifest.yaml"
REPORT_PATH = CORPUS_DIR / "ingest_report.md"

# Test queries for quality bar
TEST_QUERIES = [
    {
        "query": "What is the DEFRA 2025 emission factor for natural gas combustion?",
        "match": lambda doc_id: doc_id.startswith("01-defra-2025"),
        "desc": "DEFRA 2025 natural gas factor",
    },
    {
        "query": "How is the seasonal coefficient of performance (SCOP) defined for heat pump testing under EN 14825 / EN 14511?",
        "match": lambda doc_id: doc_id in ("03-ehpa-airwater-hp-testing", "03-ehpa-brinewater-hp-testing"),
        "desc": "EHPA heat pump testing SCOP",
    },
    {
        "query": "Show me a UK food-and-drink case study from the Industrial Energy Transformation Fund.",
        "match": lambda doc_id, sector=None: doc_id.startswith("05-ietf-") and sector == "food_and_drink",
        "desc": "IETF food & drink case study",
    },
]


def load_manifest() -> list[dict[str, Any]]:
    yaml = YAML()
    data = yaml.load(MANIFEST_PATH)
    return list(data["documents"])


def save_markdown(doc_id: str, category: str, text: str):
    """Save intermediate markdown for inspection."""
    cat_dir = MARKDOWN_DIR / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / f"{doc_id}.md").write_text(text, encoding="utf-8")


def process_doc(
    entry: dict[str, Any],
    meter: EmbeddingMeter,
    conn,
    oai_client,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Process a single document through the full pipeline. Returns stats dict."""
    doc_id = entry["id"]
    category = entry["category"]
    local_path = entry["local_path"]
    raw_path = RAW_DIR / local_path

    if not raw_path.exists():
        log.warning(f"  {doc_id}: file not found at {raw_path}")
        return {"doc_id": doc_id, "status": "skipped", "reason": "file not found"}

    # Convert
    try:
        blocks = convert_file(raw_path)
    except Exception as e:
        log.error(f"  {doc_id}: conversion error: {e}")
        return {"doc_id": doc_id, "status": "error", "reason": f"convert: {e}"}

    if not blocks:
        log.warning(f"  {doc_id}: no content extracted")
        return {"doc_id": doc_id, "status": "skipped", "reason": "no content"}

    # Save intermediate markdown
    full_md = "\n\n---\n\n".join(b["text"] for b in blocks)
    save_markdown(doc_id, category, full_md)

    # Chunk
    chunks = chunk_document(
        blocks=blocks,
        doc_id=doc_id,
        doc_title=entry.get("title", doc_id),
        source_url=entry.get("url", ""),
        category=category,
        notes=str(entry.get("notes", "")),
    )

    total_tokens = sum(c["token_count"] for c in chunks)

    if dry_run:
        return {
            "doc_id": doc_id,
            "status": "dry_run",
            "chunks": len(chunks),
            "tokens": total_tokens,
        }

    # Embed
    texts = [c["text"] for c in chunks]
    try:
        embeddings = embed_texts(texts, meter, client=oai_client)
    except Exception as e:
        log.error(f"  {doc_id}: embedding error: {e}")
        return {"doc_id": doc_id, "status": "error", "reason": f"embed: {e}"}

    for chunk, emb in zip(chunks, embeddings):
        chunk["embedding"] = emb

    # Upsert
    try:
        inserted = upsert_chunks(conn, doc_id, chunks)
    except Exception as e:
        log.error(f"  {doc_id}: DB upsert error: {e}")
        return {"doc_id": doc_id, "status": "error", "reason": f"db: {e}"}

    log.info(f"  {doc_id}: {inserted} chunks, {total_tokens} tokens")
    return {
        "doc_id": doc_id,
        "status": "ok",
        "chunks": inserted,
        "tokens": total_tokens,
    }


def run_test_queries(conn, oai_client) -> list[dict[str, Any]]:
    """Run the three quality-bar test queries. Returns list of result dicts."""
    results = []
    for tq in TEST_QUERIES:
        query_emb = embed_single(tq["query"], client=oai_client)
        hits = test_retrieval(conn, query_emb, limit=5)
        top3 = hits[:3]

        # Check if any match
        passed = False
        for h in top3:
            match_fn = tq["match"]
            try:
                # Test query 3 uses sector param
                if match_fn(h["doc_id"], sector=h.get("sector")):
                    passed = True
                    break
            except TypeError:
                if match_fn(h["doc_id"]):
                    passed = True
                    break

        results.append({
            "query": tq["query"],
            "desc": tq["desc"],
            "passed": passed,
            "top3": [
                {
                    "doc_id": h["doc_id"],
                    "section": h.get("section", ""),
                    "text": h["text"][:200] + "..." if len(h["text"]) > 200 else h["text"],
                    "similarity": round(h["similarity"], 4),
                    "source_type": h.get("source_type"),
                    "sector": h.get("sector"),
                }
                for h in top3
            ],
        })
    return results


def write_report(
    doc_results: list[dict],
    meter: EmbeddingMeter,
    elapsed_s: float,
    test_results: list[dict],
):
    """Write corpus/ingest_report.md."""
    ok = [r for r in doc_results if r["status"] == "ok"]
    total_chunks = sum(r.get("chunks", 0) for r in ok)
    total_tokens = sum(r.get("tokens", 0) for r in ok)
    tests_passed = sum(1 for t in test_results if t["passed"])

    lines = [
        "# Corpus Ingestion Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Docs processed | {len(ok)} |",
        f"| Chunks created | {total_chunks:,} |",
        f"| Tokens embedded | {meter.total_tokens:,} |",
        f"| Embedding cost (GBP) | £{meter.cost_gbp:.4f} |",
        f"| Elapsed | {int(elapsed_s // 60)}m {int(elapsed_s % 60):02d}s |",
        f"| Test queries passed | {tests_passed} / {len(test_results)} |",
        "",
    ]

    errors = [r for r in doc_results if r["status"] == "error"]
    if errors:
        lines.extend([
            "## Errors",
            "",
            "| Doc ID | Reason |",
            "|--------|--------|",
        ])
        for e in errors:
            lines.append(f"| {e['doc_id']} | {e.get('reason', '')} |")
        lines.append("")

    lines.extend([
        "## Test Query Results",
        "",
    ])
    for t in test_results:
        status = "PASS" if t["passed"] else "FAIL"
        lines.append(f"### {status}: {t['desc']}")
        lines.append(f"Query: {t['query']}")
        lines.append("")
        lines.append("| Rank | doc_id | similarity | sector | text (truncated) |")
        lines.append("|------|--------|------------|--------|------------------|")
        for i, h in enumerate(t["top3"]):
            text_esc = h["text"].replace("|", "\\|").replace("\n", " ")[:150]
            lines.append(
                f"| {i+1} | {h['doc_id']} | {h['similarity']:.4f} | "
                f"{h.get('sector') or '-'} | {text_esc} |"
            )
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines) + "\n")
    log.info(f"Report written: {REPORT_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Ingest corpus into pgvector.")
    parser.add_argument("--reembed", action="store_true", help="Force reprocess all")
    parser.add_argument("--doc-id", type=str, help="Process only this doc ID")
    parser.add_argument("--dry-run", action="store_true", help="Convert+chunk only, no embed/DB")
    args = parser.parse_args()

    manifest = load_manifest()
    downloaded = [d for d in manifest if d["status"] == "downloaded"]
    log.info(f"Manifest: {len(manifest)} entries, {len(downloaded)} downloaded")

    if args.doc_id:
        downloaded = [d for d in downloaded if d["id"] == args.doc_id]
        if not downloaded:
            log.error(f"No downloaded entry with id={args.doc_id}")
            sys.exit(1)

    conn = None
    oai_client = None
    if not args.dry_run:
        conn = get_conn()
        oai_client = get_client()

    meter = EmbeddingMeter()
    start = time.time()
    doc_results = []

    for i, entry in enumerate(downloaded):
        doc_id = entry["id"]
        log.info(f"[{i+1}/{len(downloaded)}] {doc_id}")

        # Skip if already in DB and not forcing reembed
        if not args.dry_run and not args.reembed:
            existing = count_chunks_for_doc(conn, doc_id)
            if existing > 0:
                log.info(f"  {doc_id}: already has {existing} chunks, skipping")
                doc_results.append({
                    "doc_id": doc_id, "status": "skipped", "reason": "already in DB",
                    "chunks": existing,
                })
                continue

        result = process_doc(entry, meter, conn, oai_client, dry_run=args.dry_run)
        doc_results.append(result)

    elapsed = time.time() - start

    # Summary
    ok = [r for r in doc_results if r["status"] == "ok"]
    total_chunks = sum(r.get("chunks", 0) for r in ok)
    log.info(f"\n{'='*60}")
    log.info(f"docs processed:        {len(ok)}")
    log.info(f"chunks created:        {total_chunks:,}")
    log.info(f"tokens embedded:       {meter.total_tokens:,}")
    log.info(f"embedding cost (GBP):  £{meter.cost_gbp:.4f}")
    log.info(f"elapsed:               {int(elapsed // 60)}m {int(elapsed % 60):02d}s")

    if args.dry_run:
        dry = [r for r in doc_results if r["status"] == "dry_run"]
        est_tokens = sum(r.get("tokens", 0) for r in dry)
        est_cost = (est_tokens / 1000) * 0.00013 * 0.79
        log.info(f"\nDry run estimate:")
        log.info(f"  Total chunks: {sum(r.get('chunks', 0) for r in dry):,}")
        log.info(f"  Total tokens: {est_tokens:,}")
        log.info(f"  Est cost:     £{est_cost:.4f}")
        return

    # Run test queries
    log.info("\nRunning test queries...")
    test_results = run_test_queries(conn, oai_client)
    tests_passed = sum(1 for t in test_results if t["passed"])
    log.info(f"test queries passed:   {tests_passed} / {len(test_results)}")

    for t in test_results:
        status = "PASS" if t["passed"] else "FAIL"
        log.info(f"  {status}: {t['desc']}")
        for i, h in enumerate(t["top3"]):
            log.info(f"    #{i+1} {h['doc_id']} (sim={h['similarity']:.4f})")

    # Write report
    write_report(doc_results, meter, elapsed, test_results)

    if conn:
        conn.close()

    if tests_passed < len(test_results):
        log.error(
            f"\n{len(test_results) - tests_passed} test(s) failed. "
            "If all three fail, suspect schema/connection; if just one, suspect chunking on that doc."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
