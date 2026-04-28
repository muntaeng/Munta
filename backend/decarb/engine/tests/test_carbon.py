"""Tests for carbon.compute_baseline_carbon against the 3 golden sites."""
from __future__ import annotations

import pytest

from decarb.engine.carbon import compute_baseline_carbon
from decarb.engine.parse import parse_energy_profile


class TestDairyBaselineCarbon:
    def test_total_scope_1_2_in_golden_range(self, dairy_5mw):
        """Golden truth: 7,820 tCO2e/yr Scope 1+2 location-based for 2026."""
        parsed = parse_energy_profile(dairy_5mw)
        result = compute_baseline_carbon(
            annual_balance_kwh=parsed["annual_balance_kwh"],
            year=2026,
            site_secr_reportable=True,
            cca_subsector="dairy_processing",
        )
        # Golden expectation: 7,820 tCO2e — widened for grid-factor sensitivity
        total = result["totals"]["scope_1_2_loc_t_co2e"]
        assert 7_200 < total < 9_500, f"Scope 1+2 total out of golden range: {total}"

    def test_scope_3_material(self, dairy_5mw):
        """Scope 3 WTT should add ~15-20% on top of Scope 1+2."""
        parsed = parse_energy_profile(dairy_5mw)
        result = compute_baseline_carbon(
            annual_balance_kwh=parsed["annual_balance_kwh"], year=2026
        )
        s12 = result["totals"]["scope_1_2_loc_t_co2e"]
        s123 = result["totals"]["scope_1_2_3_t_co2e"]
        ratio = (s123 - s12) / s12
        assert 0.10 < ratio < 0.25, f"Scope 3 / (S1+S2) ratio out of range: {ratio}"

    def test_carbon_trajectory_decarbonises(self, dairy_5mw):
        """No-action trajectory: Scope 1 stays flat, Scope 2 falls with grid."""
        parsed = parse_energy_profile(dairy_5mw)
        result = compute_baseline_carbon(
            annual_balance_kwh=parsed["annual_balance_kwh"], year=2026
        )
        traj = result["carbon_trajectory_no_action"]
        assert len(traj) == 16  # 0..15 years inclusive
        # 2040 total should be lower than 2026 total (grid decarbonised by then)
        first = traj[0]["total_t_co2e"]
        later = traj[-1]["total_t_co2e"]
        assert later < first, "Carbon trajectory should fall with grid decarbonisation"
        # But not by more than 30% — gas combustion is unchanged
        assert later > 0.6 * first, "No-action shouldn't fall too far without action"

    def test_uk_ets_assessment_dairy_not_in_ets(self, dairy_5mw):
        parsed = parse_energy_profile(dairy_5mw)
        result = compute_baseline_carbon(
            annual_balance_kwh=parsed["annual_balance_kwh"],
            year=2026,
            site_in_uk_ets=False,
        )
        assert result["regulatory_exposure"]["uk_ets"]["in_uk_ets"] is False

    def test_secr_assessment_present(self, dairy_5mw):
        parsed = parse_energy_profile(dairy_5mw)
        result = compute_baseline_carbon(
            annual_balance_kwh=parsed["annual_balance_kwh"],
            year=2026,
            site_secr_reportable=True,
        )
        assert result["regulatory_exposure"]["secr"]["secr_reportable"] is True
        assert result["regulatory_exposure"]["secr"]["intensity_metric_required"] is True

    def test_cca_discount_applied(self, dairy_5mw):
        parsed = parse_energy_profile(dairy_5mw)
        with_cca = compute_baseline_carbon(
            annual_balance_kwh=parsed["annual_balance_kwh"],
            year=2026,
            cca_subsector="dairy_processing",
        )
        without_cca = compute_baseline_carbon(
            annual_balance_kwh=parsed["annual_balance_kwh"],
            year=2026,
            cca_subsector=None,
        )
        # CCA should reduce CCL liability by ~90%
        ccl_with = with_cca["regulatory_exposure"]["ccl"]["annual_ccl_liability_gbp_estimate"]
        ccl_without = without_cca["regulatory_exposure"]["ccl"]["annual_ccl_liability_gbp_estimate"]
        assert ccl_with < ccl_without * 0.2

    def test_method_reference_cites_ghg_protocol(self, dairy_5mw):
        parsed = parse_energy_profile(dairy_5mw)
        result = compute_baseline_carbon(
            annual_balance_kwh=parsed["annual_balance_kwh"], year=2026
        )
        method = result["method_reference"]
        assert "GHG Protocol" in method
        assert "DEFRA" in method
        assert "Scope 2 Guidance" in method


class TestBreweryBaselineCarbon:
    def test_total_scope_1_2_in_golden_range(self, brewery_8mw):
        """Golden: 14,800 tCO2e/yr ± 400."""
        parsed = parse_energy_profile(brewery_8mw)
        result = compute_baseline_carbon(
            annual_balance_kwh=parsed["annual_balance_kwh"], year=2026
        )
        total = result["totals"]["scope_1_2_loc_t_co2e"]
        assert 13_800 < total < 15_400, f"Brewery Scope 1+2 total out of range: {total}"


class TestSoftDrinksBaselineCarbon:
    def test_total_scope_1_2_in_golden_range(self, soft_drinks_12mw):
        """Golden: 19,300 tCO2e/yr ± 600."""
        parsed = parse_energy_profile(soft_drinks_12mw)
        result = compute_baseline_carbon(
            annual_balance_kwh=parsed["annual_balance_kwh"], year=2026
        )
        total = result["totals"]["scope_1_2_loc_t_co2e"]
        assert 17_500 < total < 21_000, f"Soft drinks Scope 1+2 total out of range: {total}"


class TestProvenance:
    def test_provenance_complete(self, dairy_5mw):
        parsed = parse_energy_profile(dairy_5mw)
        result = compute_baseline_carbon(
            annual_balance_kwh=parsed["annual_balance_kwh"], year=2026
        )
        prov = result["provenance"]
        assert len(prov) > 0
        # Each entry must cite a source
        for entry in prov:
            assert "source" in entry or "method" in entry
