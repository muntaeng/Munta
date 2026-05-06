"""Tests for decarb.engine.validate — §4.4 self-critique loop."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from decarb.engine.carbon import compute_baseline_carbon
from decarb.engine.dispatch import DEFAULT_MARKET_SIGNALS, simulate_site_dispatch
from decarb.engine.parse import parse_energy_profile
from decarb.engine.pathway import optimise_investment_pathway
from decarb.engine.screen import screen_technologies
from decarb.engine.uncertainty import monte_carlo_uncertainty
from decarb.engine.validate import (
    check_carbon_balance_year_15,
    check_discounted_ge_simple_payback,
    check_provenance_arithmetic_self_consistent,
    check_screen_pathway_grid_consistency,
    check_shortlist_in_pathway_or_excluded,
    validate_pathway,
)


# ---------------------------------------------------------------------------
# Fixture: a real dairy bundle, computed once per session.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dairy_bundle() -> dict:
    site_path = (
        Path(__file__).resolve().parents[2]
        / "tests" / "sites" / "dairy_5mw.json"
    )
    site = json.loads(site_path.read_text())
    ep = parse_energy_profile(site_brief=site)
    ca = compute_baseline_carbon(annual_balance_kwh=ep["annual_balance_kwh"], year=2026)
    sc = screen_technologies(site_brief=site, energy_profile=ep)
    disp = simulate_site_dispatch(
        energy_profile=ep,
        technology_stack=[{
            "type": "gas_boiler", "id": "g",
            "capacity_kw": 10_000.0, "efficiency": 0.85,
            "serves_end_uses": ["steam", "hot_water"],
        }],
        market_signals=DEFAULT_MARKET_SIGNALS,
        dispatch_policy="merit_order",
        year=2026,
    )
    pw = optimise_investment_pathway(
        site_brief=site, screening=sc, energy_profile=ep,
        ets_allowance_price_gbp_per_tco2e=100.0,
        ietf_grant_fraction=0.38,
        pathway_selection_rule="max_reduction_positive_npv",
    )
    horizon = pw["planning_horizon_years"]
    base_year = pw["base_year"]
    bcost: list[float] = []
    bcarb: list[float] = []
    for y in range(horizon):
        d = simulate_site_dispatch(
            energy_profile=ep,
            technology_stack=[{
                "type": "gas_boiler", "id": "g",
                "capacity_kw": 10_000.0, "efficiency": 0.85,
                "serves_end_uses": ["steam", "hot_water"],
            }],
            market_signals=DEFAULT_MARKET_SIGNALS,
            dispatch_policy="merit_order",
            year=base_year + y,
        )
        bcost.append(float(d.get("annual_summary", {}).get("total_energy_cost_gbp", 0.0)))
        bcarb.append(float(d.get("carbon_summary", {}).get("total_t_co2e", 0.0)))
    mc = monte_carlo_uncertainty(
        pw, pathway_name="balanced",
        baseline_annual_cost_gbp_per_year=bcost,
        baseline_annual_carbon_t_per_year=bcarb,
        n_trials=200, seed=42,
    )
    return {
        "site_brief": site, "energy_profile": ep, "screening": sc,
        "baseline_carbon": ca, "dispatch": disp, "pathway": pw,
        "monte_carlo": mc,
    }


# ---------------------------------------------------------------------------
# Top-level: dairy passes (no error-severity failures).
# ---------------------------------------------------------------------------


def test_validate_passes_on_dairy(dairy_bundle):
    res = validate_pathway(**dairy_bundle)
    assert res["passed"] is True
    errors = [c for c in res["checks"]
              if c["severity"] == "error" and not c["passed"]]
    assert errors == []
    assert res["summary"]["errors"] == 0


def test_validate_returns_all_nine_checks(dairy_bundle):
    res = validate_pathway(**dairy_bundle)
    ids = [c["check_id"] for c in res["checks"]]
    assert ids == [
        "discounted_ge_simple_payback",
        "screen_pathway_grid_consistency",
        "carbon_balance_year_15",
        "exec_summary_baseline_consistency",
        "provenance_arithmetic_self_consistent",
        "mc_pathway_consistency",
        "shortlist_in_pathway_or_excluded",
        "standards_register_no_dupes",
        "methodology_status_matches_engine",
    ]


# ---------------------------------------------------------------------------
# Mutation tests (Phase 5 BINDING #3).
# ---------------------------------------------------------------------------


def test_mutation_d1_drop_y0_revert(dairy_bundle):
    """D1: corrupt discounted_payback so simple > discounted, expect
    discounted_ge_simple_payback to fail."""
    pw = copy.deepcopy(dairy_bundle["pathway"])
    pw["pathways_with_reinforcement"]["balanced"]["discounted_payback_years"] = 1.0
    pw["pathways_with_reinforcement"]["balanced"]["simple_payback_years"] = 5.0
    bundle = dict(dairy_bundle)
    bundle["pathway"] = pw
    res = validate_pathway(**bundle)
    assert res["passed"] is False
    failed = [c for c in res["checks"] if not c["passed"]
              and c["check_id"] == "discounted_ge_simple_payback"]
    assert len(failed) == 1


def test_mutation_d2_grid_action_in_no_reinforcement(dairy_bundle):
    """D2: re-include a requires_grid_decision action in a
    no-reinforcement pathway, expect screen_pathway_grid_consistency
    to fail."""
    pw = copy.deepcopy(dairy_bundle["pathway"])
    nr_balanced = pw["pathways_no_reinforcement"]["balanced"]
    if nr_balanced is None:
        nr_balanced = {"name": "balanced", "actions": []}
        pw["pathways_no_reinforcement"]["balanced"] = nr_balanced
    nr_balanced["actions"] = list(nr_balanced.get("actions", [])) + [{
        "year_index": 1, "tech_kind": "electrode_boiler",
        "tech_id": "eb_4000", "capacity": 4000.0,
        "capacity_unit": "kW_thermal",
        "requires_grid_decision": True,
    }]
    bundle = dict(dairy_bundle)
    bundle["pathway"] = pw
    res = validate_pathway(**bundle)
    assert res["passed"] is False
    failed = [c for c in res["checks"] if not c["passed"]
              and c["check_id"] == "screen_pathway_grid_consistency"]
    assert len(failed) == 1


def test_mutation_d5_drop_ccl_precision():
    """D5: a CCL-style provenance row whose stated £ disagrees with the
    rate × volume product trips
    provenance_arithmetic_self_consistent."""
    bad_carbon = {
        "provenance": [
            {"field": "ccl_elec",
             "method": "Main CCL rates: elec 0.77500 p/kWh × 12,500,000 kWh = £1,000,000"}
        ]
    }
    check = check_provenance_arithmetic_self_consistent(bad_carbon)
    assert check["passed"] is False
    assert check["check_id"] == "provenance_arithmetic_self_consistent"


def test_mutation_d5_correct_passes():
    good_carbon = {
        "provenance": [
            {"field": "ccl_elec",
             "method": "elec 0.77500 p/kWh × 12,500,000 kWh = £96,875"}
        ]
    }
    check = check_provenance_arithmetic_self_consistent(good_carbon)
    assert check["passed"] is True


# ---------------------------------------------------------------------------
# Per-check unit tests.
# ---------------------------------------------------------------------------


def test_carbon_balance_year_15_detects_inconsistency():
    pw = {
        "pathways_with_reinforcement": {
            "balanced": {
                "baseline_year_0_carbon_t_co2e": 1000.0,
                "year_15_total_carbon_t_co2e": 500.0,
                "year_15_reduction_pct": 30.0,  # truth: 50%
            }
        },
        "pathways_no_reinforcement": {},
    }
    chk = check_carbon_balance_year_15(pw)
    assert chk["passed"] is False
    assert chk["details"]["failures"][0]["reported_pct"] == 30.0


def test_shortlist_in_pathway_or_excluded_flags_unmapped():
    sc = {"shortlist": [], "excluded_pending_grid_decision": []}
    pw = {
        "pathways_with_reinforcement": {
            "balanced": {
                "actions": [
                    {"tech_kind": "heat_pump_mid_temp", "tech_id": "hp_mid_500"}
                ]
            }
        },
        "pathways_no_reinforcement": {},
    }
    chk = check_shortlist_in_pathway_or_excluded(sc, pw)
    assert chk["passed"] is False


def test_shortlist_passes_for_waste_heat_recovery_without_screening():
    sc = {"shortlist": [], "excluded_pending_grid_decision": []}
    pw = {
        "pathways_with_reinforcement": {
            "balanced": {
                "actions": [
                    {"tech_kind": "waste_heat_recovery", "tech_id": "whr_500"}
                ]
            }
        },
        "pathways_no_reinforcement": {},
    }
    chk = check_shortlist_in_pathway_or_excluded(sc, pw)
    assert chk["passed"] is True


def test_discounted_ge_simple_allows_simple_set_discounted_none():
    pw = {
        "pathways_with_reinforcement": {
            "balanced": {
                "simple_payback_years": 6.0,
                "discounted_payback_years": None,
            }
        },
        "pathways_no_reinforcement": {},
    }
    chk = check_discounted_ge_simple_payback(pw)
    assert chk["passed"] is True


def test_screen_pathway_grid_consistency_passes_when_all_clear():
    pw = {
        "pathways_with_reinforcement": {},
        "pathways_no_reinforcement": {
            "balanced": {
                "actions": [
                    {"tech_kind": "heat_pump_mid_temp",
                     "requires_grid_decision": False}
                ]
            }
        },
    }
    chk = check_screen_pathway_grid_consistency(pw)
    assert chk["passed"] is True
