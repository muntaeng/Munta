"""
Tests for screen_technologies against the 3 golden site fixtures.

IMPORTANT: assertions are made AGAINST the _golden_truth blocks embedded in the
site fixture files (decarb/tests/sites/*.json), NOT against output the
implementation produces.  A test that passes only because the implementation was
run to calibrate it is not a test.

Golden truth rules:
  • expected_shortlist_must_include  — every ID in this list must appear in shortlist
  • expected_shortlist_must_exclude_with_reason — each ID must appear in excluded AND
    the exclusion reason must match the cited rationale:
      - biomass: "contamination" keyword for dairy/brewery;
                 "client" keyword for soft_drinks (no_biomass = True)
      - hydrogen: city name keyword for dairy/brewery (infrastructure ground);
                  "client" keyword for soft_drinks (no_hydrogen = True)
"""
from __future__ import annotations

import pytest

from decarb.engine.screen import screen_technologies


# ---------------------------------------------------------------------------
# Shared output shape expectation
# ---------------------------------------------------------------------------

_EXPECTED_TOP_KEYS = {
    "shortlist", "excluded", "borderline_notes",
    "candidate_count", "shortlist_count", "excluded_count",
    "warnings", "standards_cited", "method_reference", "provenance",
}

_EXPECTED_SHORTLIST_ENTRY_KEYS = {"tech_id", "tech_name", "category"}
_EXPECTED_EXCLUDED_ENTRY_KEYS = {"tech_id", "tech_name", "reason", "failed_axis"}


def _shortlist_ids(result: dict) -> set[str]:
    return {t["tech_id"] for t in result["shortlist"]}


def _pending_grid_ids(result: dict) -> set[str]:
    return {t["tech_id"] for t in result.get("excluded_pending_grid_decision", [])}


def _actionable_ids(result: dict) -> set[str]:
    """Shortlist + pending-grid-decision: the union of tech the screen has
    not vetoed. Pending-grid items are not yet shortlisted but have not been
    excluded on infeasibility grounds — a senior DNO decision moves them
    into the shortlist proper. Golden-truth `must_include` lists predate
    the v0.2 grid filter and assert membership in this union."""
    return _shortlist_ids(result) | _pending_grid_ids(result)


def _excluded_ids(result: dict) -> set[str]:
    return {t["tech_id"] for t in result["excluded"]}


def _exclusion_reason(result: dict, tech_id: str) -> str:
    for entry in result["excluded"]:
        if entry["tech_id"] == tech_id:
            return entry.get("reason", "")
    return ""


# ---------------------------------------------------------------------------
# TestDairyScreen — golden tests (GOLDEN_DAIRY_5MW)
# ---------------------------------------------------------------------------

