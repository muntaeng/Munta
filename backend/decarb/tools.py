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
from decarb.engine.pathway import optimise_investment_pathway as _optimise_investment_pathway
from decarb.engine.uncertainty import monte_carlo_uncertainty as _monte_carlo_uncertainty
from decarb.engine.validate import validate_pathway as _validate_pathway
from decarb.engine.dispatch import DEFAULT_MARKET_SIGNALS
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
    """v0 brute-force pathway enumerator. Reads site_brief, screening,
    energy_profile from accumulated site_context (the agent has run
    parse_energy_profile + screen_technologies before this point); the
    LLM-facing tool surface is therefore lean. Returns three named
    pathways + Pareto frontier (compact view; full payload retained in
    site_context.engine_results for the renderer)."""
    site_brief = _site_context.get("site_brief")
    bundle = _site_context.get("engine_results") or {}
    energy_profile = bundle.get("parse_energy_profile") or _site_context.get("energy_profile")
    screening = bundle.get("screen_technologies") or _site_context.get("screening")
    if not site_brief or not energy_profile or not screening:
        return {
            "error": (
                "optimise_investment_pathway needs site_brief, "
                "parse_energy_profile and screen_technologies in site "
                "context — run those tools first."
            )
        }
    full = _optimise_investment_pathway(
        site_brief=site_brief,
        screening=screening,
        energy_profile=energy_profile,
        base_year=int(kwargs.get("base_year", 2026)),
        horizon_years=kwargs.get("horizon_years"),
        discount_rate=kwargs.get("discount_rate"),
    )
    _record_engine_output("optimise_investment_pathway", full)
    # Compact LLM-facing summary
    pathways = full.get("pathways") or {}
    return {
        "candidate_count": full.get("candidate_count"),
        "evaluated_count": full.get("evaluated_count"),
        "pareto_count": len(full.get("pareto_frontier") or []),
        "pathways": {
            name: ({
                "capex_total_gbp": pw.get("capex_total_gbp"),
                "npv_gbp": pw.get("npv_gbp"),
                "irr": pw.get("irr"),
                "simple_payback_years": pw.get("simple_payback_years"),
                "year_15_reduction_pct": pw.get("year_15_reduction_pct"),
                "cumulative_carbon_abated_t_co2e": pw.get("cumulative_carbon_abated_t_co2e"),
                "requires_grid_decision": pw.get("requires_grid_decision"),
                "actions": [
                    {"year_index": a["year_index"],
                     "tech_kind": a["tech_kind"],
                     "capacity": a["capacity"],
                     "capacity_unit": a["capacity_unit"],
                     "capex_gbp": a["capex_gbp"]}
                    for a in (pw.get("actions") or [])
                ],
            } if pw else None)
            for name, pw in pathways.items()
        },
        "warning_codes": [w.get("code") for w in full.get("warnings", [])],
    }


def monte_carlo_uncertainty(**kwargs: Any) -> dict[str, Any]:
    """v0 Monte Carlo over a deterministic pathway. Pulls the pathway and
    deterministic-baseline arrays from the accumulated site_context (the
    agent has run optimise_investment_pathway first), runs the closed-form
    LHS + Iman-Conover copula + Sobol + Morris pipeline, and stashes the
    full result on engine_results so the renderer can pick it up.

    LLM-facing return is compact (key risk metrics + Sobol top-3); the full
    NPV sample array stays inside engine_results."""
    pw_full = (_site_context.get("engine_results") or {}).get(
        "optimise_investment_pathway"
    )
    if not pw_full:
        return {
            "error": (
                "monte_carlo_uncertainty needs optimise_investment_pathway "
                "in engine_results — run optimise_investment_pathway first."
            )
        }
    pw_name = kwargs.get("pathway_name", "balanced")
    n_trials = int(kwargs.get("n_trials", 1000))
    seed = int(kwargs.get("seed", 42))
    uncertain_inputs = kwargs.get("uncertain_inputs")
    carbon_target = kwargs.get("carbon_target_trajectory")

    # Baseline arrays may have been pre-computed by the agent driver and
    # cached in site_context; otherwise compute them on the fly using a
    # gas-only dispatch over the planning horizon.
    baseline_cost = _site_context.get("baseline_annual_cost_gbp_per_year")
    baseline_carbon = _site_context.get("baseline_annual_carbon_t_per_year")
    if baseline_cost is None or baseline_carbon is None:
        baseline_cost, baseline_carbon = _gas_only_baseline_arrays(pw_full)
        _site_context["baseline_annual_cost_gbp_per_year"] = baseline_cost
        _site_context["baseline_annual_carbon_t_per_year"] = baseline_carbon

    full = _monte_carlo_uncertainty(
        pw_full,
        pathway_name=pw_name,
        baseline_annual_cost_gbp_per_year=baseline_cost,
        baseline_annual_carbon_t_per_year=baseline_carbon,
        uncertain_inputs=uncertain_inputs,
        n_trials=n_trials,
        seed=seed,
        carbon_target_trajectory=carbon_target,
    )
    _record_engine_output("monte_carlo_uncertainty", full)
    npv = full["npv_distribution"]
    return {
        "pathway_name": pw_name,
        "n_trials": full["n_trials"],
        "seed": full["seed"],
        "npv_p10_gbp": npv["p10_gbp"],
        "npv_p50_gbp": npv["p50_gbp"],
        "npv_p90_gbp": npv["p90_gbp"],
        "npv_mean_gbp": npv["mean_gbp"],
        "prob_npv_positive": full["prob_npv_positive"],
        "prob_carbon_target_met": full["prob_carbon_target_met"],
        "var_95_npv_gbp": full["var_95_npv_gbp"],
        "cvar_95_npv_gbp": full["cvar_95_npv_gbp"],
        "sobol_top_total_order": full["sobol"]["top_total_order"][:3],
        "correlation_check_ok": full["correlation_check"]["ok"],
        "warning_codes": [w.get("code") for w in full.get("warnings", [])],
    }


