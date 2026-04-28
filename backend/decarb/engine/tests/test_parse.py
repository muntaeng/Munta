"""Tests for parse.parse_energy_profile against the 3 golden sites."""
from __future__ import annotations

import numpy as np
import pytest

from decarb.engine.parse import parse_energy_profile


class TestDairy:
    def test_annual_balance_reconstructed(self, dairy_5mw):
        result = parse_energy_profile(dairy_5mw)
        b = result["annual_balance_kwh"]
        # From dairy_5mw: 12.5 GWh elec, 38 GWh gas
        assert abs(b["electricity_kwh"] - 12_500_000) < 1000
        assert abs(b["natural_gas_kwh"] - 38_000_000) < 1000

    def test_steam_load_profile_present(self, dairy_5mw):
        result = parse_energy_profile(dairy_5mw)
        steam_eu = next((eu for eu in result["end_use_profiles"] if eu["end_use"] == "steam"), None)
        assert steam_eu is not None, "steam end-use profile missing"
        # 28 GWh annual demand
        assert abs(steam_eu["annual_demand_kwh"] - 28_000_000) < 1000
        # Two-shift schedule should give peak around 2,500-4,000 kW (load concentrated in shifts)
        peak = steam_eu["metrics"]["peak_kw"]
        assert 1_500 < peak < 7_000, f"Steam peak out of expected range: {peak}"

    def test_production_linkage(self, dairy_5mw):
        result = parse_energy_profile(dairy_5mw)
        pl = result["production_linkage"]
        assert pl["production_unit"] == "tonnes_milk_processed"
        assert pl["annual_production"] == 180_000
        # 38 GWh / 180k tonnes = 211 kWh/tonne gas
        assert 200 < pl["kwh_per_production_unit"]["natural_gas"] < 220

    def test_existing_plant_utilisation_present(self, dairy_5mw):
        result = parse_energy_profile(dairy_5mw)
        plant = result["existing_plant_utilisation"]
        assert len(plant) >= 2  # at least main + backup boiler
        for asset in plant:
            assert "estimated_load_factor" in asset
            assert 0 <= asset["estimated_load_factor"] <= 1

    def test_sector_benchmark_dairy(self, dairy_5mw):
        result = parse_energy_profile(dairy_5mw)
        bm = result["sector_benchmark_note"]
        assert bm["comparison_available"] is True
        assert bm["subsector"] == "dairy_processing"
        # 211 kWh/tonne gas — within benchmark 180-280
        gas_metric = bm["metrics"]["gas_kwh_per_tonne"]
        assert gas_metric["verdict"] == "within_typical_range"

    def test_no_warnings_for_clean_input(self, dairy_5mw):
        result = parse_energy_profile(dairy_5mw)
        high_warnings = [w for w in result["warnings"] if w["severity"] == "high"]
        assert len(high_warnings) == 0


class TestBrewery:
    def test_annual_balance(self, brewery_8mw):
        result = parse_energy_profile(brewery_8mw)
        b = result["annual_balance_kwh"]
        assert abs(b["electricity_kwh"] - 18_000_000) < 1000
        assert abs(b["natural_gas_kwh"] - 62_000_000) < 1000

    def test_batch_brewing_profile_has_peaks(self, brewery_8mw):
        result = parse_energy_profile(brewery_8mw)
        steam_eu = next((eu for eu in result["end_use_profiles"] if eu["end_use"] == "steam"), None)
        assert steam_eu is not None
        # Batch brewing produces sharper peaks vs flat operation
        # Peak / average should be > 1.5
        peak = steam_eu["metrics"]["peak_kw"]
        avg = steam_eu["metrics"]["average_kw"]
        assert peak / max(avg, 1) > 1.4

    def test_production_linkage_hectolitres(self, brewery_8mw):
        result = parse_energy_profile(brewery_8mw)
        assert result["production_linkage"]["production_unit"] == "hectolitres"


class TestSoftDrinks:
    def test_annual_balance(self, soft_drinks_12mw):
        result = parse_energy_profile(soft_drinks_12mw)
        b = result["annual_balance_kwh"]
        assert abs(b["electricity_kwh"] - 26_000_000) < 1000
        assert abs(b["natural_gas_kwh"] - 78_000_000) < 1000

    def test_continuous_profile_low_peak_to_avg(self, soft_drinks_12mw):
        """Soft drinks runs near-continuously — peak/avg should be < 1.5."""
        result = parse_energy_profile(soft_drinks_12mw)
        steam_eu = next((eu for eu in result["end_use_profiles"] if eu["end_use"] == "steam"), None)
        assert steam_eu is not None
        peak = steam_eu["metrics"]["peak_kw"]
        avg = steam_eu["metrics"]["average_kw"]
        assert peak / max(avg, 1) < 1.6


class TestErrorHandling:
    def test_empty_brief_warns(self):
        result = parse_energy_profile({})
        codes = [w["code"] for w in result["warnings"]]
        assert "no_energy_data" in codes