class TestDairyScreen:
    """
    _golden_truth.expected_shortlist_must_include:
      industrial_heat_pump_mid_temp, industrial_heat_pump_high_temp,
      electrode_boiler_steam, waste_heat_recovery_chiller_to_HW,
      thermal_energy_storage

    _golden_truth.expected_shortlist_must_exclude_with_reason:
      biomass_boiler: "dairy GMP / contamination risk"
      100pc_hydrogen_boiler: "no hydrogen network in Carlisle"
    """

    @pytest.fixture
    def dairy_result(self, dairy_5mw):
        return screen_technologies(dairy_5mw)

    # --- shortlist inclusions (from _golden_truth) ---

    def test_dairy_shortlist_includes_hp_mid_temp(self, dairy_result, dairy_5mw):
        """HP mid-temp must be shortlisted: dairy hot_water at 85°C → mid-temp tier."""
        must_include = dairy_5mw["_golden_truth"]["expected_shortlist_must_include"]
        assert "industrial_heat_pump_mid_temp" in must_include, (
            "Golden truth does not list industrial_heat_pump_mid_temp — check fixture"
        )
        assert "industrial_heat_pump_mid_temp" in _shortlist_ids(dairy_result), (
            "industrial_heat_pump_mid_temp missing from dairy shortlist"
        )

    def test_dairy_shortlist_includes_hp_high_temp(self, dairy_result, dairy_5mw):
        """HP high-temp must be either shortlisted or in the pending-grid
        decision register: dairy steam at 175°C → high-temp tier, but the
        site's 1 MVA headroom against ~1.7 MW estimated electrical demand
        triggers the v0.2 grid filter. Either landing satisfies golden truth."""
        must_include = dairy_5mw["_golden_truth"]["expected_shortlist_must_include"]
        assert "industrial_heat_pump_high_temp" in must_include
        assert "industrial_heat_pump_high_temp" in _actionable_ids(dairy_result), (
            "industrial_heat_pump_high_temp missing from both shortlist and "
            "excluded_pending_grid_decision"
        )

    def test_dairy_shortlist_includes_electrode_boiler(self, dairy_result, dairy_5mw):
        """Electrode boiler must be actionable (shortlist or pending grid)
        for all steam-bearing sites. At dairy_5mw the 4-5 MW electrical
        demand exceeds 1.5× the 1 MVA headroom — pending grid decision."""
        must_include = dairy_5mw["_golden_truth"]["expected_shortlist_must_include"]
        assert "electrode_boiler_steam" in must_include
        assert "electrode_boiler_steam" in _actionable_ids(dairy_result), (
            "electrode_boiler_steam missing from both shortlist and "
            "excluded_pending_grid_decision"
        )

    def test_dairy_excludes_whr_chiller_on_temperature_gate(
        self, dairy_result, dairy_5mw
    ):
        """Issue B: chiller-condensate WHR deliverable sink ~70°C cannot
        serve dairy hot water at 85°C with the 5 K LMTD margin
        (CIBSE AM17, BS EN 14825). simulate_site_dispatch enforces the
        same gate; screen now agrees, so the dud WHR no longer carries
        £150k of orphan capex into every pathway."""
        sids = _shortlist_ids(dairy_result)
        assert "waste_heat_recovery_chiller_to_HW" not in sids, (
            "WHR (chiller→HW) must be excluded from dairy shortlist on "
            "thermodynamic grounds — sink 70°C < hw_supply 85°C + 5 K LMTD"
        )
        excluded = {
            e["tech_id"]: e for e in dairy_result.get("excluded", [])
        }
        assert "waste_heat_recovery_chiller_to_HW" in excluded
        e = excluded["waste_heat_recovery_chiller_to_HW"]
        assert e.get("failed_axis") == "thermodynamic_feasibility", (
            f"WHR exclusion axis: got {e.get('failed_axis')}"
        )

    def test_dairy_shortlist_includes_tes(self, dairy_result, dairy_5mw):
        """TES must be shortlisted for load-shifting capability."""
        must_include = dairy_5mw["_golden_truth"]["expected_shortlist_must_include"]
        assert "thermal_energy_storage" in must_include
        assert "thermal_energy_storage" in _shortlist_ids(dairy_result), (
            "thermal_energy_storage missing from dairy shortlist"
        )

    def test_dairy_shortlist_includes_all_golden_truth(self, dairy_result, dairy_5mw):
        """Every golden-truth must_include tech is at least actionable
        (shortlist or pending grid decision)."""
        must_include = dairy_5mw["_golden_truth"]["expected_shortlist_must_include"]
        missing = set(must_include) - _actionable_ids(dairy_result)
        assert not missing, (
            f"Dairy actionable set missing golden-truth technologies: {missing}\n"
            f"Shortlist: {_shortlist_ids(dairy_result)}\n"
            f"Pending grid: {_pending_grid_ids(dairy_result)}"
        )

    def test_dairy_high_demand_tech_in_pending_grid_register(self, dairy_result):
        """B1: high_temp HP and electrode_boiler_steam exceed 1.5× headroom
        at the dairy site (1 MVA headroom). They must NOT appear in the
        shortlist — they belong in excluded_pending_grid_decision so a
        senior reviewer makes the DNO call before the agent recommends them."""
        pending = _pending_grid_ids(dairy_result)
        shortlist = _shortlist_ids(dairy_result)
        assert "industrial_heat_pump_high_temp" in pending, (
            "high_temp HP must move to pending_grid_decision under 1.5× rule"
        )
        assert "electrode_boiler_steam" in pending, (
            "electrode_boiler_steam must move to pending_grid_decision under 1.5× rule"
        )
        assert "industrial_heat_pump_high_temp" not in shortlist
        assert "electrode_boiler_steam" not in shortlist
        # Each pending entry must carry the reason code and a non-trivial
        # rationale citing the headroom math.
        for entry in dairy_result["excluded_pending_grid_decision"]:
            assert entry.get("pending_reason_code"), entry
            assert "headroom" in entry.get("reason", "").lower()

    # --- exclusions (from _golden_truth) ---

    def test_dairy_biomass_is_excluded(self, dairy_result, dairy_5mw):
        """biomass_boiler must be excluded for dairy per _golden_truth."""
        must_exclude = dairy_5mw["_golden_truth"]["expected_shortlist_must_exclude_with_reason"]
        assert "biomass_boiler" in must_exclude
        assert "biomass_boiler" in _excluded_ids(dairy_result), (
            "biomass_boiler should be in dairy excluded list"
        )

    def test_dairy_biomass_excluded_on_contamination(self, dairy_result, dairy_5mw):
        """
        Golden truth: 'dairy GMP / contamination risk'.
        Exclusion reason must cite contamination or GMP — not just a generic rejection.
        """
        reason = _exclusion_reason(dairy_result, "biomass_boiler").lower()
        assert reason, "biomass_boiler exclusion reason is empty"
        assert "contamination" in reason or "gmp" in reason, (
            f"Dairy biomass exclusion reason must cite 'contamination' or 'GMP' "
            f"(golden truth: 'dairy GMP / contamination risk'). Got: {reason!r}"
        )

    def test_dairy_hydrogen_is_excluded(self, dairy_result, dairy_5mw):
        """100pc_hydrogen_boiler must be excluded for dairy per _golden_truth."""
        must_exclude = dairy_5mw["_golden_truth"]["expected_shortlist_must_exclude_with_reason"]
        assert "100pc_hydrogen_boiler" in must_exclude
        assert "100pc_hydrogen_boiler" in _excluded_ids(dairy_result), (
            "100pc_hydrogen_boiler should be in dairy excluded list"
        )

    def test_dairy_hydrogen_excluded_on_infrastructure(self, dairy_result, dairy_5mw):
        """
        Golden truth: 'no hydrogen network in Carlisle'.
        Exclusion reason must cite Carlisle and hydrogen network infrastructure.
        The dairy brief has no_hydrogen=False, so the exclusion must be on
        infrastructure grounds — NOT client constraint.
        """
        # Verify fixture: no_hydrogen must be False for this test to be meaningful
        assert dairy_5mw["constraints"]["no_hydrogen"] is False, (
            "Fixture changed: no_hydrogen should be False for dairy — update test"
        )
        reason = _exclusion_reason(dairy_result, "100pc_hydrogen_boiler").lower()
        assert reason, "100pc_hydrogen_boiler exclusion reason is empty"
        assert "carlisle" in reason, (
            f"Dairy H2 exclusion must cite 'Carlisle' (location-specific). Got: {reason!r}"
        )
        assert "network" in reason or "pipeline" in reason or "infrastructure" in reason, (
            f"Dairy H2 exclusion must cite infrastructure grounds. Got: {reason!r}"
        )

    # --- output structure ---

    def test_dairy_output_shape(self, dairy_result):
        missing = _EXPECTED_TOP_KEYS - dairy_result.keys()
        assert not missing, f"dairy screen output missing keys: {missing}"

    def test_dairy_shortlist_entries_have_required_keys(self, dairy_result):
        for entry in dairy_result["shortlist"]:
            missing = _EXPECTED_SHORTLIST_ENTRY_KEYS - entry.keys()
            assert not missing, f"Shortlist entry {entry.get('tech_id')} missing keys: {missing}"

    def test_dairy_excluded_entries_have_required_keys(self, dairy_result):
        for entry in dairy_result["excluded"]:
            missing = _EXPECTED_EXCLUDED_ENTRY_KEYS - entry.keys()
            assert not missing, f"Excluded entry {entry.get('tech_id')} missing keys: {missing}"

    def test_dairy_standards_cited_present(self, dairy_result):
        assert len(dairy_result["standards_cited"]) >= 5, "Must cite at least 5 standards"
        full_text = " ".join(dairy_result["standards_cited"])
        assert "BS EN 378" in full_text
        assert "F-Gas" in full_text or "F-gas" in full_text

    def test_dairy_provenance_present(self, dairy_result):
        assert len(dairy_result["provenance"]) > 0, "provenance must not be empty"
        for entry in dairy_result["provenance"]:
            assert "calculation" in entry, f"provenance entry missing 'calculation': {entry}"

    def test_dairy_hp_shortlist_entries_have_flagged_risks(self, dairy_result):
        """Every HP in the shortlist must have at least one flagged risk (refrigerant safety)."""
        hp_entries = [t for t in dairy_result["shortlist"]
                      if t["tech_id"].startswith("industrial_heat_pump")]
        assert hp_entries, "No HPs in shortlist — this test depends on test_dairy_shortlist_includes_all_golden_truth passing"
        for hp in hp_entries:
            assert "flagged_risks" in hp, f"HP entry {hp['tech_id']} missing flagged_risks"
            assert len(hp["flagged_risks"]) > 0, (
                f"HP {hp['tech_id']} has no flagged risks — refrigerant safety risk must be flagged"
            )


