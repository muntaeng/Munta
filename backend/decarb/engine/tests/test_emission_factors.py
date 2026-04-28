"""Tests for emission_factors module."""
from __future__ import annotations

import pytest

from decarb.engine.emission_factors import (
    GHGScope,
    SCOPE_1_FACTORS,
    SCOPE_3_WTT_FACTORS,
    grid_intensity_for_year,
    scope1_emissions_kg_co2e,
    scope2_emissions_kg_co2e,
    scope3_upstream_fuel_emissions_kg_co2e,
)


class TestDEFRAFactors:
    def test_natural_gas_factor_in_expected_range(self):
        """DEFRA natural gas (gross CV) typically 0.18-0.19 kgCO2e/kWh."""
        ef = SCOPE_1_FACTORS["natural_gas"]
        assert 0.180 < ef.co2e_kg_per_unit < 0.185
        assert ef.unit == "kWh_GCV"

    def test_gas_oil_factor_in_expected_range(self):
        ef = SCOPE_1_FACTORS["gas_oil"]
        assert 2.6 < ef.co2e_kg_per_unit < 2.8
        assert ef.unit == "litre"

    def test_biomass_combustion_co2_zero(self):
        """Biogenic CO2 considered out of scope; only CH4+N2O contribute."""
        ef = SCOPE_1_FACTORS["biomass_wood_pellets"]
        assert ef.co2_kg_per_unit == 0.0
        assert ef.co2e_kg_per_unit > 0  # CH4 + N2O still count

    def test_provenance_round_trip(self):
        ef = SCOPE_1_FACTORS["natural_gas"]
        prov = ef.to_provenance()
        assert prov["fuel"] == "natural_gas"
        assert prov["scope"] == "scope_1"
        assert "DEFRA" in prov["source"]


class TestGridIntensity:
    def test_known_year(self):
        gi = grid_intensity_for_year(2026)
        assert 0.10 < gi < 0.20

    def test_extrapolation_beyond_table(self):
        """Should clamp to 2050 value, not error."""
        gi_2099 = grid_intensity_for_year(2099)
        gi_2050 = grid_intensity_for_year(2050)
        assert gi_2099 == gi_2050

    def test_interpolation_between_known(self):
        """2031 should interpolate between 2030 and 2032."""
        gi_2030 = grid_intensity_for_year(2030)
        gi_2031 = grid_intensity_for_year(2031)
        gi_2032 = grid_intensity_for_year(2032)
        assert gi_2032 < gi_2031 < gi_2030

    def test_decarbonisation_trajectory(self):
        """Grid should monotonically decarbonise from 2024 to 2050."""
        prev = grid_intensity_for_year(2024)
        for y in range(2025, 2051):
            cur = grid_intensity_for_year(y)
            assert cur <= prev, f"Grid intensity went up: {prev} → {cur} at year {y}"
            prev = cur


class TestScope1Aggregator:
    def test_dairy_5mw_baseline(self):
        """38 GWh gas → ~6,950 t Scope 1 (DEFRA factor 0.18293)."""
        result = scope1_emissions_kg_co2e(natural_gas_kwh=38_000_000)
        # 38e6 * 0.18293 / 1000 = 6,951
        assert 6_900 < result["total_t_co2e"] < 7_000

    def test_brewery_8mw_baseline(self):
        """62 GWh gas → ~11,340 t Scope 1."""
        result = scope1_emissions_kg_co2e(natural_gas_kwh=62_000_000)
        assert 11_300 < result["total_t_co2e"] < 11_400

    def test_breakdown_includes_co2_ch4_n2o(self):
        result = scope1_emissions_kg_co2e(natural_gas_kwh=10_000_000)
        breakdown = result["breakdown_kg_co2e"]["natural_gas"]
        assert "co2_kg" in breakdown
        assert "ch4_kg" in breakdown
        assert "n2o_kg" in breakdown
        # CO2 dominant
        assert breakdown["co2_kg"] > breakdown["ch4_kg"] * 100


class TestScope2:
    def test_dairy_5mw_scope_2_2026(self):
        """12.5 GWh elec × 0.152 (2026 forecast) = ~1,900 t."""
        result = scope2_emissions_kg_co2e(
            electricity_kwh=12_500_000, year=2026
        )
        assert 1_700 < result["location_based_t_co2e"] < 2_100

    def test_dual_reporting(self):
        result = scope2_emissions_kg_co2e(
            electricity_kwh=10_000_000, year=2026
        )
        assert result["location_based_t_co2e"] > 0
        assert result["market_based_t_co2e"] > 0


class TestScope3:
    def test_natural_gas_wtt_material(self):
        """WTT for natural gas adds ~18-22% on top of Scope 1 combustion."""
        scope1 = scope1_emissions_kg_co2e(natural_gas_kwh=38_000_000)
        scope3 = scope3_upstream_fuel_emissions_kg_co2e(natural_gas_kwh=38_000_000)
        ratio = scope3["total_t_co2e"] / scope1["total_t_co2e"]
        assert 0.15 < ratio < 0.25, f"Scope 3 WTT / Scope 1 ratio out of range: {ratio}"

    def test_td_losses_on_electricity(self):
        result = scope3_upstream_fuel_emissions_kg_co2e(
            natural_gas_kwh=0, electricity_kwh=10_000_000
        )
        # 10e6 * 0.01876 / 1000 = 187.6 t
        assert 180 < result["total_t_co2e"] < 200
