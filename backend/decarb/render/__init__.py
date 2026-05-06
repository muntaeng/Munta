"""Markdown report renderer.

Pure Jinja2 templating against engine module output dicts. The renderer
performs no arithmetic — every number in the rendered report must come from a
structured engine result.

Public surface: ``render_report``.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).parent / "templates"
DEFAULT_RUNS_DIR = Path(__file__).parent.parent / "runs"
TEMPLATE_NAME = "v0_pathway_report.md.j2"


def _build_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(disabled_extensions=("md", "j2")),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )

    def fmt_int(v: Any) -> str:
        if v is None:
            return "—"
        try:
            return f"{int(round(float(v))):,}"
        except (TypeError, ValueError):
            return str(v)

    def fmt_float(v: Any, dp: int = 1) -> str:
        if v is None:
            return "—"
        try:
            return f"{float(v):,.{dp}f}"
        except (TypeError, ValueError):
            return str(v)

    def kwh_to_gwh(v: Any) -> str:
        if v is None:
            return "—"
        try:
            return f"{float(v)/1_000_000:,.1f}"
        except (TypeError, ValueError):
            return str(v)

    def kwh_to_mwh(v: Any) -> str:
        if v is None:
            return "—"
        try:
            return f"{float(v)/1_000:,.0f}"
        except (TypeError, ValueError):
            return str(v)

    def fmt_pct(v: Any, dp: int = 1) -> str:
        if v is None:
            return "—"
        try:
            f = float(v)
            if abs(f) <= 1.0:
                f *= 100.0
            return f"{f:,.{dp}f}%"
        except (TypeError, ValueError):
            return str(v)

    env.filters["fmt_int"] = fmt_int
    env.filters["fmt_float"] = fmt_float
    env.filters["kwh_to_gwh"] = kwh_to_gwh
    env.filters["kwh_to_mwh"] = kwh_to_mwh
    env.filters["fmt_pct"] = fmt_pct
    return env


def _aggregate_provenance(
    parse_result: dict,
    carbon_result: dict,
    screen_result: dict,
    dispatch_result: dict,
    pathway_result: dict | None = None,
) -> list[dict]:
    """Union of provenance lists, tagged by originating module."""
    out: list[dict] = []
    sources: list[tuple[str, dict | None]] = [
        ("parse_energy_profile", parse_result),
        ("compute_baseline_carbon", carbon_result),
        ("screen_technologies", screen_result),
        ("simulate_site_dispatch", dispatch_result),
        ("optimise_investment_pathway", pathway_result),
    ]
    for module_name, res in sources:
        if not res:
            continue
        for entry in res.get("provenance", []) or []:
            tagged = {"module": module_name}
            tagged.update(entry)
            out.append(tagged)
    return out


def _aggregate_standards(
    parse_result: dict,
    carbon_result: dict,
    screen_result: dict,
    dispatch_result: dict,
    pathway_result: dict | None = None,
) -> list[str]:
    """Deduplicated union of standards_cited lists, preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    sources = [parse_result, carbon_result, screen_result, dispatch_result]
    if pathway_result:
        sources.append(pathway_result)
    for res in sources:
        for std in (res or {}).get("standards_cited", []) or []:
            if std not in seen:
                seen.add(std)
                out.append(std)
    return out