# ---------------------------------------------------------------------------
# TestBreweryScreen — golden tests (GOLDEN_BREWERY_8MW)
# ---------------------------------------------------------------------------

class TestBreweryScreen:
    """
    _golden_truth.expected_shortlist_must_include:
      industrial_heat_pump_high_temp, industrial_heat_pump_low_temp_HW,
      electrode_boiler_steam, thermal_energy_storage_hot,
      waste_heat_recovery_wort_cooling, mechanical_vapour_recompression_MVR

    _golden_truth.expected_shortlist_must_exclude_with_reason:
      biomass_boiler: "contamination risk on UK brewery sites"
      100pc_hydrogen_boiler: "no Tadcaster H2 network"
    """

    @pytest.fixture
    def brewery_result(self, brewery_8mw):
        return screen_technologies(brewery_8mw)

    def test_brewery_shortlist_includes_all_golden_truth(self, brewery_result, brewery_8mw):
        must_include = brewery_8mw["_golden_truth"]["expected_shortlist_must_include"]
        missing = set(must_include) - _actionable_ids(brewery_result)
        assert not missing, (
            f"Brewery actionable set missing golden-truth technologies: {missing}\n"
            f"Shortlist: {_shortlist_ids(brewery_result)}\n"
            f"Pending grid: {_pending_grid_ids(brewery_result)}"
        )

    def test_brewery_biomass_excluded_on_contamination(self, brewery_result, brewery_8mw):
        """
        Golden truth: 'particulate / brewing-product contamination risk on UK brewery sites'.
        The brewery brief has no_biomass=False so exclusion is on process compatibility.
        """
        assert brewery_8mw["constraints"]["no_biomass"] is False
        assert "biomass_boiler" in _excluded_ids(brewery_result), (
            "biomass_boiler should be excluded for brewery"
        )
        reason = _exclusion_reason(brewery_result, "biomass_boiler").lower()
        assert "contamination" in reason, (
            f"Brewery biomass exclusion must cite 'contamination'. Got: {reason!r}"
        )

    def test_brewery_hydrogen_excluded_on_infrastructure(self, brewery_result, brewery_8mw):
        """
        Golden truth: 'no Tadcaster H2 network; reassess once HyNet expansion confirmed'.
        The brewery brief has no_hydrogen=False so exclusion must be infrastructure-based.
        """
        assert brewery_8mw["constraints"]["no_hydrogen"] is False
        assert "100pc_hydrogen_boiler" in _excluded_ids(brewery_result), (
            "100pc_hydrogen_boiler should be excluded for brewery"
        )
        reason = _exclusion_reason(brewery_result, "100pc_hydrogen_boiler").lower()
        assert "tadcaster" in reason, (
            f"Brewery H2 exclusion must cite 'Tadcaster'. Got: {reason!r}"
        )
        assert "network" in reason or "pipeline" in reason or "infrastructure" in reason, (
            f"Brewery H2 exclusion must cite infrastructure grounds. Got: {reason!r}"
        )

    def test_brewery_output_shape(self, brewery_result):
        missing = _EXPECTED_TOP_KEYS - brewery_result.keys()
        assert not missing, f"brewery screen output missing keys: {missing}"

    def test_brewery_standards_cited_present(self, brewery_result):
        assert len(brewery_result["standards_cited"]) >= 5