def _gas_only_baseline_arrays(pw_full: dict[str, Any]) -> tuple[list[float], list[float]]:
    """Fallback: compute the gas-only baseline arrays using simulate_site_dispatch
    on a synthetic gas-only stack. Used when the caller hasn't pre-cached them."""
    horizon = int(pw_full.get("planning_horizon_years", 15))
    base_year = int(pw_full.get("base_year", 2026))
    energy_profile = (_site_context.get("engine_results") or {}).get("parse_energy_profile") \
        or _site_context.get("energy_profile")
    site_brief = _site_context.get("site_brief") or {}
    if not energy_profile:
        return [0.0] * horizon, [0.0] * horizon
    gas_kw = 0.0
    for b in site_brief.get("existing_plant", {}).get("boilers", []):
        if "gas" in str(b.get("type", "")).lower():
            gas_kw += float(b.get("capacity_mw", 0.0)) * 1000.0
    gas_kw = max(gas_kw, 10_000.0)
    bcost: list[float] = []
    bcarb: list[float] = []
    for y in range(horizon):
        d = _simulate_site_dispatch(
            energy_profile=energy_profile,
            technology_stack=[{
                "type": "gas_boiler", "id": "baseline_gas",
                "capacity_kw": gas_kw, "efficiency": 0.85,
                "serves_end_uses": ["steam", "hot_water"],
            }],
            market_signals=DEFAULT_MARKET_SIGNALS,
            dispatch_policy="merit_order",
            year=base_year + y,
        )
        bcost.append(float(d.get("annual_summary", {}).get("total_energy_cost_gbp", 0.0)))
        bcarb.append(float(d.get("carbon_summary", {}).get("total_t_co2e", 0.0)))
    return bcost, bcarb


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
    """Cross-module consistency + arithmetic validator. Reads the full
    engine bundle from accumulated site context, runs every check in
    decarb.engine.validate, persists the full result on
    site_context.engine_results, and returns a compact LLM-facing
    summary. The agent must call this after every other engine tool
    and before render_report; render_report is gated on
    ``passed=True``."""
    site_brief = _site_context.get("site_brief")
    bundle = _site_context.get("engine_results") or {}
    energy_profile = bundle.get("parse_energy_profile") or _site_context.get("energy_profile")
    screening = bundle.get("screen_technologies") or _site_context.get("screening")
    baseline_carbon = bundle.get("compute_baseline_carbon")
    dispatch = bundle.get("simulate_site_dispatch")
    pathway = bundle.get("optimise_investment_pathway")
    monte_carlo = bundle.get("monte_carlo_uncertainty")
    missing = [
        name for name, val in (
            ("site_brief", site_brief),
            ("parse_energy_profile", energy_profile),
            ("compute_baseline_carbon", baseline_carbon),
            ("screen_technologies", screening),
            ("simulate_site_dispatch", dispatch),
            ("optimise_investment_pathway", pathway),
        )
        if not val
    ]
    if missing:
        return {
            "error": (
                "validate_pathway cannot run — missing required engine outputs: "
                + ", ".join(missing) + ". Call those tools first."
            )
        }
    full = _validate_pathway(
        site_brief=site_brief,
        energy_profile=energy_profile,
        screening=screening,
        baseline_carbon=baseline_carbon,
        dispatch=dispatch,
        pathway=pathway,
        monte_carlo=monte_carlo,
    )
    _record_engine_output("validate_pathway", full)
    failed = [
        {"check_id": c["check_id"], "severity": c["severity"],
         "message": c["message"]}
        for c in full["checks"] if not c["passed"]
    ]
    return {
        "passed": full["passed"],
        "summary": full["summary"],
        "failed_checks": failed,
        "standards_cited": full["standards_cited"],
    }


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

    # Phase 5 gate: refuse to render if validate_pathway hasn't passed.
    validate_result = bundle.get("validate_pathway")
    if not validate_result or not validate_result.get("passed"):
        if not validate_result:
            msg = (
                "render_report blocked: validate_pathway has not been "
                "called yet. Call validate_pathway first and address any "
                "failed checks before requesting render_report."
            )
        else:
            failed = [
                f"{c['check_id']} ({c['severity']}): {c['message']}"
                for c in validate_result.get("checks", [])
                if not c.get("passed") and c.get("severity") == "error"
            ]
            msg = (
                "render_report blocked: validate_pathway returned "
                "passed=false. Address the following failed error-severity "
                "checks before re-requesting render_report:\n- "
                + "\n- ".join(failed)
            )
        return {"error": msg}
    parse_result = bundle.get("parse_energy_profile")
    carbon_result = bundle.get("compute_baseline_carbon")
    screen_result = bundle.get("screen_technologies")
    dispatch_result = bundle.get("simulate_site_dispatch")
    # pathway_result is optional — when the agent has called
    # optimise_investment_pathway before render_report, §4 renders the
    # full pathway analysis; otherwise §4 falls back to the ROADMAP block
    # plus the dispatch-only summary.
    pathway_result = bundle.get("optimise_investment_pathway")

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

    uncertainty_result = bundle.get("monte_carlo_uncertainty")
    result = _render_report(
        site_brief=site_brief,
        parse_result=parse_result,
        carbon_result=carbon_result,
        screen_result=screen_result,
        dispatch_result=dispatch_result,
        pathway_result=pathway_result,
        uncertainty_result=uncertainty_result,
        validate_result=validate_result,
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
        "description": (
            "v0 brute-force enumeration of decarbonisation pathways over a "
            "planning horizon. Reads site_brief, screening shortlist + "
            "pending-grid set, and the parsed energy profile from accumulated "
            "site context (no payloads passed by the agent). For every "
            "candidate it runs simulate_site_dispatch year-by-year and "
            "computes NPV, IRR, simple/discounted payback, LCOH, and year-15 "
            "carbon reduction. Returns three named pathways (Conservative / "
            "Balanced / Aggressive) plus the cost-vs-carbon Pareto frontier. "
            "Capex envelope from site.constraints.capex_budget_gbp is a hard "
            "filter. Equipment ageing not modelled in v0 (declared in warnings)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "base_year": {"type": "integer", "default": 2026, "description": "Calendar year of planning year 0."},
                "horizon_years": {"type": "integer", "description": "Planning horizon in years; defaults to site.constraints.planning_horizon_years."},
                "discount_rate": {"type": "number", "description": "Real discount rate; defaults to site.constraints.discount_rate_real."},
            },
            "required": [],
        },
    },
    {
        "name": "monte_carlo_uncertainty",
        "description": (
            "v0 Monte Carlo on a deterministic optimise_investment_pathway "
            "result. Three independent sampling passes: (1) Latin Hypercube "
            "+ Iman-Conover Gaussian-copula correlation (default ρ=0.6 "
            "between gas and electricity) → main NPV / carbon distribution "
            "with P10/P50/P90, VaR_95, CVaR_95, prob_npv_positive, "
            "prob_carbon_target_met; (2) Saltelli sample → Sobol first- "
            "and total-order sensitivity indices on NPV; (3) Morris "
            "elementary effects for screening sensitivity. Inner loop is "
            "a closed-form perturbation (no per-trial dispatch) — see "
            "engine/uncertainty.py docstring for limitations. Reads the "
            "deterministic pathway from accumulated site context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pathway_name": {
                    "type": "string",
                    "enum": ["conservative", "balanced", "aggressive"],
                    "default": "balanced",
                    "description": "Which named pathway from optimise_investment_pathway to stress-test.",
                },
                "n_trials": {
                    "type": "integer", "default": 1000,
                    "description": "LHS sample size for the main NPV / carbon distribution.",
                },
                "seed": {
                    "type": "integer", "default": 42,
                    "description": "Numpy RNG seed; same seed → bit-identical output.",
                },
                "uncertain_inputs": {
                    "type": "object",
                    "description": (
                        "Optional override of the default uncertain-input schedule. "
                        "Each entry: {name: {kind: 'triangular'|'bernoulli', "
                        "params: [...], comment: '...'}}. Defaults: "
                        "electricity_price, gas_price, hp_capex_multiplier, "
                        "grid_carbon_intensity, ietf_grant_outcome, demand_growth."
                    ),
                },
                "carbon_target_trajectory": {
                    "type": "array", "items": {"type": "number"},
                    "description": (
                        "Per-year tCO2e ceiling for prob_carbon_target_met. "
                        "Default: linear glide from baseline year-0 carbon "
                        "to zero at horizon-end (UK Net Zero proxy)."
                    ),
                },
            },
            "required": [],
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
        "description": (
            "Cross-module consistency and arithmetic check over the full "
            "engine bundle. Call this AFTER all other tool calls and "
            "BEFORE render_report. Returns `passed: bool` plus a "
            "structured failed-check list. If `passed=false`, fix the "
            "underlying engine output; do NOT proceed to render."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
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
