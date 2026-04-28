# Reference corpus — Week 1 spike

Documents the agent retrieves from when grounding numerical claims, citing standards, or reasoning about UK regulation.

## Status (snapshot, 2026-04-28)

108 documents indexed across 9 sections — comfortably over the 80-doc target. All entries have verified URLs, publisher, licence and target filename.

| Section | Section name                                | Target | Indexed |
|---------|---------------------------------------------|-------:|--------:|
| 01      | Emission factors and grid intensity         |      5 |       6 |
| 02      | UK regulatory framework                     |      8 |      15 |
| 03      | Engineering standards (free alternatives)   |     12 |      15 |
| 04      | Heat pump / electrification datasheets      |     15 |      19 |
| 05      | Public worked case studies                  |     15 |      17 |
| 06      | Food & drink sector knowledge               |     10 |      12 |
| 07      | Pinch analysis and process integration      |      8 |       9 |
| 08      | Techno-economic methodology                 |      5 |       7 |
| 09      | Reference consultancy reports               |      5 |       8 |
| **Tot** |                                             | **80** | **108** |

By status: 98 `todo` (URL verified, not yet downloaded) · 7 `free-alt` (free substitute for paid original) · 3 `paid` (CIBSE TM54, Kemp 3rd ed, IChemE 1994 user guide).

## Layout

```
corpus/
├── README.md              this file
├── manifest.yaml          one entry per document — schema documented at top of file
├── manifest.csv           DEPRECATED — see manifest.yaml
└── raw/                   downloaded source documents (currently empty pending download)
    ├── 01_emission_factors/
    ├── 02_uk_regulatory/
    ├── 03_engineering_standards/
    ├── 04_heat_pump_tech/
    ├── 05_case_studies/
    ├── 06_sector_food_drink/
    ├── 07_pinch_analysis/
    ├── 08_techno_economic/
    └── 09_reference_reports/
```

## Manifest schema

Each entry in `manifest.yaml` carries:

| field        | meaning                                                                 |
|--------------|-------------------------------------------------------------------------|
| id           | stable identifier, format `<NN>-<slug>`                                  |
| category     | `01_emission_factors`..`09_reference_reports`                            |
| title        | human-readable document title                                            |
| publisher    | issuing body                                                             |
| url          | canonical download URL (PDF preferred)                                   |
| landing      | (optional) HTML landing page if `url` is a direct asset link             |
| licence      | `ogl-v3` \| `crown-copyright` \| `manufacturer-public` \| `open-access` \| `paid` \| `free-alt` |
| status       | `todo` \| `downloaded` \| `free-alt` \| `paid` \| `blocked`              |
| local_path   | expected file location once downloaded (relative to `raw/`)              |
| notes        | caveats, version info, why-this-doc justification                        |

## Plan-vs-reality fixes recorded in the manifest

A few corrections to the original `plan/spike/week1_corpus.md` callouts surfaced during research and are noted in the relevant entries:

- **CIBSE AM16** named in the plan as "Combined Heat and Power for Buildings" — actually heat pumps for multi-residential. The CHP applications manual is **AM12**. Manifest entry uses AM12.
- **Parat MEW** named as an electrode boiler — actually Parat's exhaust-gas water-tube boiler (marine). The electrode product is **Parat IEH**. Manifest entry uses IEH.
- **Danfoss Termax** doesn't match a real Danfoss product line. Substituted Danfoss IR Application Handbook + Heat Pump Components Selection Guide.
- **DEFRA 2026 factors** not yet published as of today (annual June release pattern). Using DEFRA 2025 as best-current; swap when 2026 drops.
- **PAS 2060** retired 1 Jan 2025; superseded by ISO 14068-1:2023. Both are paid — using BSI's free implementation brochure + NQA's free implementation guide as substitutes.

## Acquisition status — what's blocking, what to hand to Claude Code

This session **could not download files** — the egress allowlist for outbound HTTP is restricted to `*.anthropic.com` / `*.claude.com`, so gov.uk, manufacturer hosts, IEA, NREL etc. all return `cowork-egress-blocked`. WebSearch (which routes through Anthropic) was used to verify every URL, but actual file pulls need to happen either:

1. **In a Cowork session with the egress allowlist expanded** (Settings → Capabilities, then full app restart), or
2. **In Claude Code**, which runs without the same proxy restrictions.

Recommendation: hand `manifest.yaml` to Claude Code and have it run a downloader.

## Suggested downloader behaviour (specification, not code)

- Iterate `documents:` from `manifest.yaml`.
- Skip entries where `status == 'paid'`.
- For each remaining entry, fetch `url` to `raw/<local_path>`. If `url` is an HTML landing page (e.g. CIBSE Knowledge Portal, Bosch product pages, gov.uk publication hubs), expect to follow one or two links to find the actual PDF — keep a small per-publisher adaptor where needed.
- Set `User-Agent` to something polite (the corpus is being collected for non-commercial decarbonisation R&D).
- On success, set `status: downloaded` in the manifest.
- On 4xx/5xx or login wall, set `status: blocked` and capture the failure reason in `notes`. Specifically expect email-gates on CIBSE Knowledge Portal entries (AM17, AM15, Guide A, Guide F companion).
- For NESO FES 2025 supporting docs (data workbook, methodology, assumptions), the asset IDs rotate — re-discover from the FES Documents page rather than hard-coding URLs.
- Validate each downloaded PDF: file size > 50 kB, magic bytes `%PDF-`, page count > 1. Flag anything that fails these checks for re-fetch.

## Quality bar before Week 2

- [ ] All 108 docs in `raw/` (or marked `free-alt` / `paid`).
- [ ] Test query returns correct DEFRA 2025 natural-gas combustion factor.
- [ ] Test query returns correct CIBSE TM54 reference (or its `paid` placeholder note).
- [ ] Test query returns a relevant IETF F&D case study.
- [ ] Total embedding spend < £5.

## Processing pipeline (for Week 1 second half, after acquisition)

1. PDF → markdown via `pymupdf4llm`; HTML → markdown directly.
2. Chunk to 500–1000 tokens with 100-token overlap.
3. Per chunk: text, source filename, document title, section heading, page number.
4. Embed with `text-embedding-3-large` (OpenAI) or Anthropic equivalent.
5. Index in pgvector with HNSW.