# ---------------------------------------------------------------------------
# TestSoftDrinksScreen — golden tests (GOLDEN_SOFTDRINKS_12MW)
# ---------------------------------------------------------------------------

class TestSoftDrinksScreen:
    """
    _golden_truth.expected_shortlist_must_include:
      industrial_heat_pump_low_temp_hot_water, industrial_heat_pump_med_temp_steam_make_up,
      electrode_boiler_steam, thermal_energy_storage_hot,
      waste_heat_recovery_chiller_to_HW_HUGE, compressed_air_heat_recovery,
      mechanical_vapour_recompression_MVR

    _golden_truth.expected_shortlist_must_exclude_with_reason:
      biomass_boiler: "explicitly excluded by client constraints" (no_biomass=True)
      100pc_hydrogen_boiler: "explicitly excluded by client constraints" (no_hydrogen=True)
    """

    @pytest.fixture
    def sd_result(self, soft_drinks_12mw):
        return screen_technologies(soft_drinks_12mw)

    def test_softdrinks_shortlist_includes_all_golden_truth(self, sd_result, soft_drinks_12mw):
        must_include = soft_drinks_12mw["_golden_truth"]["expected_shortlist_must_include"]
        missing = set(must_include) - _actionable_ids(sd_result)
        assert not missing, (
            f"Soft drinks actionable set missing golden-truth technologies: {missing}\n"
            f"Shortlist: {_shortlist_ids(sd_result)}\n"
            f"Pending grid: {_pending_grid_ids(sd_result)}"
        )

    def test_softdrinks_biomass_excluded_on_client_constraint(self, sd_result, soft_drinks_12mw):
        """
        Golden truth: 'explicitly excluded by client constraints'.
        no_biomass=True in site brief → exclusion reason must cite client constraint.
        """
        assert soft_drinks_12mw["constraints"]["no_biomass"] is True
        assert "biomass_boiler" in _excluded_ids(sd_result), (
            "biomass_boiler should be excluded for soft_drinks"
        )
        reason = _exclusion_reason(sd_result, "biomass_boiler").lower()
        assert "client" in reason or "constraint" in reason or "explicitly" in reason, (
            f"Soft drinks biomass exclusion must cite 'client constraint'. Got: {reason!r}"
        )

    def test_softdrinks_hydrogen_excluded_on_client_constraint(self, sd_result, soft_drinks_12mw):
        """
        Golden truth: 'explicitly excluded by client constraints'.
        no_hydrogen=True in site brief → exclusion reason must cite client constraint.
        """
        assert soft_drinks_12mw["constraints"]["no_hydrogen"] is True
        assert "100pc_hydrogen_boiler" in _excluded_ids(sd_result), (
            "100pc_hydrogen_boiler should be excluded for soft_drinks"
        )
        reason = _exclusion_reason(sd_result, "100pc_hydrogen_boiler").lower()
        assert "client" in reason or "constraint" in reason or "explicitly" in reason, (
            f"Soft drinks H2 exclusion must cite 'client constraint'. Got: {reason!r}"
        )

    def test_softdrinks_whr_huge_not_generic(self, sd_result, soft_drinks_12mw):
        """
        Soft drinks has 10.5 MW of chillers (6.5 + 4 MW) — must generate the _HUGE variant.
        The standard chiller_to_HW variant must NOT appear in the shortlist.
        """
        sids = _shortlist_ids(sd_result)
        assert "waste_heat_recovery_chiller_to_HW_HUGE" in sids, (
            "Large chiller fleet (10.5 MW) must generate HUGE WHR variant"
        )
        assert "waste_heat_recovery_chiller_to_HW" not in sids, (
            "Standard WHR variant should not appear when HUGE variant is generated"
        )

    def test_softdrinks_output_shape(self, sd_result):
        missing = _EXPECTED_TOP_KEYS - sd_result.keys()
        assert not missing

    def test_softdrinks_standards_cited_present(self, sd_result):
        assert len(sd_result["standards_cited"]) >= 5


# ---------------------------------------------------------------------------
# TestScreenInputEdgeCases
# ---------------------------------------------------------------------------

class TestScreenInputEdgeCases:
    def test_empty_brief_returns_warnings(self):
        """Empty site brief must return warnings, not crash."""
        result = screen_technologies({})
        codes = [w["code"] for w in result["warnings"]]
        assert "no_site_brief" in codes

    def test_output_always_has_all_keys(self):
        """Even on empty input, all top-level keys must be present."""
        result = screen_technologies({})
        missing = _EXPECTED_TOP_KEYS - result.keys()
        assert not missing, f"Empty-input result missing keys: {missing}"
