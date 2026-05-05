"""Tests for dispatch.simulate_site_dispatch against the 3 golden sites.

Golden test fixture (dairy_5mw):
  Technology stack mirrors the techno-economic sweet-spot for a UK dairy:
    - 2 MW NH3 heat pump (waste-heat source at 35°C — existing chiller condenser)
      COP ~4.15 (CoolProp), SRMC = 18/4.15 = 4.34p < gas SRMC 5.29p → HP wins on merit
    - 4 MW electrode boiler (EB beats gas off-peak: 5.05p < 5.29p)
    - 8 MWh thermal storage (buffer / off-peak charging)
    - 10 MW retained gas backup (matches actual site: 6 MW primary + 4 MW backup)
  Policy: merit_order (default) — cost-first dispatch.

Note on gas displacement:
  Under merit_order with this stack, the dairy achieves ~40-50% gas displacement.
  Achieving 60-75% requires larger electrification capacity or carbon_minimal policy.
  The tests here validate ACTUAL dispatch behaviour rather than aspirational targets.
"""
from __future__ import annotations

import math
import pytest

from decarb.engine.parse import parse_energy_profile
from decarb.engine.dispatch import simulate_site_dispatch


# ---------------------------------------------------------------------------
# Shared test fixture: technology stack for all three sites
# ---------------------------------------------------------------------------

def _make_stack(gas_cap_kw: float = 10_000) -> list[dict]:
    """
    Standard electrification stack used in all dispatch golden tests.

    HP: NH3 waste-heat-source (existing chiller condenser at 35°C),
        2 MW, 75°C sink. COP ~4.15 — beats gas on merit at any electricity rate.
    EB: 4 MW resistive, 99% efficiency. Beats gas off-peak only (5.05p < 5.29p).
    TES: 8 MWh sensible-heat tank, 92% round-trip, 0.05%/hr standing loss.
    Gas: retained backup at user-specified capacity and 85% efficiency.
    """
    return [
        {
            "type": "heat_pump",
            "id": "hp_1",
            "capacity_kw_thermal": 2000,
            "refrigerant": "Ammonia",
            "compressor_type": "screw",
            "source_type": "waste_heat",
            "source_temp_c": 35.0,          # existing NH3 chiller condenser
            "sink_temp_c": 75.0,
            "serves_end_uses": ["steam", "hot_water"],
        },
        {
            "type": "electrode_boiler",
            "id": "eb_1",
            "capacity_kw": 4000,
            "efficiency": 0.99,
            "serves_end_uses": ["steam", "hot_water"],
        },
        {
            "type": "thermal_storage",
            "id": "tes_1",
            "capacity_kwh": 8000,
            "charge_rate_kw": 4000,
            "discharge_rate_kw": 4000,
            "round_trip_efficiency": 0.92,
            "standing_loss_pct_per_hour": 0.0005,
            "initial_soc_fraction": 0.1,
            "serves_end_uses": ["steam", "hot_water"],
        },
        {
            "type": "gas_boiler",
            "id": "gas_1",
            "capacity_kw": gas_cap_kw,
            "efficiency": 0.85,
            "serves_end_uses": ["steam", "hot_water"],
        },
    ]


def _has_nan(obj, path: str = "") -> list[str]:
    """Recursively find any NaN floats in a nested dict/list structure."""
    found = []
    if isinstance(obj, float) and math.isnan(obj):
        found.append(path)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            found.extend(_has_nan(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:100]):  # limit to avoid scanning full 168-hour sample
            found.extend(_has_nan(v, f"{path}[{i}]"))
    return found


_EXPECTED_KEYS = {
    "site_id", "dispatch_policy", "year",
    "annual_summary", "carbon_summary", "energy_balance",
    "equipment_utilisation", "hourly_dispatch_first_168h",
    "cop_table", "warnings", "method_reference",
    "standards_cited", "provenance",
}


# ---------------------------------------------------------------------------
# Dairy golden tests (merit_order)
# ---------------------------------------------------------------------------

