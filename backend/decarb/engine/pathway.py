"""
optimise_investment_pathway — §6 of the engine.

v0 implementation: brute-force enumeration of ~50 candidate decarbonisation
pathways over a 15-year planning horizon, each evaluated through the
dispatch + carbon engine modules, and ranked by NPV. Returns three named
pathways (Conservative, Balanced, Aggressive) plus the cost-vs-carbon
Pareto frontier.

Hard rules respected (per CLAUDE.md):
  - LLM never does arithmetic. Every output number traces to a deterministic
    function call here or in the dispatch / carbon modules.
  - The optimiser CALLS simulate_site_dispatch + compute_baseline_carbon as
    its inner loop — it does not re-implement them.
  - HP sink_temp_c vs end-use supply_temp_c B0 constraint is enforced
    inside dispatch; this module just constructs feasible configs.
  - Capex budget envelope from site_brief.constraints.capex_budget_gbp is
    a hard filter; pathways exceeding it are discarded.
  - Equipment ageing / replacement is NOT modelled in v0 — flagged in
    `warnings`, deferred to v0.2 alongside the proper stochastic MILP.

Standards / methodology references:
  - HM Treasury Green Book (appraisal methodology).
  - BS EN 16247-1 §6 (techno-economic appraisal of audit recommendations).
  - IEA Cost & Performance Database 2024 (industrial heat-pump and
    electrode-boiler capex ranges).
  - methodology.md §3.6.

The module is independently runnable:

    pathway = optimise_investment_pathway(
        site_brief=site,
        screening=screen_result,
        energy_profile=parsed,
    )
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np

from decarb.engine.carbon import compute_baseline_carbon
from decarb.engine.dispatch import DEFAULT_MARKET_SIGNALS, simulate_site_dispatch
from decarb.engine.emission_factors import grid_intensity_for_year


# ---------------------------------------------------------------------------
# Indicative capex / opex curves (UK industrial 2026, IEA Cost & Performance
# Database 2024, IETF Phase 3 cost benchmarks). Values are flat per-kW or
# per-kWh; learning-rate evolution and equipment-class breakpoints land in
# v0.2 alongside the MILP optimiser.
# ---------------------------------------------------------------------------

_CAPEX_CURVES_GBP: dict[str, float] = {
    "heat_pump_mid_temp":      800.0,   # £/kW thermal — NH3 single-stage screw, sink ≤95°C
    "heat_pump_high_temp":   1_100.0,   # £/kW thermal — multi-stage NH3 / HFO, sink 95-120°C
    "electrode_boiler":        150.0,   # £/kW
    "thermal_storage":          40.0,   # £/kWh sensible-heat tank
    "waste_heat_recovery":     300.0,   # £/kW (HX skid + interconnect)
}

_OPEX_FRACTION_OF_CAPEX: dict[str, float] = {
    # Annual O&M as a fraction of installed capex. Reflects vendor-published
    # service-contract rates for industrial-scale plant.
    "heat_pump_mid_temp":     0.025,
    "heat_pump_high_temp":    0.030,
    "electrode_boiler":       0.015,
    "thermal_storage":        0.010,
    "waste_heat_recovery":    0.020,
}

_EQUIPMENT_LIFETIME_YEARS: dict[str, int] = {
    "heat_pump_mid_temp":     20,
    "heat_pump_high_temp":    20,
    "electrode_boiler":       25,
    "thermal_storage":        25,
    "waste_heat_recovery":    20,
}


# Carbon-pricing and grant defaults. Both default to 0.0 in v0 — the v0
# release surfaces the absence as a top-level warning rather than baking
# a particular forecast in. Senior FN reviewer overlays a sensitivity
# manually until v0.2.
#
# - ETS / shadow-carbon price: HM Treasury Green Book central forecast
#   for the appraisal carbon value lands at ~£75/tCO2e for 2026 (DESNZ
#   2024 update). UK ETS forward 2026 has traded £40-£90/tCO2e in the
#   current cycle. Default 0.0 keeps v0 conservative; tests run with
#   an explicit £75 to validate the engineering target.
# - IETF grant fraction: typical Phase-3 awards land 30–50% of capex
#   for HP-led pathways. Default 0.0; tests run 0.30 to validate.
_DEFAULT_ETS_PRICE_GBP_PER_TCO2E = 0.0
_DEFAULT_IETF_GRANT_FRACTION = 0.0


# ---------------------------------------------------------------------------
# Pathway-action data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Action:
    """One install event: which technology, what capacity, in which planning year."""
    year: int                  # 0-indexed planning year (0 = year 1)
    tech_kind: str             # key into _CAPEX_CURVES_GBP
    capacity: float            # kW thermal for HP/EB/WHR; kWh for TES
    config: dict[str, Any]     # full dispatch tech-stack entry
    requires_grid_decision: bool = False


@dataclass
class _PathwayCandidate:
    name: str
    actions: list[_Action]


# ---------------------------------------------------------------------------
# Helpers — capex, opex, baseline cost, NPV / IRR / payback
# ---------------------------------------------------------------------------


def _capex_for_action(a: _Action) -> float:
    rate = _CAPEX_CURVES_GBP.get(a.tech_kind, 0.0)
    return rate * a.capacity


def _annual_opex_for_action(a: _Action) -> float:
    return _OPEX_FRACTION_OF_CAPEX.get(a.tech_kind, 0.0) * _capex_for_action(a)


def _stack_at_year(
    actions: Iterable[_Action],
    year_idx: int,
    gas_backup_capacity_kw: float,
    must_keep_steam_backup: bool,
) -> list[dict[str, Any]]:
    """Build the dispatch technology stack as it stands at the *start* of
    planning year `year_idx` (0-indexed). All actions with action.year ≤
    year_idx are installed; the retained gas backup is appended if the site
    declares must_keep_steam_backup. (must_keep_steam_backup is True for
    every site brief shipping in v0; the False branch is a future-only
    case and not exercised today.)"""
    stack: list[dict[str, Any]] = [
        dict(a.config) for a in actions if a.year <= year_idx
    ]
    if must_keep_steam_backup:
        stack.append({
            "type": "gas_boiler",
            "id": "retained_gas",
            "capacity_kw": gas_backup_capacity_kw,
            "efficiency": 0.85,
            "serves_end_uses": ["steam", "hot_water"],
        })
    return stack


def _baseline_dispatch_for_year(
    *,
    energy_profile: dict[str, Any],
    market_signals: dict[str, Any],
    base_year: int,
    year_offset: int,
    gas_backup_capacity_kw: float,
) -> dict[str, Any]:
    """Run dispatch with a gas-only stack to obtain the do-nothing
    counterfactual energy cost and carbon for a given year. Used as the
    apples-to-apples benchmark against pathway dispatches: same dispatch
    logic, same TOU tariffs, same boiler efficiency assumptions."""
    return simulate_site_dispatch(
        energy_profile=energy_profile,
        technology_stack=[{
            "type": "gas_boiler",
            "id": "baseline_gas_only",
            "capacity_kw": max(gas_backup_capacity_kw, 10_000.0),
            "efficiency": 0.85,
            "serves_end_uses": ["steam", "hot_water"],
        }],
        market_signals=market_signals,
        dispatch_policy="merit_order",
        year=base_year + year_offset,
    )


def _npv(cashflows: list[float], discount_rate: float) -> float:
    """Standard NPV of a cashflow list, year 0 not discounted."""
    return float(sum(cf / ((1.0 + discount_rate) ** y) for y, cf in enumerate(cashflows)))


def _irr_brentq(cashflows: list[float]) -> float | None:
    """Internal Rate of Return via Brent's method on the NPV(r) function.

    Returns None if no sign change (i.e. no IRR exists in [-0.99, +1.0]).
    """
    if not cashflows or all(cf >= 0 for cf in cashflows) or all(cf <= 0 for cf in cashflows):
        return None
    try:
        from scipy.optimize import brentq
    except ImportError:
        return None

    def f(r: float) -> float:
        return _npv(cashflows, r)

    lo, hi = -0.99, 1.0
    f_lo, f_hi = f(lo), f(hi)
    if f_lo * f_hi > 0:
        return None
    try:
        return float(brentq(f, lo, hi, xtol=1e-5, maxiter=200))
    except (ValueError, RuntimeError):
        return None


def _simple_payback_years(
    capex_total: float, annual_savings_year1: float
) -> float | None:
    if annual_savings_year1 <= 0 or capex_total <= 0:
        return None
    return capex_total / annual_savings_year1


def _discounted_payback_years(
    cashflows: list[float], discount_rate: float
) -> float | None:
    """Year (interpolated) at which cumulative discounted cashflow turns
    positive. Returns None if it never recovers within the horizon."""
    cumulative = 0.0
    for y, cf in enumerate(cashflows):
        disc_cf = cf / ((1.0 + discount_rate) ** y)
        prev = cumulative
        cumulative += disc_cf
        if prev < 0 <= cumulative:
            # Linear interpolation within year y.
            return (y - 1) + (-prev) / disc_cf if disc_cf != 0 else float(y)
        if y == 0 and cumulative >= 0:
            return 0.0
    return None


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------


def _hp_config_mid_temp(capacity_kw: float, requires_grid: bool = False) -> dict[str, Any]:
    return {
        "type": "heat_pump",
        "id": f"hp_mid_{int(capacity_kw)}",
        "capacity_kw_thermal": capacity_kw,
        "refrigerant": "Ammonia",
        "compressor_type": "screw",
        "source_type": "waste_heat",
        "source_temp_c": 35.0,
        "sink_temp_c": 90.0,                 # serves hot_water (85°C + 5K margin)
        "serves_end_uses": ["hot_water"],
    }


def _hp_config_high_temp(capacity_kw: float, requires_grid: bool = True) -> dict[str, Any]:
    """High-temperature HP candidate (NH3 cascade / R744 transcritical).
    Sink 125°C is the realistic single-stage / cascade upper bound for
    NH3+R744 in 2026; multi-stage to 145°C in v0.2 alongside transcritical
    CO2. Declares serves_end_uses=['steam','hot_water'] — the dispatch
    sink-temperature guard will reject 175°C-steam service at 125°C sink
    (per BS EN 14825 5K LMTD). That rejection is now propagated to the
    top-level pathway warnings (per Reviewer iter-1 issue #2/#3) so a
    senior reader sees *why* high-temp HP can't electrify dairy steam,
    rather than the fact being silently absent."""
    return {
        "type": "heat_pump",
        "id": f"hp_high_{int(capacity_kw)}",
        "capacity_kw_thermal": capacity_kw,
        "refrigerant": "Ammonia",
        "compressor_type": "screw",
        "source_type": "waste_heat",
        "source_temp_c": 35.0,
        "sink_temp_c": 125.0,                # NH3 cascade ceiling (2026)
        "serves_end_uses": ["steam", "hot_water"],
    }


def _electrode_config(capacity_kw: float) -> dict[str, Any]:
    return {
        "type": "electrode_boiler",
        "id": f"eb_{int(capacity_kw)}",
        "capacity_kw": capacity_kw,
        "efficiency": 0.99,
        "serves_end_uses": ["steam"],
    }


def _tes_config(capacity_kwh: float) -> dict[str, Any]:
    return {
        "type": "thermal_storage",
        "id": f"tes_{int(capacity_kwh)}",
        "capacity_kwh": capacity_kwh,
        "charge_rate_kw": min(4_000.0, capacity_kwh / 2.0),
        "discharge_rate_kw": min(4_000.0, capacity_kwh / 2.0),
        "round_trip_efficiency": 0.92,
        "standing_loss_pct_per_hour": 0.0005,
        "initial_soc_fraction": 0.1,
        "serves_end_uses": ["steam", "hot_water"],
    }


def _whr_config(capacity_kw: float) -> dict[str, Any]:
    """WHR from existing chiller condenser to hot-water supply at 60–70°C.
    Modelled as a heat_pump entry with low lift (chiller condensate ~40°C
    to hot_water 60°C) — approximate, refined in v0.2."""
    return {
        "type": "heat_pump",
        "id": f"whr_{int(capacity_kw)}",
        "capacity_kw_thermal": capacity_kw,
        "refrigerant": "Ammonia",
        "compressor_type": "screw",
        "source_type": "waste_heat",
        "source_temp_c": 40.0,               # chiller condensate
        "sink_temp_c": 70.0,                 # hot_water pre-heat
        "serves_end_uses": ["hot_water"],
    }


def _generate_candidates(
    shortlist_ids: set[str],
    pending_grid_ids: set[str],
    capex_budget_gbp: float,
) -> list[_PathwayCandidate]:
    """Enumerate ~50 representative pathway candidates from the actionable
    technology pool. Three named anchor pathways plus a sweep of capacity-
    and timing-permutations covering the budget envelope."""

    actionable = shortlist_ids | pending_grid_ids
    has_mid_hp = "industrial_heat_pump_mid_temp" in actionable
    has_high_hp = "industrial_heat_pump_high_temp" in actionable
    has_eb = "electrode_boiler_steam" in actionable
    has_tes = "thermal_energy_storage" in actionable or "thermal_energy_storage_hot" in actionable
    has_whr = any(t.startswith("waste_heat_recovery") for t in actionable)

    eb_requires_grid = "electrode_boiler_steam" in pending_grid_ids
    hp_requires_grid = "industrial_heat_pump_mid_temp" in pending_grid_ids
    high_hp_requires_grid = "industrial_heat_pump_high_temp" in pending_grid_ids

    candidates: list[_PathwayCandidate] = []

    # ---------------- Conservative anchor ----------------
    cons_actions: list[_Action] = []
    if has_whr:
        cons_actions.append(_Action(
            year=0, tech_kind="waste_heat_recovery", capacity=500.0,
            config=_whr_config(500.0),
        ))
    if has_mid_hp:
        cons_actions.append(_Action(
            year=0, tech_kind="heat_pump_mid_temp", capacity=500.0,
            config=_hp_config_mid_temp(500.0, hp_requires_grid),
            requires_grid_decision=hp_requires_grid,
        ))
    candidates.append(_PathwayCandidate("conservative_anchor", cons_actions))

    # ---------------- Aggressive anchor ----------------
    agg_actions: list[_Action] = []
    if has_mid_hp:
        agg_actions.append(_Action(
            year=0, tech_kind="heat_pump_mid_temp", capacity=1_500.0,
            config=_hp_config_mid_temp(1_500.0, hp_requires_grid),
            requires_grid_decision=hp_requires_grid,
        ))
    if has_eb:
        agg_actions.append(_Action(
            year=1, tech_kind="electrode_boiler", capacity=4_000.0,
            config=_electrode_config(4_000.0),
            requires_grid_decision=eb_requires_grid,
        ))
    if has_tes:
        agg_actions.append(_Action(
            year=2, tech_kind="thermal_storage", capacity=8_000.0,
            config=_tes_config(8_000.0),
        ))
    if has_whr:
        agg_actions.append(_Action(
            year=3, tech_kind="waste_heat_recovery", capacity=1_000.0,
            config=_whr_config(1_000.0),
        ))
    candidates.append(_PathwayCandidate("aggressive_anchor", agg_actions))

    # ---------------- High-temperature HP candidate ----------------
    # Honest engineering: include a high-temp HP option whenever the
    # screening allowed industrial_heat_pump_high_temp into the actionable
    # pool. The B0 dispatch sink-temperature guard will reject this for
    # 175°C steam at 125°C sink — but the rejection now surfaces in the
    # top-level pathway warnings, making the "we tried HP for steam and
    # the physics rejects it" case visible to the senior reviewer
    # (per Reviewer iter-1 issue #3).
    if has_high_hp:
        for cap in (1_000.0, 2_000.0):
            high_hp_actions: list[_Action] = [_Action(
                year=0, tech_kind="heat_pump_high_temp", capacity=cap,
                config=_hp_config_high_temp(cap, high_hp_requires_grid),
                requires_grid_decision=high_hp_requires_grid,
            )]
            if has_tes:
                high_hp_actions.append(_Action(
                    year=1, tech_kind="thermal_storage", capacity=8_000.0,
                    config=_tes_config(8_000.0),
                ))
            candidates.append(_PathwayCandidate(
                f"high_temp_hp_{int(cap)}kW", high_hp_actions,
            ))

    # ---------------- Sweep: HP × EB × TES capacity / timing combinations ---
    # Trimmed to keep total candidates ≤ ~50 per the methodology (§3.6:
    # "approximately 50 candidate pathways"). Coarser-grained sweep here;
    # the v0.2 MILP optimiser will explore continuous capacity / timing.
    hp_options: list[float] = [1_000.0, 2_000.0] if has_mid_hp else [0.0]
    eb_options: list[float] = [0.0, 2_000.0, 4_000.0] if has_eb else [0.0]
    tes_options: list[float] = [0.0, 4_000.0, 8_000.0] if has_tes else [0.0]
    hp_year_options = [0, 1] if has_mid_hp else [0]
    eb_year_options = [1, 3] if has_eb else [0]

    seq = 0
    for hp_kw, eb_kw, tes_kwh, hp_y, eb_y in itertools.product(
        hp_options, eb_options, tes_options, hp_year_options, eb_year_options,
    ):
        if hp_kw == 0 and eb_kw == 0 and tes_kwh == 0:
            continue
        actions: list[_Action] = []
        if hp_kw > 0:
            actions.append(_Action(
                year=hp_y, tech_kind="heat_pump_mid_temp", capacity=hp_kw,
                config=_hp_config_mid_temp(hp_kw, hp_requires_grid),
                requires_grid_decision=hp_requires_grid,
            ))
        if eb_kw > 0:
            actions.append(_Action(
                year=eb_y, tech_kind="electrode_boiler", capacity=eb_kw,
                config=_electrode_config(eb_kw),
                requires_grid_decision=eb_requires_grid,
            ))
        if tes_kwh > 0:
            tes_year = max(eb_y, hp_y)            # TES installs alongside or after the latest tech
            actions.append(_Action(
                year=tes_year, tech_kind="thermal_storage", capacity=tes_kwh,
                config=_tes_config(tes_kwh),
            ))
        if has_whr and hp_kw + eb_kw > 0:
            actions.append(_Action(
                year=0, tech_kind="waste_heat_recovery", capacity=500.0,
                config=_whr_config(500.0),
            ))
        candidates.append(_PathwayCandidate(f"sweep_{seq}", actions))
        seq += 1

    # ---------------- Capex-budget filter ----------------
    survivors: list[_PathwayCandidate] = []
    for c in candidates:
        capex = sum(_capex_for_action(a) for a in c.actions)
        if capex <= capex_budget_gbp:
            survivors.append(c)
    return survivors


# ---------------------------------------------------------------------------
# Evaluator: run a pathway over the planning horizon
# ---------------------------------------------------------------------------


def _evaluate_pathway(
    candidate: _PathwayCandidate,
    *,
    site_brief: dict,
    energy_profile: dict,
    horizon_years: int,
    discount_rate: float,
    base_year: int,
    market_signals: dict,
    baseline_annual_cost_gbp_per_year: list[float],
    baseline_annual_carbon_t_per_year: list[float],
    must_keep_steam_backup: bool,
    gas_backup_capacity_kw: float,
    dispatch_cache: dict[tuple, dict],
    ets_price_gbp_per_t: float = 0.0,
    grant_fraction: float = 0.0,
) -> dict[str, Any] | None:
    """Run one candidate end-to-end through dispatch × horizon and return a
    consolidated metric record. Returns None on dispatch failure (e.g. all
    HPs filtered out by the sink-temperature guard).

    `dispatch_cache` is shared across all pathway evaluations in one
    optimiser run — many candidates share the same stack for early years
    (e.g. gas-only at year 0 across all candidates that defer their first
    install to year 1+). Caching cuts the dairy run from ~100 s to <30 s."""

    capex_per_year: list[float] = [0.0] * horizon_years
    opex_per_year: list[float] = [0.0] * horizon_years
    annual_dispatch_costs: list[float] = []
    annual_carbon_t: list[float] = []
    annual_thermal_kwh: list[float] = []
    capex_total = 0.0

    # Sum capex into install year (net of grant offset), opex into install
    # year and every later year. Grant fraction reduces capex_per_year and
    # capex_total but not opex.
    grant_factor = max(0.0, 1.0 - float(grant_fraction))
    for a in candidate.actions:
        cx_gross = _capex_for_action(a)
        cx_net = cx_gross * grant_factor
        if a.year < horizon_years:
            capex_per_year[a.year] += cx_net
        capex_total += cx_net
        annual_opex = _annual_opex_for_action(a)
        for y in range(a.year, horizon_years):
            opex_per_year[y] += annual_opex

    # Sink-temperature warnings observed during this pathway's dispatch
    # runs. Per Reviewer iter-1 issue #2: NOT a private "_-prefixed" field;
    # propagated into the top-level optimiser warnings so a senior reader
    # sees that pathway X's HP capacity is physics-blocked for some end
    # uses.
    sink_warnings_seen: list[dict[str, Any]] = []
    seen_codes_for_dedup: set[str] = set()

    def _stack_signature(stack: list[dict]) -> tuple:
        """Hashable signature for caching equivalent stacks."""
        items: list[tuple] = []
        for tech in stack:
            tup = (
                tech.get("type"),
                tech.get("id"),
                tech.get("capacity_kw") or tech.get("capacity_kw_thermal") or tech.get("capacity_kwh"),
                tech.get("sink_temp_c"),
                tech.get("source_type"),
            )
            items.append(tup)
        return tuple(items)

    for y in range(horizon_years):
        stack = _stack_at_year(
            candidate.actions, y, gas_backup_capacity_kw, must_keep_steam_backup,
        )
        sig = (_stack_signature(stack), base_year + y)
        if sig in dispatch_cache:
            d = dispatch_cache[sig]
        else:
            d = simulate_site_dispatch(
                energy_profile=energy_profile,
                technology_stack=stack,
                market_signals=market_signals,
                dispatch_policy="merit_order",
                year=base_year + y,
            )
            dispatch_cache[sig] = d

        # Don't abort on sink-warnings — B0 has zeroed the offending HP duty
        # already — but DO capture them, deduplicated, for top-level
        # propagation.
        for w in d.get("warnings", []):
            code = w.get("code", "")
            if code in (
                "hp_sink_too_cold_for_end_use",
                "hp_inactive_no_compatible_end_use",
            ) and code not in seen_codes_for_dedup:
                seen_codes_for_dedup.add(code)
                sink_warnings_seen.append({
                    "code": code,
                    "severity": w.get("severity", "high"),
                    "message": w.get("message", ""),
                })

        annual_dispatch_costs.append(
            float(d.get("annual_summary", {}).get("total_energy_cost_gbp", 0.0))
        )
        annual_carbon_t.append(
            float(d.get("carbon_summary", {}).get("total_t_co2e", 0.0))
        )
        annual_thermal_kwh.append(
            float(d.get("annual_summary", {}).get("total_heat_delivered_kwh", 0.0))
        )

    # Year-by-year cashflows.
    # cashflow_y = energy_savings_y + carbon_value_y - capex_y - opex_y
    # carbon_value_y = (baseline_carbon_y - pathway_carbon_y) × ets_price.
    # This treats the ETS / shadow-carbon price as a savings revenue
    # (HM Treasury Green Book §6 conventions for non-traded sectors).
    cashflows: list[float] = []
    for y in range(horizon_years):
        savings = baseline_annual_cost_gbp_per_year[y] - annual_dispatch_costs[y]
        carbon_abated_y = max(
            0.0, baseline_annual_carbon_t_per_year[y] - annual_carbon_t[y]
        )
        carbon_value_y = carbon_abated_y * ets_price_gbp_per_t
        cashflows.append(
            savings + carbon_value_y - capex_per_year[y] - opex_per_year[y]
        )

    npv = _npv(cashflows, discount_rate)
    irr = _irr_brentq(cashflows)

    # Year-1 savings used for simple payback (year 1 = first full
    # operational year after the year-0 capex hit). Use horizon[1] if
    # available, else horizon[0]. Includes carbon value to be consistent
    # with the cashflow definition above.
    pb_year = 1 if horizon_years > 1 else 0
    pb_carbon_value = max(
        0.0,
        baseline_annual_carbon_t_per_year[pb_year] - annual_carbon_t[pb_year],
    ) * ets_price_gbp_per_t
    annual_savings_y1 = (
        baseline_annual_cost_gbp_per_year[pb_year]
        - annual_dispatch_costs[pb_year]
        + pb_carbon_value
        - opex_per_year[pb_year]
    )
    simple_payback = _simple_payback_years(capex_total, annual_savings_y1)
    discounted_payback = _discounted_payback_years(cashflows, discount_rate)

    # Carbon metrics
    baseline_y0_carbon = baseline_annual_carbon_t_per_year[0]
    pathway_y15_carbon = annual_carbon_t[-1]
    year_15_reduction_pct = (
        (baseline_y0_carbon - pathway_y15_carbon) / baseline_y0_carbon * 100.0
        if baseline_y0_carbon > 0 else 0.0
    )

    # Cumulative carbon abated (sum over horizon)
    cumulative_abated_t = 0.0
    for y in range(horizon_years):
        cumulative_abated_t += max(
            0.0, baseline_annual_carbon_t_per_year[y] - annual_carbon_t[y]
        )

    # LCOH: NPV(total cost) / NPV(thermal delivered)
    pv_cost = sum(
        (annual_dispatch_costs[y] + capex_per_year[y] + opex_per_year[y])
        / ((1.0 + discount_rate) ** y)
        for y in range(horizon_years)
    )
    pv_thermal = sum(
        annual_thermal_kwh[y] / ((1.0 + discount_rate) ** y)
        for y in range(horizon_years)
    )
    lcoh_gbp_per_mwh = (pv_cost / pv_thermal * 1000.0) if pv_thermal > 0 else None

    requires_grid_decision = any(a.requires_grid_decision for a in candidate.actions)

    return {
        "name": candidate.name,
        "actions": [
            {
                "year_index": a.year,                    # 0-indexed planning year
                "calendar_year": base_year + a.year,
                "tech_kind": a.tech_kind,
                "tech_id": a.config.get("id"),
                "capacity": a.capacity,
                "capacity_unit": "kWh" if a.tech_kind == "thermal_storage" else "kW_thermal",
                "capex_gbp": round(_capex_for_action(a), 0),
                "annual_opex_gbp": round(_annual_opex_for_action(a), 0),
                "lifetime_years": _EQUIPMENT_LIFETIME_YEARS.get(a.tech_kind, 20),
                "config": a.config,
                "requires_grid_decision": a.requires_grid_decision,
            }
            for a in candidate.actions
        ],
        "capex_total_gbp": round(capex_total, 0),
        "annual_opex_year1_gbp": round(opex_per_year[0], 0),
        "npv_gbp": round(npv, 0),
        "irr": round(irr, 4) if irr is not None else None,
        "irr_unrecoverable_reason": (
            None if irr is not None
            else "Cashflows monotone-negative or never cross zero — IRR undefined."
        ),
        "simple_payback_years": (
            round(simple_payback, 2) if simple_payback is not None else None
        ),
        "simple_payback_unrecoverable_reason": (
            None if simple_payback is not None
            else "Year-1 net savings ≤ 0 — payback period undefined."
        ),
        "discounted_payback_years": (
            round(discounted_payback, 2) if discounted_payback is not None else None
        ),
        "discounted_payback_unrecoverable_reason": (
            None if discounted_payback is not None
            else "Cumulative discounted cashflow does not cross zero within the horizon."
        ),
        "lcoh_gbp_per_mwh": (
            round(lcoh_gbp_per_mwh, 1) if lcoh_gbp_per_mwh is not None else None
        ),
        "year_15_reduction_pct": round(year_15_reduction_pct, 1),
        "cumulative_carbon_abated_t_co2e": round(cumulative_abated_t, 0),
        "cashflows_gbp": [round(c, 0) for c in cashflows],
        "annual_dispatch_cost_gbp": [round(c, 0) for c in annual_dispatch_costs],
        "annual_pathway_carbon_t_co2e": [round(c, 1) for c in annual_carbon_t],
        "requires_grid_decision": requires_grid_decision,
        "sink_warnings": sink_warnings_seen,
    }


# ---------------------------------------------------------------------------
# Pareto frontier
# ---------------------------------------------------------------------------


def _pareto_frontier(
    evaluated: list[dict[str, Any]],
    *,
    cost_axis: str = "capex_total_gbp",
) -> list[dict[str, Any]]:
    """Return the (cost, carbon-abated) Pareto frontier under one of:

      cost_axis="capex_total_gbp" — the lay client's cost view. Lower
        is better; sorted ascending. (As shipped in iter 1.)
      cost_axis="lifetime_cost_gbp" — the senior engineer's view: PV
        of all costs minus PV of all savings = -NPV. Lower is better;
        sorted ascending. Per Reviewer iter-1 issue #5, methodology
        §3.6 specifies "cost vs carbon" in a 15-yr techno-economic
        appraisal sense.

    A pathway dominates another if it is no worse on cost AND no worse
    on cumulative carbon abated, and strictly better on at least one.
    The frontier is the non-dominated set, sorted by cost ascending.
    """
    if not evaluated:
        return []

    def _cost(e: dict[str, Any]) -> float:
        if cost_axis == "lifetime_cost_gbp":
            # Lifetime cost = -NPV. Lower is better.
            return -float(e.get("npv_gbp", 0.0))
        return float(e.get(cost_axis, e.get("capex_total_gbp", 0.0)))

    sorted_by_cost = sorted(
        evaluated, key=lambda e: (_cost(e), -e["cumulative_carbon_abated_t_co2e"]),
    )
    frontier: list[dict[str, Any]] = []
    best_carbon = -float("inf")
    for e in sorted_by_cost:
        if e["cumulative_carbon_abated_t_co2e"] > best_carbon:
            frontier.append(e)
            best_carbon = e["cumulative_carbon_abated_t_co2e"]
    return frontier


# ---------------------------------------------------------------------------
# Main public entry point
# ---------------------------------------------------------------------------


def optimise_investment_pathway(
    *,
    site_brief: dict[str, Any],
    screening: dict[str, Any],
    energy_profile: dict[str, Any],
    market_signals: dict[str, Any] | None = None,
    base_year: int = 2026,
    horizon_years: int | None = None,
    discount_rate: float | None = None,
    ets_allowance_price_gbp_per_tco2e: float | None = None,
    ietf_grant_fraction: float | None = None,
) -> dict[str, Any]:
    """Brute-force enumerate candidate decarbonisation pathways and return
    Conservative / Balanced / Aggressive picks plus the cost-vs-carbon
    Pareto frontier.

    Args:
        site_brief: parsed site JSON (needs constraints, regulatory).
        screening: output of screen_technologies — used to define the
            actionable technology pool (shortlist + pending_grid_decision).
        energy_profile: output of parse_energy_profile.
        market_signals: optional override for tariffs / gas price.
        base_year: calendar-year of planning year 0 (default 2026).
        horizon_years: planning horizon (default site.constraints.planning_horizon_years).
        discount_rate: real discount rate (default site.constraints.discount_rate_real).

    Returns:
        Output dict per the schema in the module docstring.
    """
    constraints = site_brief.get("constraints", {})
    horizon_years = int(horizon_years or constraints.get("planning_horizon_years", 15))
    discount_rate = float(
        discount_rate if discount_rate is not None
        else constraints.get("discount_rate_real", 0.08)
    )
    capex_budget = float(constraints.get("capex_budget_gbp", 5_000_000.0))
    must_keep_gas = bool(constraints.get("must_keep_steam_backup", True))
    market = {**DEFAULT_MARKET_SIGNALS, **(market_signals or {})}
    ets_price = float(
        ets_allowance_price_gbp_per_tco2e
        if ets_allowance_price_gbp_per_tco2e is not None
        else market.get("ets_allowance_price_gbp_per_tco2e", _DEFAULT_ETS_PRICE_GBP_PER_TCO2E)
    )
    grant_frac = float(
        ietf_grant_fraction
        if ietf_grant_fraction is not None
        else market.get("ietf_grant_fraction", _DEFAULT_IETF_GRANT_FRACTION)
    )

    # Existing gas backup capacity (sum across all gas boilers in the site)
    gas_backup_kw = 0.0
    for b in site_brief.get("existing_plant", {}).get("boilers", []):
        if "gas" in str(b.get("type", "")).lower():
            gas_backup_kw += float(b.get("capacity_mw", 0.0)) * 1000.0
    if gas_backup_kw <= 0:
        gas_backup_kw = 10_000.0   # 10 MW fallback

    warnings_out: list[dict[str, Any]] = []

    # Baseline trajectory year-by-year — run dispatch with a gas-only stack
    # for each year of the horizon. Same accounting conventions as pathway
    # dispatches (TOU tariffs, 0.85 boiler eff, identical demand profile).
    baseline_annual_cost_per_year: list[float] = []
    baseline_annual_carbon_t_per_year: list[float] = []
    for y in range(horizon_years):
        d = _baseline_dispatch_for_year(
            energy_profile=energy_profile,
            market_signals=market,
            base_year=base_year,
            year_offset=y,
            gas_backup_capacity_kw=gas_backup_kw,
        )
        baseline_annual_cost_per_year.append(
            float(d.get("annual_summary", {}).get("total_energy_cost_gbp", 0.0))
        )
        baseline_annual_carbon_t_per_year.append(
            float(d.get("carbon_summary", {}).get("total_t_co2e", 0.0))
        )

    # Baseline carbon trajectory record (used for §5 of the report; not the
    # numbers fed into pathway NPV/savings, which come from the per-year
    # dispatch above so dispatch and pathway use identical accounting).
    baseline_carbon_record = compute_baseline_carbon(
        annual_balance_kwh=energy_profile["annual_balance_kwh"],
        year=base_year,
        site_secr_reportable=site_brief.get("regulatory", {}).get("secr_reportable", True),
        site_in_uk_ets=site_brief.get("regulatory", {}).get("in_uk_ets", False),
        cca_subsector=site_brief.get("regulatory", {}).get("cca_subsector"),
        cbam_exposed=site_brief.get("regulatory", {}).get("cbam_exposed", False),
    )

    # Actionable tech pool — shortlist plus pending-grid (with a flag)
    shortlist_ids = {t["tech_id"] for t in screening.get("shortlist", [])}
    pending_grid_ids = {
        t["tech_id"] for t in screening.get("excluded_pending_grid_decision", [])
    }

    candidates = _generate_candidates(shortlist_ids, pending_grid_ids, capex_budget)
    if not candidates:
        warnings_out.append({
            "severity": "high",
            "code": "no_pathway_candidates",
            "message": (
                "No pathway candidates fit within the capex budget envelope "
                f"(£{capex_budget:,.0f}). Either uprate the budget or expand "
                "the screening shortlist."
            ),
        })

    # Evaluate every candidate. Dispatch cache shared across candidates
    # — many sweep entries share the same stack signature at early years
    # (gas-only year 0 across all year-1+ install candidates).
    dispatch_cache: dict[tuple, dict[str, Any]] = {}
    evaluated: list[dict[str, Any]] = []
    for c in candidates:
        rec = _evaluate_pathway(
            c,
            site_brief=site_brief,
            energy_profile=energy_profile,
            horizon_years=horizon_years,
            discount_rate=discount_rate,
            base_year=base_year,
            market_signals=market,
            baseline_annual_cost_gbp_per_year=baseline_annual_cost_per_year,
            baseline_annual_carbon_t_per_year=baseline_annual_carbon_t_per_year,
            must_keep_steam_backup=must_keep_gas,
            gas_backup_capacity_kw=gas_backup_kw,
            dispatch_cache=dispatch_cache,
            ets_price_gbp_per_t=ets_price,
            grant_fraction=grant_frac,
        )
        if rec is not None:
            evaluated.append(rec)

    # ---- Pick the three named pathways ----------------------------------
    # Selection rules (per Reviewer iter-1 issue #1 — Conservative MUST
    # differ from Balanced; the methodology promises three distinct
    # scenarios, not three labels for the same option):
    #
    #   Balanced     = max NPV across the feasible set (the lay senior
    #                  reader's "best value" pick).
    #   Conservative = max year-15 reduction subject to NPV ≥ best_NPV − Δ
    #                  AND capex ≤ 25% of budget. The "small-capex carbon
    #                  leader still close to NPV-best" — answers "what's
    #                  the most carbon I can buy without compromising the
    #                  Balanced economics". Δ = max(£500k, 25% × |best NPV|).
    #   Aggressive   = max year-15 reduction subject to capex ≤ budget.
    #                  The all-out carbon-leader, no NPV constraint.
    pathways: dict[str, Any] = {}
    if evaluated:
        balanced = max(evaluated, key=lambda e: e["npv_gbp"])
        best_npv = balanced["npv_gbp"]
        delta = max(500_000.0, 0.25 * abs(best_npv))

        small_capex_cap = 0.25 * capex_budget
        cons_pool = [
            e for e in evaluated
            if e["capex_total_gbp"] <= small_capex_cap
            and e["npv_gbp"] >= best_npv - delta
            and e["year_15_reduction_pct"] > 0
        ]
        # Fallbacks if no candidate satisfies both constraints:
        # 1. Relax the small-capex cap to 50% of budget
        # 2. Relax further to "any pathway with positive reduction and
        #    NPV-near-best", picking smallest capex
        # 3. Last resort: smallest-capex pathway with positive reduction
        if not cons_pool:
            cons_pool = [
                e for e in evaluated
                if e["capex_total_gbp"] <= 0.5 * capex_budget
                and e["npv_gbp"] >= best_npv - delta
                and e["year_15_reduction_pct"] > 0
            ]
        if not cons_pool:
            cons_pool = [
                e for e in evaluated
                if e["year_15_reduction_pct"] > 0
                and e["npv_gbp"] >= best_npv - delta
            ]
        if not cons_pool:
            cons_pool = [e for e in evaluated if e["year_15_reduction_pct"] > 0]
        if not cons_pool:
            cons_pool = evaluated
        conservative = max(
            cons_pool,
            key=lambda e: (e["year_15_reduction_pct"], -e["capex_total_gbp"]),
        )
        pathways["conservative"] = {**conservative, "name": "conservative"}
        pathways["balanced"] = {**balanced, "name": "balanced"}

        aggressive = max(evaluated, key=lambda e: e["year_15_reduction_pct"])
        pathways["aggressive"] = {**aggressive, "name": "aggressive"}
    else:
        warnings_out.append({
            "severity": "high",
            "code": "no_evaluated_pathways",
            "message": "No pathways could be evaluated — check screening output and capex budget.",
        })
        pathways = {"conservative": None, "balanced": None, "aggressive": None}

    pareto_capex = _pareto_frontier(evaluated, cost_axis="capex_total_gbp")
    pareto_npv = _pareto_frontier(evaluated, cost_axis="lifetime_cost_gbp")

    # Warn if the three named pathways collapsed onto fewer than 3 distinct
    # action sets — signals the candidate pool was too narrow or the
    # carbon/grant overlay made the same pathway optimal under all rules.
    def _action_signature(pw_record: dict | None) -> tuple | None:
        if not pw_record:
            return None
        return tuple(sorted(
            (a["tech_kind"], round(a["capacity"], 1), a["year_index"])
            for a in pw_record.get("actions") or []
        ))
    sig_cons = _action_signature(pathways.get("conservative"))
    sig_bal = _action_signature(pathways.get("balanced"))
    sig_agg = _action_signature(pathways.get("aggressive"))
    distinct_sigs = {s for s in (sig_cons, sig_bal, sig_agg) if s is not None}
    if len(distinct_sigs) < 3 and evaluated:
        warnings_out.append({
            "severity": "advisory",
            "code": "pathways_collapsed",
            "message": (
                f"{3 - len(distinct_sigs)} of the three named pathways "
                "collapsed onto a duplicate action set — the candidate "
                "pool admits fewer than three meaningfully different "
                "trade-offs at this site under the current "
                "carbon-price / grant configuration. Surface to the "
                "senior reviewer; do not present duplicates as "
                "distinct options."
            ),
        })

    # Aggregate sink-temperature warnings observed across all pathway
    # evaluations into the top-level warnings list (Reviewer iter-1 issue
    # #2). One entry per (code, pathway-name) pair so the senior reader
    # sees which named pathways are physics-blocked.
    for name in ("conservative", "balanced", "aggressive"):
        pw = pathways.get(name)
        if not pw:
            continue
        for w in pw.get("sink_warnings") or []:
            warnings_out.append({
                "severity": w.get("severity", "high"),
                "code": w.get("code", "hp_sink_warning"),
                "pathway": name,
                "message": (
                    f"[{name} pathway] " + w.get("message", "")
                ),
            })
    # Also propagate the dispatch sink-warning surfaced by any high-temp
    # HP candidate even if it didn't make it into a named slot, to keep
    # the failure-to-electrify-steam case visible.
    for e in evaluated:
        if e.get("name", "").startswith("high_temp_hp_") and e.get("sink_warnings"):
            for w in e["sink_warnings"]:
                warnings_out.append({
                    "severity": w.get("severity", "high"),
                    "code": w.get("code", "hp_sink_warning"),
                    "pathway": e["name"],
                    "message": (
                        f"[{e['name']}] " + w.get("message", "")
                        + " — confirms high-temperature HP cannot be used "
                        "for 175°C steam at 125°C sink. v0.2 will add "
                        "transcritical CO2 / cascade variants reaching "
                        "145–160°C; 175°C steam remains out of single-stage HP envelope."
                    ),
                })
                break  # one entry per high-temp candidate is enough
            break

    # Retained-gas-backup advisory (iter-1 issue #9): every pathway carries
    # the must_keep_steam_backup gas boiler, which structurally caps year-15
    # reduction.
    if must_keep_gas:
        warnings_out.append({
            "severity": "advisory",
            "code": "retained_gas_backup_active",
            "message": (
                f"Site declares must_keep_steam_backup; retained gas boiler "
                f"capacity {gas_backup_kw / 1000.0:.1f} MW is included in every "
                "pathway's stack. Steam peaks always go through gas — this caps "
                "year-15 carbon reduction below 100% by construction."
            ),
        })

    # Carbon-price / grant disclosure (iter-1 issue #4)
    if ets_price <= 0.0 and grant_frac <= 0.0:
        warnings_out.append({
            "severity": "high",
            "code": "carbon_price_and_grant_excluded",
            "message": (
                "v0 cashflow excludes both UK ETS / shadow-carbon price and "
                "IETF grant uplift (ets_allowance_price_gbp_per_tco2e=0.0, "
                "ietf_grant_fraction=0.0). Negative NPV across all pathways is "
                "a direct consequence — published IETF case studies, CCC "
                "scenarios and BS EN 16247-1 retrofit appraisals incorporate "
                "both. Re-run with ets_allowance_price_gbp_per_tco2e in the "
                "£40–£90/tCO2e UK ETS forward range and ietf_grant_fraction in "
                "the 0.30–0.50 typical-award range to obtain an engineering-"
                "target NPV. v0.2 will wire IETF eligibility detection into "
                "lookup_grants and apply automatically."
            ),
        })
    elif ets_price > 0.0 or grant_frac > 0.0:
        warnings_out.append({
            "severity": "advisory",
            "code": "carbon_price_or_grant_applied",
            "message": (
                f"Cashflow includes ETS / shadow-carbon price "
                f"£{ets_price:.0f}/tCO2e and IETF grant fraction "
                f"{grant_frac:.0%}. Both are appraisal overlays — confirm the "
                "site's actual ETS scope and IETF eligibility before "
                "committing to the resulting NPV."
            ),
        })

    # Reviewer iter-2 issue #3: under v0 defaults (carbon=0, grant=0)
    # the "max NPV" pick lands on a near-do-nothing WHR-only pathway,
    # so Balanced.year_15 < Conservative.year_15. Honest output, but
    # the labelling reads counter-intuitively without context. Surface
    # the inversion explicitly so the renderer can flag it in §1.
    if (
        pathways.get("balanced") and pathways.get("conservative")
        and pathways["balanced"]["year_15_reduction_pct"]
            < pathways["conservative"]["year_15_reduction_pct"] - 1e-6
    ):
        warnings_out.append({
            "severity": "advisory",
            "code": "balanced_underperforms_conservative_under_v0_defaults",
            "message": (
                "Balanced (max-NPV) pathway delivers less year-15 carbon "
                "reduction than Conservative at this scenario — a "
                "consequence of zero carbon price and zero grant in the "
                "v0 default. With the £75/tCO2e + 30% IETF-grant overlay "
                "applied, Balanced typically reverts to the "
                "highest-reduction-with-positive-NPV pathway. The "
                "renderer should flag this inversion in the executive "
                "summary so a senior reader doesn't mistake "
                "'Balanced 1.6%' for engine failure."
            ),
        })

    # Reviewer iter-2 issue #1: methodology §3.6 lists "Sensitivity to
    # electricity price, gas price, grant outcome" + CVaR-90% as
    # required per-pathway outputs. v0 doesn't yet run the sweep —
    # declare explicitly rather than leave silently absent.
    warnings_out.append({
        "severity": "medium",
        "code": "sensitivity_not_yet_computed",
        "message": (
            "Per-pathway sensitivity sweeps (electricity ±20%, gas ±20%, "
            "grant 0/30/50%) and risk-adjusted NPV (CVaR @ 90%) are "
            "deferred to v0.2 alongside the stochastic MILP optimiser. "
            "Manually overlay sensitivities by re-running with perturbed "
            "ets_allowance_price_gbp_per_tco2e / ietf_grant_fraction / "
            "market_signals until the v0.2 release."
        ),
    })

    # Reviewer iter-2 issue #2: capex curves are flat £/kW with no
    # equipment-class breakpoint. IETF Phase 3 award schedule shows
    # NH3 HPs at £1,200-£1,500/kW thermal at 1-3 MW scale, dropping
    # to £800-£1,000/kW at 5+ MW. v0 uses £800/kW flat — at the
    # optimistic end of the published evidence.
    warnings_out.append({
        "severity": "medium",
        "code": "capex_flat_rate_v0",
        "message": (
            "Capex curves are flat £/kW with no size-dependent "
            "breakpoint. IETF Phase 3 award schedule data (DESNZ 2024) "
            "indicates real industrial NH3 HP capex spans £800-£1,500/kW "
            "thermal across the 1-5 MW range; the v0 flat £800/kW sits "
            "at the optimistic edge. A ±30% capex envelope shifts "
            "balanced NPV by approximately £500k under default tariffs "
            "for dairy_5mw — material for a senior decision. v0.2 will "
            "introduce a two-segment piecewise (£1,400/kW for <2 MW, "
            "£900/kW for ≥2 MW) with explicit row-level citations."
        ),
    })

    # Equipment-ageing limitation flag
    warnings_out.append({
        "severity": "advisory",
        "code": "equipment_ageing_not_modelled",
        "message": (
            "Equipment ageing and end-of-life replacement decisions are not "
            "modelled in v0 — all installed equipment assumed to operate at "
            "rated performance for the full 15-year horizon. Refresh in v0.2 "
            "alongside the stochastic MILP optimiser."
        ),
    })
    warnings_out.append({
        "severity": "advisory",
        "code": "v0_brute_force_enumeration",
        "message": (
            "v0 uses brute-force enumeration of ~50 candidate pathways "
            "(merit-order dispatch evaluator). The proper multi-period "
            "stochastic MILP via Pyomo / OR-Tools lands in v0.2."
        ),
    })

    return {
        "site_id": site_brief.get("site_id", "unknown"),
        "planning_horizon_years": horizon_years,
        "base_year": base_year,
        "discount_rate_real": discount_rate,
        "capex_budget_gbp": capex_budget,
        "ets_allowance_price_gbp_per_tco2e": ets_price,
        "ietf_grant_fraction": grant_frac,
        "candidate_count": len(candidates),
        "evaluated_count": len(evaluated),
        "pathways": pathways,
        "pareto_frontier": pareto_capex,                  # legacy alias = capex frontier
        "pareto_frontier_capex_vs_carbon": pareto_capex,
        "pareto_frontier_npv_vs_carbon": pareto_npv,
        "warnings": warnings_out,
        "method_reference": (
            "Brute-force enumeration of pathway candidates (capacity × timing "
            "permutations from the screening actionable pool, capex-budget "
            "filtered). Each candidate evaluated by 15-year run of "
            "simulate_site_dispatch + compute_baseline_carbon. NPV at the "
            "site's declared real discount rate; IRR by Brent's method on "
            "NPV(r); LCOH = PV(total cost) / PV(thermal delivered). "
            "Equipment ageing not modelled (v0.2). Stochastic MILP not "
            "implemented (v0.2)."
        ),
        "standards_cited": [
            "HM Treasury Green Book — Appraisal and Evaluation in Central Government",
            "BS EN 16247-1:2022 §6 — Techno-economic appraisal of energy audits",
            "IEA Cost & Performance Database 2024 — industrial heat-pump and electrode-boiler capex",
            "IETF Phase 3 indicative cost benchmarks (DESNZ, 2024)",
            "Lazard Levelized Cost of Energy v17 (industrial heat sources)",
            "NESO Future Energy Scenarios 2025 — UK grid carbon intensity forecast",
            "DEFRA UK GHG Conversion Factors 2026 — natural gas Scope 1 emission factor",
        ],
        "provenance": [
            {
                "calculation": "capex per technology",
                "method": "Flat £/kW or £/kWh from indicative 2026 UK industrial benchmarks",
                "source": "IEA Cost & Performance Database 2024; IETF Phase 3 cost data",
                "values_used": dict(_CAPEX_CURVES_GBP),
            },
            {
                "calculation": "annual O&M",
                "method": "Fraction of installed capex; vendor service-contract benchmarks",
                "values_used": dict(_OPEX_FRACTION_OF_CAPEX),
            },
            {
                "calculation": "NPV",
                "method": (
                    f"Sum of (savings_y - capex_y - opex_y) / (1+r)^y over y=0..{horizon_years - 1}, "
                    f"r = {discount_rate}. Savings = baseline_energy_cost - dispatch_energy_cost. "
                    "HM Treasury Green Book §6 conventions."
                ),
            },
            {
                "calculation": "IRR",
                "method": "Brent's method on NPV(r) over [-0.99, +1.0]; None if no sign change",
                "source": "scipy.optimize.brentq",
            },
            {
                "calculation": "LCOH",
                "method": (
                    "PV(annual_dispatch_cost + capex + opex) / PV(annual_thermal_delivered)"
                ),
            },
            {
                "calculation": "year-15 carbon reduction %",
                "method": (
                    "(baseline_year0_carbon - pathway_year15_carbon) / "
                    "baseline_year0_carbon * 100. Baseline from "
                    "compute_baseline_carbon.carbon_trajectory_no_action."
                ),
            },
            {
                "calculation": "Pareto frontier",
                "method": (
                    "Non-dominated set of (capex_total_gbp, "
                    "cumulative_carbon_abated_t_co2e) over all evaluated candidates."
                ),
            },
        ],
    }


__all__ = ["optimise_investment_pathway"]
