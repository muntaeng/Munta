"""
Chunk markdown text into embedding-ready pieces with metadata.
"""
from __future__ import annotations

import re
from typing import Any

import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")

TARGET_MIN = 500
TARGET_MAX = 1000
OVERLAP = 100
MAX_TOKENS = 8000  # OpenAI per-input limit

# Category → source_type mapping
CATEGORY_SOURCE_TYPE = {
    "01_emission_factors": "regulation",
    "02_uk_regulatory": "regulation",
    "03_engineering_standards": "standard",
    "04_heat_pump_tech": "datasheet",
    "05_case_studies": "case_study",
    "06_sector_food_drink": "case_study",
    "07_pinch_analysis": "textbook",
    "08_techno_economic": "regulation",
    "09_reference_reports": "case_study",
}

FOOD_DRINK_KEYWORDS = re.compile(
    r"\b(food|drink|dairy|brewery|beverage|bakery|confectionery|meat|poultry)\b",
    re.IGNORECASE,
)


def token_count(text: str) -> int:
    return len(_enc.encode(text))


def _split_by_headings(text: str) -> list[dict[str, Any]]:
    """Split markdown into sections by headings. Returns [{heading, text}]."""
    lines = text.split("\n")
    sections: list[dict[str, Any]] = []
    current_heading = ""
    current_lines: list[str] = []

    for line in lines:
        if re.match(r"^#{1,3}\s+", line):
            if current_lines:
                sections.append({
                    "heading": current_heading,
                    "text": "\n".join(current_lines).strip(),
                })
            current_heading = line.strip().lstrip("#").strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append({
            "heading": current_heading,
            "text": "\n".join(current_lines).strip(),
        })

    return sections


def _sliding_window(text: str, heading: str) -> list[dict[str, Any]]:
    """Split long text into overlapping chunks."""
    tokens = _enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + TARGET_MAX, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = _enc.decode(chunk_tokens)
        chunks.append({"heading": heading, "text": chunk_text})
        if end >= len(tokens):
            break
        start = end - OVERLAP
    return chunks


def chunk_document(
    blocks: list[dict[str, Any]],
    doc_id: str,
    doc_title: str,
    source_url: str,
    category: str,
    notes: str = "",
) -> list[dict[str, Any]]:
    """
    Take converted blocks and produce embedding-ready chunks with metadata.
    Each block is {text, page_number}.
    """
    source_type = CATEGORY_SOURCE_TYPE.get(category, "case_study")
    is_food_drink = category == "06_sector_food_drink"

    # Gather all text with page tracking
    all_sections: list[dict[str, Any]] = []
    for block in blocks:
        page = block.get("page_number")
        sections = _split_by_headings(block["text"])
        for s in sections:
            s["page_number"] = page
        all_sections.extend(sections)

    # Fold small sibling sections together
    merged: list[dict[str, Any]] = []
    buffer_heading = ""
    buffer_text = ""
    buffer_page = None

    for s in all_sections:
        s_tokens = token_count(s["text"])

        if s_tokens >= TARGET_MIN:
            # Flush buffer
            if buffer_text.strip():
                merged.append({"heading": buffer_heading, "text": buffer_text.strip(), "page_number": buffer_page})
            buffer_heading = s["heading"]
            buffer_text = s["text"]
            buffer_page = s["page_number"]
        else:
            combined = (buffer_text + "\n\n" + s["text"]).strip() if buffer_text else s["text"]
            if token_count(combined) <= TARGET_MAX:
                buffer_text = combined
                if not buffer_heading:
                    buffer_heading = s["heading"]
                if buffer_page is None:
                    buffer_page = s["page_number"]
            else:
                # Flush buffer then start new
                if buffer_text.strip():
                    merged.append({"heading": buffer_heading, "text": buffer_text.strip(), "page_number": buffer_page})
                buffer_heading = s["heading"]
                buffer_text = s["text"]
                buffer_page = s["page_number"]

    if buffer_text.strip():
        merged.append({"heading": buffer_heading, "text": buffer_text.strip(), "page_number": buffer_page})

    # Split oversized sections, enforce max token limit
    final_sections: list[dict[str, Any]] = []
    for m in merged:
        tc = token_count(m["text"])
        if tc > TARGET_MAX:
            splits = _sliding_window(m["text"], m["heading"])
            for sp in splits:
                sp["page_number"] = m["page_number"]
            final_sections.extend(splits)
        else:
            final_sections.append(m)

    # Check for food/drink sector
    if not is_food_drink and notes:
        is_food_drink = bool(FOOD_DRINK_KEYWORDS.search(notes))

    # Build chunk metadata
    chunks = []
    heading_path: list[str] = []
    for i, s in enumerate(final_sections):
        if s["heading"]:
            heading_path = [s["heading"]]

        sector = "food_and_drink" if is_food_drink else None
        # Also check chunk text for food/drink keywords
        if not sector and FOOD_DRINK_KEYWORDS.search(s["text"][:500]):
            # Only tag if category is case_study or sector-related
            if category in ("05_case_studies", "06_sector_food_drink"):
                sector = "food_and_drink"

        tc = token_count(s["text"])
        # Hard cap at MAX_TOKENS
        if tc > MAX_TOKENS:
            tokens = _enc.encode(s["text"])[:MAX_TOKENS]
            s["text"] = _enc.decode(tokens)
            tc = MAX_TOKENS

        chunks.append({
            "doc_id": doc_id,
            "doc_title": doc_title,
            "section": " > ".join(heading_path) if heading_path else None,
            "page_number": s["page_number"],
            "chunk_index": i,
            "text": s["text"],
            "token_count": tc,
            "embedding": None,  # filled by embed step
            "source_url": source_url,
            "source_type": source_type,
            "sector": sector,
        })

    return chunks