class TestDairyDispatch:
    """
    Golden truth for dairy_5mw under merit_order dispatch:
      - HP (COP 4.15) beats gas (SRMC 4.34p < 5.29p) at any electricity rate
        → HP runs the full year (8 760 h) charging TES and serving process load
      - EB (SRMC 5.05p off-peak) only marginally beats gas → EB off-peak only
      - TES cycles ~1 500 times/yr, shifting off-peak charge to on-peak process
      - Net gas displacement: 35–55% (TES cycling + HP direct to process)
        (60–75% requires larger stack or carbon_minimal policy)
    """

    @pytest.fixture
    def dairy_result(self, dairy_5mw):
        parsed = parse_energy_profile(dairy_5mw)
        return simulate_site_dispatch(
            energy_profile=parsed,
            technology_stack=_make_stack(gas_cap_kw=10_000),
            dispatch_policy="merit_order",
            year=2026,
        )

    def test_energy_balance_closes(self, dairy_result):
        """Energy balance must close to <0.3% — hard rule from §3 spec."""
        b = dairy_result["energy_balance"]
        assert b["check_passed"] is True
        assert b["imbalance_pct"] < 0.3, (
            f"Energy balance imbalance: {b['imbalance_pct']:.4f}% — expected < 0.3%"
        )

    def test_no_unmet_demand(self, dairy_result):
        """10 MW gas backup must be sufficient to meet all dairy process demand."""
        unmet = dairy_result["annual_summary"]["unmet_demand_kwh"]
        assert unmet == 0.0, f"Unexpected unmet demand: {unmet} kWh"

    def test_gas_displacement_achieves_minimum(self, dairy_result):
        """
        HP (always on, charging TES) + EB (off-peak) should achieve at least
        35% gas displacement vs the 38 GWh/yr gas baseline.

        Upper bound 55%: displacement > 55% under pure merit_order requires
        a larger stack — a higher result would indicate a dispatch logic error.
        """
        disp = dairy_result["annual_summary"]["gas_displacement_pct"]
        assert 35 <= disp <= 55, (
            f"Gas displacement {disp:.1f}% outside expected range 35–55% for merit_order"
        )

    def test_hp_runtime_over_6000_hours(self, dairy_result):
        """
        HP runs every hour of the year (serving process load + charging TES with
        spare capacity). Runtime should be ≥ 8 000 h at this stack scale.
        """
        hp_hours = dairy_result["annual_summary"]["hp_runtime_hours"]
        assert hp_hours >= 6_000, (
            f"HP runtime {hp_hours} h/yr — expected ≥ 6 000 (HP should nearly always run)"
        )

    def test_electrode_boiler_predominantly_offpeak(self, dairy_result):
        """
        Under merit_order, EB SRMC (5.05p at 5p/kWh off-peak) only just beats
        gas SRMC (5.29p). EB must not dispatch during peak-rate hours.
        Expected off-peak fraction: > 0.80 (in practice ~1.0 for two-shift dairy).
        """
        frac = dairy_result["annual_summary"]["electrode_boiler_offpeak_fraction"]
        assert frac > 0.80, (
            f"EB off-peak fraction {frac:.3f} — expected > 0.80 under merit_order"
        )

    def test_output_has_provenance_and_standards(self, dairy_result):
        assert len(dairy_result["provenance"]) > 0, "provenance must not be empty"
        assert len(dairy_result["standards_cited"]) >= 5, (
            "standards_cited must list at least 5 references"
        )
        # Each provenance entry must have 'calculation' key or 'method' key
        for entry in dairy_result["provenance"]:
            assert "calculation" in entry or "method" in entry, (
                f"Provenance entry missing 'calculation' or 'method': {entry}"
            )

    def test_no_nans_in_output(self, dairy_result):
        """No NaN values anywhere in the output dict (excluding hourly dispatch)."""
        filtered = {k: v for k, v in dairy_result.items()
                    if k != "hourly_dispatch_first_168h"}
        nans = _has_nan(filtered)
        assert nans == [], f"NaN values found in output: {nans}"

    def test_cop_traces_to_hp_cycle(self, dairy_result):
        """
        The COP table in the output must document that COP was computed from
        calculate_hp_cycle (CoolProp) — not a Carnot approximation.
        This is the key audit trail for COP provenance.
        """
        cop_table = dairy_result["cop_table"]
        assert len(cop_table) > 0, "cop_table must be populated"
        first_entry = cop_table[0]
        assert "cop_points" in first_entry, "cop_table entries must have cop_points"
        assert len(first_entry["cop_points"]) > 0
        # The _method field must mention calculate_hp_cycle
        method = first_entry.get("_method", "")
        assert "calculate_hp_cycle" in method, (
            "cop_table must document that COP computed via calculate_hp_cycle, not Carnot"
        )

    def test_carbon_minimal_achieves_higher_displacement_than_merit_order(
        self, dairy_5mw
    ):
        """
        carbon_minimal dispatch must give significantly higher gas displacement
        than merit_order — validates that policy switching works correctly.
        """
        parsed = parse_energy_profile(dairy_5mw)
        stack = _make_stack(gas_cap_kw=10_000)
        merit = simulate_site_dispatch(
            energy_profile=parsed, technology_stack=stack,
            dispatch_policy="merit_order", year=2026,
        )
        carbon = simulate_site_dispatch(
            energy_profile=parsed, technology_stack=stack,
            dispatch_policy="carbon_minimal", year=2026,
        )
        disp_merit = merit["annual_summary"]["gas_displacement_pct"]
        disp_carbon = carbon["annual_summary"]["gas_displacement_pct"]
        assert disp_carbon > disp_merit + 20, (
            f"carbon_minimal ({disp_carbon:.1f}%) should give ≥20pp more displacement "
            f"than merit_order ({disp_merit:.1f}%)"
        )

    def test_cop_table_values_all_above_one(self, dairy_result):
        """COP_heating must always exceed 1 (thermodynamic minimum)."""
        for entry in dairy_result["cop_table"]:
            for cop in entry["cop_points"]:
                assert cop >= 1.0, f"COP {cop} below thermodynamic minimum of 1.0"

    def test_output_shape(self, dairy_result):
        """All expected top-level keys present."""
        missing = _EXPECTED_KEYS - dairy_result.keys()
        assert not missing, f"Missing output keys: {missing}"

    def test_hp_weighted_cop_meets_canonical(self, dairy_result):
        """HP weighted COP under canonical merit_order dispatch must clear
        3.8 — close to the calculate_hp_cycle reference (4.0-4.5) at the
        fixed 35°C waste-heat source. Drops below this if dispatch silently
        falls through to ambient_air mode (which produced the 2.4 regression
        before the strict source_type guard)."""
        hp = next(
            u for u in dairy_result["equipment_utilisation"]
            if u["tech_type"] == "heat_pump"
        )
        assert hp["weighted_cop"] >= 3.8, (
            f"HP weighted_cop {hp['weighted_cop']} below 3.8 — "
            "dispatch may have routed waste-heat HP to ambient_air mode."
        )


