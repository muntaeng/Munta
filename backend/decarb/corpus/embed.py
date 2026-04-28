"""
OpenAI embedding client with batching, retry, and cost metering.
Model: text-embedding-3-large (3072 dims) per architecture spec.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from openai import OpenAI

log = logging.getLogger("corpus.embed")

MODEL = "text-embedding-3-large"
DIMS = 3072
BATCH_SIZE = 96
MAX_TOKENS_PER_INPUT = 8000
BATCH_DELAY_S = 1.0
MAX_RETRIES = 5

# OpenAI pricing for text-embedding-3-large as of 2026-04-28
# $0.13 per 1M tokens
PRICE_PER_1K_TOKENS_USD = 0.00013
USD_TO_GBP = 0.79  # approximate
COST_CEILING_GBP = 8.0


def get_client() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key or key.startswith("sk-...") or len(key) < 20:
        raise RuntimeError(
            "OPENAI_API_KEY not set or is a placeholder. "
            "Set it in .env with your real OpenAI API key."
        )
    return OpenAI(api_key=key)


class EmbeddingMeter:
    """Track embedding token usage and cost."""

    def __init__(self):
        self.total_tokens = 0
        self.total_chunks = 0
        self.cost_gbp = 0.0

    def add(self, tokens: int, chunks: int):
        self.total_tokens += tokens
        self.total_chunks += chunks
        self.cost_gbp = (self.total_tokens / 1000) * PRICE_PER_1K_TOKENS_USD * USD_TO_GBP

    def check_ceiling(self):
        if self.cost_gbp >= COST_CEILING_GBP:
            raise RuntimeError(
                f"Embedding cost ceiling reached: £{self.cost_gbp:.2f} >= £{COST_CEILING_GBP:.2f}. "
                f"Total tokens: {self.total_tokens:,}. Stopping."
            )

    def report(self) -> str:
        return (
            f"Chunks: {self.total_chunks:,}  "
            f"Tokens: {self.total_tokens:,}  "
            f"Cost: £{self.cost_gbp:.4f}"
        )


def embed_texts(
    texts: list[str],
    meter: EmbeddingMeter,
    client: OpenAI | None = None,
) -> list[list[float]]:
    """Embed a list of texts in batches. Returns list of embedding vectors."""
    if client is None:
        client = get_client()

    all_embeddings: list[list[float]] = [[] for _ in texts]

    for batch_start in range(0, len(texts), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(texts))
        batch = texts[batch_start:batch_end]

        for attempt in range(MAX_RETRIES):
            try:
                response = client.embeddings.create(
                    model=MODEL,
                    input=batch,
                )
                break
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate_limit" in err_str or "5" in str(getattr(e, "status_code", "")):
                    wait = 2 ** attempt * 5
                    log.warning(f"Rate limited/server error, waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    time.sleep(wait)
                else:
                    raise
        else:
            raise RuntimeError(f"Failed after {MAX_RETRIES} retries")

        usage_tokens = response.usage.total_tokens if response.usage else sum(
            len(t.split()) for t in batch  # rough fallback
        )
        meter.add(usage_tokens, len(batch))
        meter.check_ceiling()

        for item in response.data:
            all_embeddings[batch_start + item.index] = item.embedding

        if meter.total_chunks % 500 < BATCH_SIZE:
            log.info(f"Progress: {meter.report()}")

        if batch_end < len(texts):
            time.sleep(BATCH_DELAY_S)

    return all_embeddings


def embed_single(text: str, client: OpenAI | None = None) -> list[float]:
    """Embed a single text (for test queries)."""
    if client is None:
        client = get_client()
    response = client.embeddings.create(model=MODEL, input=[text])
    return response.data[0].embedding
