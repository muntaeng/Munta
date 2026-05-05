"""
Tool definitions for the orchestrator agent.

Each tool is:
  1. A Python function with rigorous type hints + docstring
  2. Registered in TOOL_SCHEMAS for Anthropic tool-use
  3. Dispatched in TOOL_HANDLERS

Design principle: the LLM never does arithmetic. Every number in the output
traces to a tool call here.

Tools are imported from `decarb.engine.*` modules; this file is just the
Anthropic-facing wiring. The real engineering lives in `engine/`.

parse_energy_profile and screen_technologies are NOT in TOOL_SCHEMAS — the
agent pre-runs them before the LLM loop and injects a compact summary into
the initial message.  This keeps tool-call payloads lean.
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from typing import Any, Callable

from decarb.engine.hp_cycle import calculate_hp_cycle as _calculate_hp_cycle
from decarb.engine.parse import parse_energy_profile as _parse_energy_profile
from decarb.engine.carbon import compute_baseline_carbon as _compute_baseline_carbon
from decarb.engine.dispatch import simulate_site_dispatch as _simulate_site_dispatch
from decarb.engine.screen import screen_technologies as _screen_technologies
from decarb.render import render_report as _render_report
from decarb.corpus.db import get_conn, search_chunks
from decarb.corpus.embed import embed_single, get_client as _get_embed_client


# ---------------------------------------------------------------------------
# Site context — populated by agent.py before the LLM loop
# ---------------------------------------------------------------------------

_site_context: dict[str, Any] = {}


def set_site_context(ctx: dict[str, Any]) -> None:
    """Store pre-computed site context (energy profile, screening) for tool wrappers.

    The renderer reads from a `engine_results` sub-dict that this module
    accumulates as the agent calls tools (compute_baseline_carbon,
    simulate_site_dispatch, etc.). We seed it from the pre-run results
    that ``agent.py`` passes in (energy_profile, screening) so the
    renderer has the full bundle available regardless of tool-call
    ordering.
    """
    global _site_context
    _site_context = dict(ctx)
    bundle = dict(_site_context.get("engine_results") or {})
    if "energy_profile" in _site_context and "parse_energy_profile" not in bundle:
        bundle["parse_energy_profile"] = _site_context["energy_profile"]
    if "screening" in _site_context and "screen_technologies" not in bundle:
        bundle["screen_technologies"] = _site_context["screening"]
    _site_context["engine_results"] = bundle


def get_site_context() -> dict[str, Any]:
    return _site_context


def _record_engine_output(tool_name: str, full_output: dict[str, Any]) -> None:
    """Accumulate full engine output keyed by tool name, for the renderer."""
    bundle = _site_context.setdefault("engine_results", {})
    bundle[tool_name] = full_output


# ---------------------------------------------------------------------------
# Real tools (week 1 + 2 — implemented in decarb/engine/)
# ---------------------------------------------------------------------------

def calculate_hp_cycle(**kwargs: Any) -> dict[str, Any]:
    full = _calculate_hp_cycle(**kwargs)
    perf = full.get("performance", {})
    # Compact: just the numbers the LLM needs to reason about
    return {
        "cop_heating": perf.get("cop_heating"),
        "cop_net_electrical": perf.get("cop_heating_net_electrical"),
        "carnot_cop": perf.get("carnot_cop_heating"),
        "pressure_ratio": perf.get("pressure_ratio"),
        "constraints_ok": full.get("operating_constraints_passed"),
        "sizing": full.get("sizing") or {},
        "warnings": [w["code"] for w in full.get("warnings", [])],
    }


def parse_energy_profile(**kwargs: Any) -> dict[str, Any]:
    full = _parse_energy_profile(**kwargs)
    _record_engine_output("parse_energy_profile", full)
    return full


def compute_baseline_carbon(**kwargs: Any) -> dict[str, Any]:
    # Translate lean schema params to engine's annual_balance_kwh dict
    if "annual_balance_kwh" not in kwargs and "electricity_kwh" in kwargs:
        elec = kwargs.pop("electricity_kwh")
        gas = kwargs.pop("natural_gas_kwh", 0)
        oil = kwargs.pop("fuel_oil_kwh", 0)
        bio = kwargs.pop("biomass_kwh", 0)
        kwargs["annual_balance_kwh"] = {
            "electricity_kwh": elec,
            "natural_gas_kwh": gas,
            "fuel_oil_kwh_equivalent": oil,
            "biomass_kwh": bio,
            "fuel_oil_litres": 0,
            "total_primary_kwh": elec + gas + oil + bio,
        }
    full = _compute_baseline_carbon(**kwargs)
    _record_engine_output("compute_baseline_carbon", full)
    # Compact: key numbers only
    return {
        "scope_1_tco2e": full.get("scope_1", {}).get("t_co2e_year"),
        "scope_2_loc_tco2e": full.get("scope_2_location_based", {}).get("t_co2e_year"),
        "scope_1_2_total": full.get("totals", {}).get("scope_1_2_loc_t_co2e"),
        "scope_1_2_3_total": full.get("totals", {}).get("scope_1_2_3_t_co2e"),
    }


# ---------------------------------------------------------------------------
# Dispatch wrapper — pulls energy_profile from pre-computed site context
# ---------------------------------------------------------------------------


def simulate_site_dispatch(**kwargs: Any) -> dict[str, Any]:
    energy_profile = _site_context.get("energy_profile")
    if not energy_profile:
        return {"error": "No energy profile in site context — agent must pre-run parse_energy_profile"}
    kwargs["energy_profile"] = energy_profile
    full = _simulate_site_dispatch(**kwargs)
    _record_engine_output("simulate_site_dispatch", full)
    # Compact: carbon + utilisation summary only
    carbon = full.get("carbon_summary", {})
    utils = full.get("equipment_utilisation", [])
    return {
        "scope_1_tco2e": carbon.get("scope_1_t_co2e"),
        "scope_2_tco2e": carbon.get("scope_2_loc_t_co2e"),
        "total_tco2e": carbon.get("total_t_co2e"),
        "gas_displaced_pct": full.get("annual_energy_summary", {}).get("gas_displacement_pct"),
        "equipment": [
            {"id": u.get("tech_id"), "type": u.get("tech_type"),
             "output_mwh": round(u.get("annual_thermal_output_kwh", 0) / 1000, 1),
             "cop": u.get("weighted_cop"), "load_factor": u.get("load_factor")}
            for u in utils
        ],
        "warnings": [w.get("code", "") for w in full.get("warnings", [])],
    }


# ---------------------------------------------------------------------------
# Stubs — implemented in week 2 with the depth spec'd in plan/spike/week2_engine_modules.md
# ---------------------------------------------------------------------------


def screen_technologies(**kwargs: Any) -> dict[str, Any]:
    full = _screen_technologies(**kwargs)
    _record_engine_output("screen_technologies", full)
    return full


def compute_pinch_analysis(**kwargs: Any) -> dict[str, Any]:
    """STUB. Implemented Week 3 — see week2_engine_modules.md §8."""
    return {"_stub": True, "tool": "compute_pinch_analysis"}


def optimise_investment_pathway(**kwargs: Any) -> dict[str, Any]:
    """STUB. Implemented Week 2 — see week2_engine_modules.md §6."""
    return {"_stub": True, "tool": "optimise_investment_pathway"}


def monte_carlo_uncertainty(**kwargs: Any) -> dict[str, Any]:
    """STUB. Implemented Week 2 — see week2_engine_modules.md §7."""
    return {"_stub": True, "tool": "monte_carlo_uncertainty"}


def compute_safety_constraints(**kwargs: Any) -> dict[str, Any]:
    """STUB. Implemented Week 3 — see week2_engine_modules.md §9."""
    return {"_stub": True, "tool": "compute_safety_constraints"}


def assess_grid_connection(**kwargs: Any) -> dict[str, Any]:
    """STUB. Implemented Week 3 — see week2_engine_modules.md §10."""
    return {"_stub": True, "tool": "assess_grid_connection"}


def compute_reliability_availability(**kwargs: Any) -> dict[str, Any]:
    """STUB. Implemented Week 3 — see week2_engine_modules.md §11."""
    return {"_stub": True, "tool": "compute_reliability_availability"}


def lookup_grants(**kwargs: Any) -> dict[str, Any]:
    """STUB. Implemented Week 3."""
    return {"_stub": True, "tool": "lookup_grants"}


def lookup_regulations(**kwargs: Any) -> dict[str, Any]:
    """STUB. Implemented Week 3."""
    return {"_stub": True, "tool": "lookup_regulations"}


@functools.lru_cache(maxsize=128)
def _cached_embed(query: str) -> tuple[float, ...]:
    """LRU-cached query embedding. Returns tuple (hashable) for cache compatibility."""
    return tuple(embed_single(query, client=_get_embed_client()))


# Module-level counter for testing cache behaviour
_embed_call_count = 0
_original_cached_embed = _cached_embed.__wrapped__


def _counted_embed(query: str) -> tuple[float, ...]:
    global _embed_call_count
    _embed_call_count += 1
    return _original_cached_embed(query)


# Rewrap with counting
_cached_embed = functools.lru_cache(maxsize=128)(_counted_embed)


def retrieve_reference_docs(**kwargs: Any) -> dict[str, Any]:
    """RAG retrieval over the reference corpus via pgvector cosine search."""
    query = kwargs.get("query", "")
    top_k = kwargs.get("top_k", 5)
    source_type_filter = kwargs.get("source_type_filter")
    sector = kwargs.get("sector")

    conn = get_conn()
    try:
        # Check corpus is populated
        row = conn.execute("SELECT count(*) FROM corpus_chunks").fetchone()
        if not row or row[0] == 0:
            return {"n": 0, "hits": [], "error": "corpus_chunks is empty — run ingestion"}

        query_emb = list(_cached_embed(query))
        hits = search_chunks(
            conn, query_emb,
            limit=top_k,
            source_type=source_type_filter,
            sector=sector,
        )
    finally:
        conn.close()

    _ws = re.compile(r"\s+")
    result_hits = []
    for h in hits:
        snippet = _ws.sub(" ", h.get("text", "")).strip()[:180]
        result_hits.append({
            "doc_id": h["doc_id"],
            "section": h.get("section") or "",
            "similarity": round(h["similarity"], 3),
            "snippet": snippet,
            "doc_title": h.get("doc_title") or "",
            "page_number": h.get("page_number"),
            "source_url": h.get("source_url") or "",
            "source_type": h.get("source_type") or "",
            "sector": h.get("sector"),
        })

    return {"n": len(result_hits), "hits": result_hits}


def validate_pathway(**kwargs: Any) -> dict[str, Any]:
    """STUB. Implemented Week 4."""
    return {"_stub": True, "tool": "validate_pathway"}


def render_report(**kwargs: Any) -> dict[str, Any]:
    """Render the 11-section pathway markdown report from accumulated
    engine outputs. Reads from ``_site_context['engine_results']`` rather
    than taking tool-output payloads — this keeps the LLM-facing tool
    surface lean while still giving the renderer the full bundles.
    """
    fmt = kwargs.get("format", "markdown")
    include_appendices = kwargs.get("include_appendices", True)

    site_brief = _site_context.get("site_brief")
    bundle = _site_context.get("engine_results") or {}
    parse_result = bundle.get("parse_energy_profile")
    carbon_result = bundle.get("compute_baseline_carbon")
    screen_result = bundle.get("screen_technologies")
    dispatch_result = bundle.get("simulate_site_dispatch")

    missing = [
        name for name, val in (
            ("site_brief", site_brief),
            ("parse_energy_profile", parse_result),
            ("compute_baseline_carbon", carbon_result),
            ("screen_technologies", screen_result),
            ("simulate_site_dispatch", dispatch_result),
        )
        if not val
    ]
    if missing:
        return {
            "error": (
                "render_report cannot run — missing required engine outputs in "
                "site context: " + ", ".join(missing) + ". Call those tools first."
            )
        }

    if fmt == "pdf":
        return {"error": "PDF rendering is deferred — request format='markdown'."}

    result = _render_report(
        site_brief=site_brief,
        parse_result=parse_result,
        carbon_result=carbon_result,
        screen_result=screen_result,
        dispatch_result=dispatch_result,
        format="markdown",
        include_appendices=include_appendices,
    )
    return {
        "path": result["path"],
        "format": result["format"],
        "char_count": result["char_count"],
        "section_count": result["section_count"],
        "provenance_entries": result["provenance_entries"],
        "standards_cited_count": result["standards_cited_count"],
    }


# ---------------------------------------------------------------------------
# Anthropic tool schemas — note these mirror the *real* function signatures,
# including all engineering depth. The LLM sees the full surface.
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    # -----------------------------------------------------------------------
    # Real tools — lean parameter sets, no site-brief passthrough
    # -----------------------------------------------------------------------
    {
        "name": "calculate_hp_cycle",
        "description": (
            "Compute a heat pump thermodynamic cycle (CoolProp). "
            "Returns state points, COP, sizing, warnings, BS EN 378 checks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "refrigerant": {"type": "string", "description": "One of: 'Ammonia', 'R744', 'R290', 'R1234ze(E)', 'R134a'"},
                "process_evaporator_temp_c": {"type": "number", "description": "Process-side cold temperature °C"},
                "process_condenser_temp_c": {"type": "number", "description": "Process-side hot temperature °C"},
                "cycle_type": {"type": "string", "enum": ["single_stage", "two_stage_economiser", "two_stage_intercooled", "cascade", "transcritical_co2"], "default": "single_stage"},
                "evaporator_approach_k": {"type": "number", "default": 5.0},
                "condenser_approach_k": {"type": "number", "default": 5.0},
                "superheat_useful_k": {"type": "number", "default": 5.0},
                "subcool_k": {"type": "number", "default": 3.0},
                "compressor_type": {"type": "string", "enum": ["screw", "reciprocating", "scroll", "centrifugal", "turbo"], "default": "screw"},
                "isentropic_efficiency": {"type": "number", "description": "Optional override"},
                "capacity_kw_thermal": {"type": "number", "description": "Heating duty kW; if given, sizing block populated"},
                "operating_point": {"type": "string", "enum": ["design", "part_load_75", "part_load_50", "part_load_25"], "default": "design"},
            },
            "required": ["refrigerant", "process_evaporator_temp_c", "process_condenser_temp_c"],
        },
    },
    {
        "name": "compute_baseline_carbon",
        "description": (
            "GHG Protocol Scope 1+2+3 baseline using DEFRA 2026 factors + NESO grid intensity. "
            "Returns tCO2e breakdown, regulatory exposure, 15-year trajectory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "electricity_kwh": {"type": "number", "description": "Annual electricity consumption kWh"},
                "natural_gas_kwh": {"type": "number", "description": "Annual natural gas consumption kWh"},
                "fuel_oil_kwh": {"type": "number", "default": 0, "description": "Annual fuel oil kWh equivalent"},
                "biomass_kwh": {"type": "number", "default": 0},
                "year": {"type": "integer", "default": 2026},
                "site_in_uk_ets": {"type": "boolean", "default": False},
                "site_secr_reportable": {"type": "boolean", "default": True},
                "cca_subsector": {"type": "string"},
                "cbam_exposed": {"type": "boolean", "default": False},
            },
            "required": ["electricity_kwh", "natural_gas_kwh"],
        },
    },
    {
        "name": "simulate_site_dispatch",
        "description": (
            "Simulate 8,760-hour merit-order dispatch for an electrified technology stack. "
            "Energy profile is loaded automatically from pre-computed site context. "
            "Returns annual energy summary, gas displacement %, COP, carbon, and audit trail."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "technology_stack": {
                    "type": "array",
                    "description": (
                        "Ordered list of technology configs. Each dict needs 'type' key. "
                        "Types: 'heat_pump' (capacity_kw_thermal, refrigerant, compressor_type, "
                        "source_type, sink_temp_c, serves_end_uses), "
                        "'electrode_boiler' (capacity_kw, efficiency, serves_end_uses), "
                        "'thermal_storage' (capacity_kwh, charge_rate_kw, discharge_rate_kw, "
                        "round_trip_efficiency), "
                        "'gas_boiler' (capacity_kw, efficiency, serves_end_uses)."
                    ),
                    "items": {"type": "object", "additionalProperties": True},
                },
                "dispatch_policy": {
                    "type": "string",
                    "enum": ["merit_order", "carbon_minimal", "pareto_weighted", "regulatory_constrained"],
                    "default": "merit_order",
                },
                "year": {"type": "integer", "default": 2026},
            },
            "required": ["technology_stack"],
        },
    },
    # -----------------------------------------------------------------------
    # Stubs — lean schemas with specific typed params, no open dicts
    # -----------------------------------------------------------------------
    {
        "name": "compute_pinch_analysis",
        "description": "STUB Week 3. Pinch analysis: composite curves, min utility targets, HEN synthesis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hot_streams": {"type": "array", "items": {"type": "object"}, "description": "List of {name, T_start_c, T_target_c, duty_kw}"},
                "cold_streams": {"type": "array", "items": {"type": "object"}, "description": "List of {name, T_start_c, T_target_c, duty_kw}"},
                "dt_min_k": {"type": "number", "default": 10.0},
            },
            "required": ["hot_streams", "cold_streams"],
        },
    },
    {
        "name": "optimise_investment_pathway",
        "description": "STUB Week 2. Multi-period MILP: optimal technology sequencing over planning horizon.",
        "input_schema": {
            "type": "object",
            "properties": {
                "shortlisted_tech_ids": {"type": "array", "items": {"type": "string"}, "description": "Technology IDs from screening"},
                "planning_horizon_years": {"type": "integer", "default": 15},
                "capex_budget_gbp": {"type": "number"},
                "discount_rate": {"type": "number", "default": 0.08},
                "scenarios": {"type": "array", "items": {"type": "string"}, "description": "e.g. ['conservative', 'balanced', 'aggressive']"},
            },
            "required": ["shortlisted_tech_ids"],
        },
    },
    {
        "name": "monte_carlo_uncertainty",
        "description": "STUB Week 2. Monte Carlo on NPV and carbon trajectory with Sobol sensitivity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario_id": {"type": "string", "description": "Which pathway scenario to stress-test"},
                "n_samples": {"type": "integer", "default": 1000},
                "uncertain_params": {"type": "array", "items": {"type": "string"}, "description": "e.g. ['gas_price', 'electricity_price', 'grid_carbon_intensity']"},
            },
            "required": ["scenario_id"],
        },
    },
    {
        "name": "compute_safety_constraints",
        "description": "STUB Week 3. BS EN 378 charge limits, ATEX/DSEAR zones, F-gas tracking.",
        "input_schema": {
            "type": "object",
            "properties": {
                "technology_ids": {"type": "array", "items": {"type": "string"}, "description": "Shortlisted tech IDs to assess"},
                "refrigerant": {"type": "string"},
                "occupied_zone_proximity_m": {"type": "number"},
            },
            "required": ["technology_ids"],
        },
    },
    {
        "name": "assess_grid_connection",
        "description": "STUB Week 3. G99 assessment, DNO reinforcement risk, time-to-connect.",
        "input_schema": {
            "type": "object",
            "properties": {
                "additional_electrical_load_kw": {"type": "number", "description": "Total new electrical demand kW"},
                "existing_connection_mva": {"type": "number"},
                "headroom_mva": {"type": "number"},
            },
            "required": ["additional_electrical_load_kw"],
        },
    },
    {
        "name": "compute_reliability_availability",
        "description": "STUB Week 3. MTBF/MTTR availability, N+1 sizing, downtime cost.",
        "input_schema": {
            "type": "object",
            "properties": {
                "technology_ids": {"type": "array", "items": {"type": "string"}},
                "required_availability_pct": {"type": "number", "default": 98.0},
            },
            "required": ["technology_ids"],
        },
    },
    {
        "name": "lookup_grants",
        "description": "STUB Week 3. UK grant eligibility: IETF Phase 3, H2PBM, ETS free allocations, CCAs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "technology_ids": {"type": "array", "items": {"type": "string"}, "description": "Shortlisted tech IDs"},
                "sector": {"type": "string"},
                "capex_gbp": {"type": "number"},
            },
            "required": ["technology_ids"],
        },
    },
    {
        "name": "lookup_regulations",
        "description": "STUB Week 3. SECR, UK ETS, CBAM, MEES, CCL, IED compliance check.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {"type": "string"},
                "in_uk_ets": {"type": "boolean"},
                "secr_reportable": {"type": "boolean"},
                "cbam_exposed": {"type": "boolean"},
            },
            "required": ["sector"],
        },
    },
    {
        "name": "retrieve_reference_docs",
        "description": (
            "Vector search over the reference corpus (DEFRA factors, UK regulation, "
            "CIBSE/EHPA standards, IETF case studies, manufacturer datasheets, textbooks). "
            "Use to ground numerical claims in cited sources before asserting them. "
            "Returns top-K matching chunks with doc_id, section, page, similarity score, "
            "snippet, and source URL. Prefer narrow, technically-specific queries "
            "(e.g. 'DEFRA 2025 natural gas combustion factor', not 'emission factors'). "
            "Multiple narrow queries beat one broad one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
                "source_type_filter": {"type": "string", "enum": ["standard", "regulation", "case_study", "datasheet", "textbook"]},
                "sector": {"type": "string", "enum": ["food_and_drink"]},
            },
            "required": ["query"],
        },
    },
    {
        "name": "validate_pathway",
        "description": "STUB Week 4. Energy + carbon conservation, thermo feasibility, regulatory compliance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario_id": {"type": "string", "description": "Pathway scenario to validate"},
                "checks": {"type": "array", "items": {"type": "string"}, "description": "e.g. ['energy_balance', 'carbon_conservation', 'capex_within_budget']"},
            },
            "required": ["scenario_id"],
        },
    },
    {
        "name": "render_report",
        "description": (
            "Render the 11-section pathway markdown deliverable from accumulated "
            "engine outputs (parse_energy_profile, compute_baseline_carbon, "
            "screen_technologies, simulate_site_dispatch). Modules not yet "
            "implemented appear as ROADMAP placeholders. Output is written to "
            "decarb/runs/<site_id>_<timestamp>.md. Returns the file path and "
            "summary statistics. Call this LAST, after all engine modules above "
            "have been invoked at least once for this site."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["markdown", "pdf"], "default": "markdown"},
                "include_appendices": {"type": "boolean", "default": True},
            },
            "required": [],
        },
    },
]


TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "calculate_hp_cycle": calculate_hp_cycle,
    "compute_baseline_carbon": compute_baseline_carbon,
    "simulate_site_dispatch": simulate_site_dispatch,
    "compute_pinch_analysis": compute_pinch_analysis,
    "optimise_investment_pathway": optimise_investment_pathway,
    "monte_carlo_uncertainty": monte_carlo_uncertainty,
    "compute_safety_constraints": compute_safety_constraints,
    "assess_grid_connection": assess_grid_connection,
    "compute_reliability_availability": compute_reliability_availability,
    "lookup_grants": lookup_grants,
    "lookup_regulations": lookup_regulations,
    "retrieve_reference_docs": retrieve_reference_docs,
    "validate_pathway": validate_pathway,
    "render_report": render_report,
}


@dataclass
class ToolCallRecord:
    sequence: int
    tool_name: str
    inputs: dict[str, Any]
    outputs: dict[str, Any] | None
    duration_ms: int
    error: str | None = None


def dispatch(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call. Raises clearly on unknown tools."""
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise ValueError(f"Unknown tool: {tool_name}")
    return handler(**tool_input)