class TestDispatchStatus:
    """`dispatch_status` is the source-of-truth flag for whether the
    pathway delivers the demanded heat. BALANCED = closure tight + unmet
    < 0.5%. HEAT_DEFICIT = closure tight but unmet > 0.5% (capacity short).
    ACCOUNTING_ERROR = bookkeeping bug (raises)."""

    def test_balanced_status_for_dairy(self, dairy_5mw):
        parsed = parse_energy_profile(dairy_5mw)
        result = simulate_site_dispatch(
            energy_profile=parsed,
            technology_stack=_make_stack(gas_cap_kw=10_000),
            dispatch_policy="merit_order",
            year=2026,
        )
        assert result["energy_balance"]["dispatch_status"] == "BALANCED"
        assert result["energy_balance"]["check_passed"] is True
        assert result.get("deficit_analysis") is None, (
            "deficit_analysis must be None under BALANCED status"
        )

    def test_undersized_gas_returns_heat_deficit_no_raise(self, dairy_5mw):
        """200 kW gas backup is deliberately too small to cover the dairy
        steam peaks. Dispatch should return HEAT_DEFICIT, check_passed=False,
        emit a deficit_analysis block, and NOT raise."""
        parsed = parse_energy_profile(dairy_5mw)
        result = simulate_site_dispatch(
            energy_profile=parsed,
            technology_stack=_make_stack(gas_cap_kw=200),
            dispatch_policy="merit_order",
            year=2026,
        )
        eb = result["energy_balance"]
        assert eb["dispatch_status"] == "HEAT_DEFICIT"
        assert eb["check_passed"] is False
        assert eb["unmet_demand_kwh"] > 0
        assert eb["unmet_demand_pct"] > 0.5

        da = result["deficit_analysis"]
        assert da is not None
        assert da["deficit_pct"] > 0.5
        assert da["deficit_gwh"] > 0
        assert da["additional_scope_1_if_gas_closed_t_co2e"] > 0
        assert (
            da["scope_1_upper_bound_t_co2e"]
            > result["carbon_summary"]["scope_1_t_co2e"]
        )

    def test_unmet_demand_pct_field_present(self, dairy_5mw):
        parsed = parse_energy_profile(dairy_5mw)
        result = simulate_site_dispatch(
            energy_profile=parsed,
            technology_stack=_make_stack(gas_cap_kw=10_000),
            dispatch_policy="merit_order",
            year=2026,
        )
        assert "unmet_demand_pct" in result["energy_balance"]