def render_report(
    *,
    site_brief: dict,
    parse_result: dict,
    carbon_result: dict,
    screen_result: dict,
    dispatch_result: dict,
    pathway_result: dict | None = None,
    uncertainty_result: dict | None = None,
    format: str = "markdown",
    include_appendices: bool = True,
    output_dir: Path | str | None = None,
    write_file: bool = True,
    timestamp: str | None = None,
) -> dict:
    """Render an 11-section consultancy-grade pathway report.

    All numerical content is sourced from the four engine result dicts; the
    template does no arithmetic. Modules not yet implemented appear as
    ROADMAP placeholders, not fabricated numbers.

    Returns a record with ``markdown``, ``path`` (if written), section count,
    aggregated provenance count, and the standards-register length.
    """
    if format not in ("markdown", "pdf"):
        raise ValueError(f"format must be 'markdown' or 'pdf', got {format!r}")
    if format == "pdf":
        raise NotImplementedError(
            "PDF rendering deferred — markdown only in v0. "
            "Once stable, weasyprint will be wired in."
        )

    env = _build_env()
    template = env.get_template(TEMPLATE_NAME)

    provenance = _aggregate_provenance(
        parse_result, carbon_result, screen_result, dispatch_result,
        pathway_result,
    )
    standards = _aggregate_standards(
        parse_result, carbon_result, screen_result, dispatch_result,
        pathway_result,
    )
    if uncertainty_result:
        for entry in uncertainty_result.get("provenance", []) or []:
            tagged = {"module": "monte_carlo_uncertainty"}
            tagged.update(entry)
            provenance.append(tagged)
        for std in uncertainty_result.get("standards_cited", []) or []:
            if std not in standards:
                standards.append(std)

    # Prefer the recommended (Balanced) pathway's year-1 dispatch over
    # the canonical hand-spec dispatch when both are available — issue
    # C in the dairy report review. The canonical stack is illustrative
    # only and does not correspond to any §4.1 pathway, so quoting its
    # numbers in §1 / §5.3 mis-describes the recommendation.
    pathway_dispatch = None
    pathway_dispatch_pathway_name = None
    pathway_dispatch_calendar_year = None
    if pathway_result and pathway_result.get("pathways"):
        for prefer in ("balanced", "conservative", "aggressive"):
            pw = pathway_result["pathways"].get(prefer)
            if pw and pw.get("first_full_stack_dispatch"):
                pathway_dispatch = pw["first_full_stack_dispatch"]
                pathway_dispatch_pathway_name = prefer
                pathway_dispatch_calendar_year = pw.get(
                    "first_full_stack_calendar_year"
                )
                break

    headline_dispatch = pathway_dispatch or dispatch_result

    ts = timestamp or dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    md = template.render(
        site=site_brief,
        parse=parse_result,
        carbon=carbon_result,
        screen=screen_result,
        dispatch=dispatch_result,
        headline_dispatch=headline_dispatch,
        pathway_dispatch=pathway_dispatch,
        pathway_dispatch_pathway_name=pathway_dispatch_pathway_name,
        pathway_dispatch_calendar_year=pathway_dispatch_calendar_year,
        pathway=pathway_result,
        uncertainty=uncertainty_result,
        provenance=provenance,
        standards=standards,
        include_appendices=include_appendices,
        generated_at=ts,
        engine_version="v0",
    )

    # §9 specificity gate — issue G in the dairy report review.
    # The engine spec (prompts/orchestrator_v0_1.txt) requires §9
    # decisions to be in the form "Senior to confirm: <finding>. If
    # <alternative>, <impact> changes from <X> to <Y>." Count the
    # "Senior to confirm:" markers and refuse to emit a report whose
    # §9 has fewer than four. This is a deterministic post-condition,
    # not an LLM-tested heuristic.
    senior_to_confirm_count = md.count("**Senior to confirm:")
    if senior_to_confirm_count < 4:
        raise AssertionError(
            f"§9 specificity gate failed: rendered report has only "
            f"{senior_to_confirm_count} 'Senior to confirm:' decisions, "
            "engine spec requires ≥4 (HP capacity, grid headroom, NH3 "
            "charge limit, IETF eligibility). Issue G."
        )

    out: dict[str, Any] = {
        "format": "markdown",
        "markdown": md,
        "char_count": len(md),
        "section_count": 11,
        "provenance_entries": len(provenance),
        "standards_cited_count": len(standards),
        "section_9_senior_decisions_count": senior_to_confirm_count,
        "path": None,
    }

    if write_file:
        out_dir = Path(output_dir) if output_dir is not None else DEFAULT_RUNS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        site_id = site_brief.get("site_id") or "UNKNOWN_SITE"
        out_path = out_dir / f"{site_id}_{ts}.md"
        out_path.write_text(md, encoding="utf-8")
        out["path"] = str(out_path)

    return out


__all__ = ["render_report"]
