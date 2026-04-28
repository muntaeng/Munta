"""
Database helpers for corpus_chunks — psycopg (v3) connection + upsert.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

# Walk up to find .env at repo root
_here = Path(__file__).resolve()
for _p in _here.parents:
    _env = _p / ".env"
    if _env.exists():
        load_dotenv(_env)
        break


def get_connection_string() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set in .env")
    return url


def get_conn() -> psycopg.Connection:
    return psycopg.connect(get_connection_string(), autocommit=True)


def count_chunks_for_doc(conn: psycopg.Connection, doc_id: str) -> int:
    row = conn.execute(
        "SELECT count(*) FROM corpus_chunks WHERE doc_id = %s", (doc_id,)
    ).fetchone()
    return row[0] if row else 0


def upsert_chunks(conn: psycopg.Connection, doc_id: str, chunks: list[dict[str, Any]]) -> int:
    """Delete existing chunks for doc_id, then bulk insert new ones. Returns count inserted."""
    with conn.transaction():
        conn.execute("DELETE FROM corpus_chunks WHERE doc_id = %s", (doc_id,))
        if not chunks:
            return 0
        sql = """
            INSERT INTO corpus_chunks
                (doc_id, doc_title, section, page_number, chunk_index,
                 text, token_count, embedding, source_url, source_type, sector)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s)
        """
        with conn.cursor() as cur:
            for c in chunks:
                emb_str = "[" + ",".join(str(x) for x in c["embedding"]) + "]" if c["embedding"] else None
                text = c["text"].replace("\x00", "") if c["text"] else c["text"]
                cur.execute(sql, (
                    c["doc_id"], c["doc_title"], c["section"], c["page_number"],
                    c["chunk_index"], text, c["token_count"], emb_str,
                    c["source_url"], c["source_type"], c["sector"],
                ))
    return len(chunks)


def search_chunks(
    conn: psycopg.Connection,
    query_embedding: list[float],
    *,
    limit: int = 5,
    source_type: str | None = None,
    sector: str | None = None,
) -> list[dict]:
    """Cosine similarity search with optional WHERE filters."""
    emb_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    where_clauses = []
    # params order: SELECT similarity (%s), WHERE filters (%s...), ORDER BY (%s), LIMIT (%s)
    params: list[Any] = [emb_str]
    if source_type:
        where_clauses.append("source_type = %s")
        params.append(source_type)
    if sector:
        where_clauses.append("sector = %s")
        params.append(sector)
    where_sql = (" AND " + " AND ".join(where_clauses)) if where_clauses else ""
    params.append(emb_str)  # for ORDER BY
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT doc_id, doc_title, section, page_number, text, token_count,
               source_url, source_type, sector,
               1 - (embedding <=> %s::vector) AS similarity
        FROM corpus_chunks
        WHERE embedding IS NOT NULL{where_sql}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        tuple(params),
    ).fetchall()
    cols = ["doc_id", "doc_title", "section", "page_number", "text",
            "token_count", "source_url", "source_type", "sector", "similarity"]
    return [dict(zip(cols, row)) for row in rows]


def test_retrieval(conn: psycopg.Connection, query_embedding: list[float], limit: int = 5) -> list[dict]:
    """Cosine similarity search. Returns list of {doc_id, section, text, similarity}."""
    emb_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    rows = conn.execute(
        """
        SELECT doc_id, doc_title, section, page_number, text, token_count, source_type, sector,
               1 - (embedding <=> %s::vector) AS similarity
        FROM corpus_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (emb_str, emb_str, limit),
    ).fetchall()
    cols = ["doc_id", "doc_title", "section", "page_number", "text",
            "token_count", "source_type", "sector", "similarity"]
    return [dict(zip(cols, row)) for row in rows]
