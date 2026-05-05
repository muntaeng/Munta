"""Tests for dispatch.simulate_site_dispatch against the 3 golden sites.

Golden test fixture (dairy_5mw) — physically honest:
  Technology stack respects the 5 K LMTD margin between HP sink and end-use
  supply temperature (steam 175°C, hot_water 85°C, cooling 2°C). A 75°C-sink
  HP cannot serve 175°C steam — that fiction was the old fixture's flaw and
  is now caught by the dispatch sink-temperature guard.

    - 1 MW NH3 heat pump, waste-heat source 35°C → 90°C sink, serves ['hot_water']
      (90°C ≥ 85°C + 5 K LMTD). COP_net ~3.09 at this lift (CoolProp).
    - 4 MW electrode boiler, serves ['steam'] (175°C achievable for any electric
      resistance heater; SRMC 5.05 p/kWh off-peak vs gas 5.29 p/kWh → wins off-peak).
    - 8 MWh thermal storage, serves ['steam','hot_water'] (off-peak charging).
    - 10 MW retained gas backup, serves ['steam','hot_water'] (matches site:
      6 MW primary + 4 MW backup).
  Policy: merit_order (default) — cost-first dispatch.

Honest gas-displacement expectation:
  Under merit_order with this stack, hot-water demand (~7 GWh/yr) is fully
  HP-served, steam (28 GWh/yr) is EB off-peak + gas peak. Gas displacement
  drops vs the old fixture's headline ~44% to a more honest ~15–30% — the
  difference quantifies how much credit the previous fixture took for
  thermodynamically infeasible HP→steam attribution.
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
    Canonical, thermodynamically honest electrification stack.

    HP: NH3 waste-heat-source 35°C, **90°C sink, serves only hot_water**
        (90°C ≥ 85°C + 5 K LMTD margin per CIBSE AM17 / BS EN 14825).
        Capacity 1 MW thermal — covers the ~800 kW average hot-water load
        with TES smoothing and HP runs ~24/7.
    EB: 4 MW resistive, 99% efficiency. Steam-only.
    TES: 8 MWh sensible-heat tank, 92% round-trip, 0.05%/hr standing loss.
    Gas: retained backup, gas_cap_kw, 85% efficiency.

    The previous fixture (HP sink=75°C, serves both steam+hot_water) was
    rejected by the dispatch sink-temperature guard for crediting the HP
    with 175°C steam delivery it could not physically produce.
    """
    return [
        {
            "type": "heat_pump",
            "id": "hp_1",
            "capacity_kw_thermal": 1000,
            "refrigerant": "Ammonia",
            "compressor_type": "screw",
            "source_type": "waste_heat",
            "source_temp_c": 35.0,           # existing NH3 chiller condenser
            "sink_temp_c": 90.0,             # ≥ hot_water 85°C + 5 K LMTD margin
            "serves_end_uses": ["hot_water"],
        },
        {
            "type": "electrode_boiler",
            "id": "eb_1",
            "capacity_kw": 4000,
            "efficiency": 0.99,
            "serves_end_uses": ["steam"],
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
        HP serves hot_water only (~7 GWh/yr) under the honest canonical stack;
        EB picks up steam off-peak. Under merit_order, gas displacement lands
        in the 20–35% band — lower than the previous fixture's 35–55% headline,
        because the old fixture credited the 75°C-sink HP with 175°C steam
        delivery (rejected by the v0.2 sink-temperature guard).

        Upper bound 35%: displacement > 35% under pure merit_order with this
        stack would suggest the EB is dispatching during peak, which the
        EB-offpeak test would also catch.
        """
        disp = dairy_result["annual_summary"]["gas_displacement_pct"]
        assert 20 <= disp <= 35, (
            f"Gas displacement {disp:.1f}% outside expected range 20–35% for merit_order"
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
        """HP weighted COP under canonical merit_order dispatch must land
        in the 35→90°C NH3-screw band. CoolProp gives COP_net ≈ 3.09 at
        this lift; allow 2.95–3.25 to absorb minor part-load / ambient
        smearing. Drops below this if dispatch silently routes the waste-
        heat HP to ambient_air mode (the regression that produced 2.4)."""
        hp = next(
            u for u in dairy_result["equipment_utilisation"]
            if u["tech_type"] == "heat_pump"
        )
        assert 2.95 <= hp["weighted_cop"] <= 3.25, (
            f"HP weighted_cop {hp['weighted_cop']} outside 2.95–3.25 band "
            "for canonical NH3 35→90°C screw — investigate."
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


class TestUnmetDemandAggregation:
    """B3: per-hour unmet_demand warnings are aggregated into a single
    summary at module exit. Multiple hours of deficit must produce exactly
    ONE warning entry with code='unmet_demand' carrying total_unmet_kwh,
    n_unmet_hours, peak_unmet_kw, representative_hours fields."""

    def test_undersized_stack_emits_single_aggregated_warning(self, dairy_5mw):
        parsed = parse_energy_profile(dairy_5mw)
        result = simulate_site_dispatch(
            energy_profile=parsed,
            technology_stack=_make_stack(gas_cap_kw=200),
            dispatch_policy="merit_order",
            year=2026,
        )
        unmet_warnings = [
            w for w in result["warnings"] if w.get("code") == "unmet_demand"
        ]
        assert len(unmet_warnings) == 1, (
            f"expected exactly 1 aggregated unmet_demand warning, got "
            f"{len(unmet_warnings)} — per-hour spam was not aggregated"
        )
        w = unmet_warnings[0]
        assert w["severity"] == "high"
        assert w["n_unmet_hours"] > 1, (
            "test fixture should produce many unmet hours"
        )
        assert w["total_unmet_kwh"] > 0
        assert w["peak_unmet_kw"] > 0
        assert isinstance(w["representative_hours"], list)
        assert 1 <= len(w["representative_hours"]) <= 3
        # Message text must summarise rather than enumerate.
        msg = w["message"]
        assert "across" in msg
        assert "peaking" in msg
        assert "representative hours" in msg

    def test_balanced_stack_emits_no_unmet_warning(self, dairy_5mw):
        parsed = parse_energy_profile(dairy_5mw)
        result = simulate_site_dispatch(
            energy_profile=parsed,
            technology_stack=_make_stack(gas_cap_kw=10_000),
            dispatch_policy="merit_order",
            year=2026,
        )
        unmet_warnings = [
            w for w in result["warnings"] if w.get("code") == "unmet_demand"
        ]
        assert unmet_warnings == [], (
            "BALANCED dispatch must not emit any unmet_demand warning"
        )


class TestSinkTemperatureGuard:
    """The dispatch must refuse to credit a HP with end-use duty it cannot
    physically deliver: HP.sink_temp_c must clear (end_use.temperature_c +
    5 K LMTD margin) for every end-use in serves_end_uses. Violations are
    high-severity warnings and the offending end-uses are stripped from the
    HP's effective serves list."""

    def _stack_with_hp_serving_steam_at_75c_sink(self) -> list[dict]:
        """A HP at sink=75°C declaring it serves steam (175°C) — physically
        impossible. This is the configuration the old `_make_stack` used."""
        return [
            {
                "type": "heat_pump",
                "id": "hp_misconfigured",
                "capacity_kw_thermal": 2000,
                "refrigerant": "Ammonia",
                "compressor_type": "screw",
                "source_type": "waste_heat",
                "source_temp_c": 35.0,
                "sink_temp_c": 75.0,
                "serves_end_uses": ["steam", "hot_water"],
            },
            {
                "type": "electrode_boiler", "id": "eb_1",
                "capacity_kw": 4000, "efficiency": 0.99,
                "serves_end_uses": ["steam", "hot_water"],
            },
            {
                "type": "gas_boiler", "id": "gas_1",
                "capacity_kw": 10_000, "efficiency": 0.85,
                "serves_end_uses": ["steam", "hot_water"],
            },
        ]

    def test_misconfigured_hp_raises_high_severity_warning(self, dairy_5mw):
        parsed = parse_energy_profile(dairy_5mw)
        stack = self._stack_with_hp_serving_steam_at_75c_sink()
        result = simulate_site_dispatch(
            energy_profile=parsed,
            technology_stack=stack,
            dispatch_policy="merit_order",
            year=2026,
        )
        warnings = result["warnings"]
        sink_warnings = [
            w for w in warnings if w.get("code") == "hp_sink_too_cold_for_end_use"
        ]
        assert len(sink_warnings) == 1, (
            f"expected 1 hp_sink_too_cold_for_end_use warning, got {len(sink_warnings)}"
        )
        assert sink_warnings[0]["severity"] == "high"
        # Both steam (needs ≥180°C sink) and hot_water (needs ≥90°C sink)
        # exceed the 75°C sink — both must be named in the message.
        msg = sink_warnings[0]["message"]
        assert "steam" in msg
        assert "hot_water" in msg

    def test_misconfigured_hp_becomes_inactive(self, dairy_5mw):
        """Both serves_end_uses are infeasible → HP is fully inactive.
        Equipment utilisation reports zero output and the inactive warning
        fires."""
        parsed = parse_energy_profile(dairy_5mw)
        stack = self._stack_with_hp_serving_steam_at_75c_sink()
        result = simulate_site_dispatch(
            energy_profile=parsed,
            technology_stack=stack,
            dispatch_policy="merit_order",
            year=2026,
        )
        hp = next(
            u for u in result["equipment_utilisation"]
            if u["tech_type"] == "heat_pump"
        )
        assert hp["annual_thermal_output_kwh"] == 0.0
        assert hp["annual_electrical_input_kwh"] == 0.0
        inactive_warnings = [
            w for w in result["warnings"]
            if w.get("code") == "hp_inactive_no_compatible_end_use"
        ]
        assert len(inactive_warnings) == 1
        assert inactive_warnings[0]["severity"] == "high"

    def test_partial_infeasibility_keeps_hp_active(self, dairy_5mw):
        """HP at 90°C sink declares it serves [steam, hot_water]. Steam
        (175°C) is rejected; hot_water (85°C) is fine. HP runs serving
        hot_water; warning fires for the steam strip."""
        parsed = parse_energy_profile(dairy_5mw)
        stack = [
            {
                "type": "heat_pump", "id": "hp_partial",
                "capacity_kw_thermal": 1000,
                "refrigerant": "Ammonia", "compressor_type": "screw",
                "source_type": "waste_heat",
                "source_temp_c": 35.0,
                "sink_temp_c": 90.0,                       # OK for hot_water, not steam
                "serves_end_uses": ["steam", "hot_water"],
            },
            {
                "type": "electrode_boiler", "id": "eb_1",
                "capacity_kw": 4000, "efficiency": 0.99,
                "serves_end_uses": ["steam"],
            },
            {
                "type": "gas_boiler", "id": "gas_1",
                "capacity_kw": 10_000, "efficiency": 0.85,
                "serves_end_uses": ["steam", "hot_water"],
            },
        ]
        result = simulate_site_dispatch(
            energy_profile=parsed,
            technology_stack=stack,
            dispatch_policy="merit_order",
            year=2026,
        )
        sink_warnings = [
            w for w in result["warnings"]
            if w.get("code") == "hp_sink_too_cold_for_end_use"
        ]
        assert len(sink_warnings) == 1
        assert "steam" in sink_warnings[0]["message"]
        assert "hot_water" not in sink_warnings[0]["message"]
        # HP must still run on hot_water duty.
        hp = next(
            u for u in result["equipment_utilisation"]
            if u["tech_type"] == "heat_pump"
        )
        assert hp["annual_thermal_output_kwh"] > 0
        # And the inactive warning must NOT fire.
        inactive_warnings = [
            w for w in result["warnings"]
            if w.get("code") == "hp_inactive_no_compatible_end_use"
        ]
        assert inactive_warnings == []

    def test_canonical_stack_no_sink_warnings(self, dairy_5mw):
        """Honest canonical fixture must not trip the guard."""
        parsed = parse_energy_profile(dairy_5mw)
        result = simulate_site_dispatch(
            energy_profile=parsed,
            technology_stack=_make_stack(gas_cap_kw=10_000),
            dispatch_policy="merit_order",
            year=2026,
        )
        sink_warnings = [
            w for w in result["warnings"]
            if w.get("code")
            in ("hp_sink_too_cold_for_end_use", "hp_inactive_no_compatible_end_use")
        ]
        assert sink_warnings == []


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