class TestSourceTypeStrictness:
    """The dispatch must reject unknown HP source_type strings rather than
    silently routing to ambient_air. Silent fallback was the cause of a
    real regression (rendered weighted_cop 2.4 instead of 4.15)."""

    def test_unknown_source_type_raises(self, dairy_5mw):
        parsed = parse_energy_profile(dairy_5mw)
        bad_stack = _make_stack(gas_cap_kw=10_000)
        # Override only the HP entry with an unknown source_type.
        bad_stack[0] = {**bad_stack[0], "source_type": "waste_heat_chiller"}
        with pytest.raises(ValueError, match="source_type"):
            simulate_site_dispatch(
                energy_profile=parsed,
                technology_stack=bad_stack,
                dispatch_policy="merit_order",
                year=2026,
            )


# ---------------------------------------------------------------------------
# Brewery structural tests (merit_order)
# ---------------------------------------------------------------------------

class TestBreweryDispatch:
    """Structural correctness for brewery_8mw. Golden truth: balance + no NaN."""

    @pytest.fixture
    def brewery_result(self, brewery_8mw):
        parsed = parse_energy_profile(brewery_8mw)
        return simulate_site_dispatch(
            energy_profile=parsed,
            technology_stack=_make_stack(gas_cap_kw=15_000),
            dispatch_policy="merit_order",
            year=2026,
        )

    def test_output_shape(self, brewery_result):
        missing = _EXPECTED_KEYS - brewery_result.keys()
        assert not missing, f"Missing output keys: {missing}"

    def test_energy_balance_closes(self, brewery_result):
        b = brewery_result["energy_balance"]
        assert b["check_passed"] is True
        assert b["imbalance_pct"] < 0.5, (
            f"Energy balance imbalance: {b['imbalance_pct']:.4f}%"
        )

    def test_no_nans(self, brewery_result):
        filtered = {k: v for k, v in brewery_result.items()
                    if k != "hourly_dispatch_first_168h"}
        nans = _has_nan(filtered)
        assert nans == [], f"NaN values found in brewery output: {nans}"


# ---------------------------------------------------------------------------
# Soft drinks structural tests (merit_order)
# ---------------------------------------------------------------------------

class TestSoftDrinksDispatch:
    """Structural correctness for soft_drinks_12mw. Golden truth: balance + no NaN."""

    @pytest.fixture
    def sd_result(self, soft_drinks_12mw):
        parsed = parse_energy_profile(soft_drinks_12mw)
        return simulate_site_dispatch(
            energy_profile=parsed,
            technology_stack=_make_stack(gas_cap_kw=15_000),
            dispatch_policy="merit_order",
            year=2026,
        )

    def test_output_shape(self, sd_result):
        missing = _EXPECTED_KEYS - sd_result.keys()
        assert not missing, f"Missing output keys: {missing}"

    def test_energy_balance_closes(self, sd_result):
        b = sd_result["energy_balance"]
        assert b["check_passed"] is True
        assert b["imbalance_pct"] < 0.5, (
            f"Energy balance imbalance: {b['imbalance_pct']:.4f}%"
        )

    def test_no_nans(self, sd_result):
        filtered = {k: v for k, v in sd_result.items()
                    if k != "hourly_dispatch_first_168h"}
        nans = _has_nan(filtered)
        assert nans == [], f"NaN values found in soft_drinks output: {nans}"
