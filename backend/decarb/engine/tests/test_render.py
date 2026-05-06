"""End-to-end tests for `decarb.render.render_report`.

The renderer is pure Jinja2 templating against engine outputs — no
arithmetic. These tests verify:

  1. Numerical traceability — every 4+digit run in the rendered markdown
     either matches a numerical leaf of one of the input dicts (with
     thousands-separator and rounding tolerance) or appears verbatim in
     a string field (e.g. a "BS EN 14825" citation).
  2. Section structure — all 11 expected sections render against each
     of the three golden sites; no NaN strings; no Jinja Undefined
     leaks.
  3. Substantive content — rendered report references the site name,
     the gas baseline, the Scope 1+2 figure, at least one HP COP from
     the dispatch cop_table, and a non-trivial provenance + standards
     register.

The engine modules under test are: parse_energy_profile,
compute_baseline_carbon, screen_technologies, simulate_site_dispatch.
ROADMAP modules (optimise_investment_pathway, monte_carlo_uncertainty,
pinch, safety, grid, reliability) are deliberately not exercised — the
renderer must surface them as ROADMAP placeholders, not synthesise
numbers for them.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from decarb.engine.carbon import compute_baseline_carbon
from decarb.engine.dispatch import simulate_site_dispatch
from decarb.engine.parse import parse_energy_profile
from decarb.engine.pathway import optimise_investment_pathway
from decarb.engine.screen import screen_technologies
from decarb.engine.tests.test_dispatch import _make_stack
from decarb.render import render_report


# ---------------------------------------------------------------------------
# Fixture: run the four engine modules end-to-end, returning the bundle the
# renderer expects. Uses the canonical _make_stack from test_dispatch.py as
# single source of truth — same stack across dispatch and render tests so
# any drift in one module shows up in both test suites.
# ---------------------------------------------------------------------------


def _engine_bundle(
    site: dict[str, Any],
    gas_cap_kw: float = 10_000,
) -> dict[str, Any]:
    parsed = parse_energy_profile(site_brief=site)
    carbon = compute_baseline_carbon(
        annual_balance_kwh=parsed["annual_balance_kwh"],
        year=2026,
        site_secr_reportable=site.get("regulatory", {}).get("secr_reportable", True),
        site_in_uk_ets=site.get("regulatory", {}).get("in_uk_ets", False),
        cca_subsector=site.get("regulatory", {}).get("cca_subsector"),
        cbam_exposed=site.get("regulatory", {}).get("cbam_exposed", False),
    )
    screen = screen_technologies(site_brief=site, energy_profile=parsed)
    dispatch = simulate_site_dispatch(
        energy_profile=parsed,
        technology_stack=_make_stack(gas_cap_kw=gas_cap_kw),
        dispatch_policy="merit_order",
        year=2026,
    )
    return {
        "site_brief": site,
        "parse_result": parsed,
        "carbon_result": carbon,
        "screen_result": screen,
        "dispatch_result": dispatch,
    }


@pytest.fixture
def dairy_bundle(dairy_5mw):
    return _engine_bundle(dairy_5mw)


@pytest.fixture
def brewery_bundle(brewery_8mw):
    return _engine_bundle(brewery_8mw)


@pytest.fixture
def softdrinks_bundle(soft_drinks_12mw):
    return _engine_bundle(soft_drinks_12mw)


@pytest.fixture
def dairy_deficit_bundle(dairy_5mw):
    """Dairy with deliberately undersized 200 kW gas backup → HEAT_DEFICIT."""
    return _engine_bundle(dairy_5mw, gas_cap_kw=200)


# ---------------------------------------------------------------------------
# Numerical traceability helper
# ---------------------------------------------------------------------------


_DIGIT_GROUP = re.compile(r"\d[\d,]*\d|\d")


def _digit_runs(text: str) -> list[str]:
    """Extract digit-runs (with embedded commas as thousand separators stripped),
    returning only those of length ≥ 4 after comma removal."""
    raw = _DIGIT_GROUP.findall(text)
    out: list[str] = []
    for r in raw:
        cleaned = r.replace(",", "")
        if len(cleaned) >= 4:
            out.append(cleaned)
    return out


def _walk_numeric_leaves(obj: Any) -> list[float]:
    """Yield every numeric leaf (int/float, but not bool) reachable in obj."""
    out: list[float] = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_walk_numeric_leaves(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_walk_numeric_leaves(v))
    return out


def _build_haystack(*dicts: dict[str, Any]) -> str:
    """Stringify all input dicts to a haystack containing:

      (a) the raw JSON serialisation (commas stripped) — captures both
          numeric leaves like '8851.34' and citation strings like 'BS EN 14825';
      (b) every numeric leaf rounded to int (covers '14078' for raw 14077.85);
      (c) every numeric leaf rounded to one decimal place (covers '14077.9').

    The renderer formats numbers with the int/round-1dp filters, so the
    rounded variants are what actually appears in the markdown.
    """
    serialised = json.dumps(dicts, default=str).replace(",", "")
    rounded_tokens: list[str] = []
    for n in _walk_numeric_leaves(dicts):
        rounded_tokens.append(str(int(round(n))))
        rounded_tokens.append(f"{n:.1f}")
        rounded_tokens.append(f"{n:.0f}")
        # MWh and GWh conversions also rendered by the template:
        if abs(n) >= 1000:
            rounded_tokens.append(f"{n/1000:.0f}")
            rounded_tokens.append(f"{n/1000:.1f}")
        if abs(n) >= 1_000_000:
            rounded_tokens.append(f"{n/1_000_000:.1f}")
    return serialised + " " + " ".join(rounded_tokens)


# Tokens the renderer adds that aren't from the engine dicts: the generated_at
# timestamp and the engine version. These are control metadata, not data.
_RENDER_METADATA_TOKENS = ("RENDER_TS_TEST",)


def _untraceable_numbers(markdown: str, *dicts: dict[str, Any]) -> list[str]:
    """Return digit-runs in the markdown that don't appear in either:

      (a) the JSON-stringified input dicts, including rounded variants
          of every numeric leaf (integer rounding and 1-decimal rounding,
          plus /1e3 and /1e6 conversions for MWh / GWh display); or
      (b) a citation string within those dicts (e.g. '14825' in
          'BS EN 14825:2022').

    Render metadata (timestamp, engine version) is whitelisted out before
    the check by passing ``timestamp=RENDER_TS_TEST`` to ``render_report``.
    """
    haystack = _build_haystack(*dicts) + " " + " ".join(_RENDER_METADATA_TOKENS)
    return [d for d in _digit_runs(markdown) if d not in haystack]


# ---------------------------------------------------------------------------
# §1 Substantive content tests against dairy_5mw
# ---------------------------------------------------------------------------


class TestDairyEndToEnd:
    def test_renderer_returns_markdown_and_writes_file(self, dairy_bundle, tmp_path):
        result = render_report(**dairy_bundle, output_dir=tmp_path)
        assert result["format"] == "markdown"
        assert result["section_count"] == 11
        assert result["char_count"] > 1500
        assert result["path"] is not None
        path = Path(result["path"])
        assert path.exists()
        assert path.read_text(encoding="utf-8") == result["markdown"]

    def test_contains_site_name(self, dairy_bundle):
        md = render_report(**dairy_bundle, write_file=False)["markdown"]
        assert dairy_bundle["site_brief"]["site_name"] in md

    def test_contains_baseline_gas_in_gwh(self, dairy_bundle):
        """Gas baseline is 38,000,000 kWh = 38.0 GWh — must appear in §2."""
        md = render_report(**dairy_bundle, write_file=False)["markdown"]
        # The renderer formats kWh→GWh with one decimal place; '38.0' must appear.
        assert "38.0" in md

    def test_contains_scope_1_2_figure(self, dairy_bundle):
        """The engine returns ~8,851 tCO2e Scope 1+2 location-based for the
        dairy at 2026 grid intensity. Golden truth is 7,820 tCO2e ± grid
        sensitivity (see test_carbon.py — accepted band 7,200–9,500). The
        rendered report must contain whatever the carbon module returns,
        rounded to integer with thousands separator."""
        carbon = dairy_bundle["carbon_result"]
        s12 = carbon["totals"]["scope_1_2_loc_t_co2e"]
        md = render_report(**dairy_bundle, write_file=False)["markdown"]
        assert f"{int(round(s12)):,}" in md
        # Sanity: engine value must be in the published golden band.
        assert 7_200 < s12 < 9_500

    def test_contains_at_least_one_hp_cop_value(self, dairy_bundle):
        """The dispatch cop_table holds per-degree COP values; at least one
        must be quoted in the report so a reviewer can audit the COP path
        without reading the raw JSON."""
        dispatch = dairy_bundle["dispatch_result"]
        md = render_report(**dairy_bundle, write_file=False)["markdown"]
        cop_values = []
        for hp in dispatch.get("cop_table", []) or []:
            cop_values.extend(hp.get("cop_points", []))
        assert cop_values, "dispatch cop_table empty — engine regression?"
        # The template renders the first and last cop points for each HP.
        first_cop = str(cop_values[0])
        assert first_cop in md, f"COP value {first_cop} not found in report"

    def test_provenance_appendix_non_empty(self, dairy_bundle):
        result = render_report(**dairy_bundle, write_file=False)
        assert result["provenance_entries"] >= 5
        assert "Appendix A — Calculation Provenance" in result["markdown"]

    def test_standards_register_at_least_10_entries(self, dairy_bundle):
        result = render_report(**dairy_bundle, write_file=False)
        assert result["standards_cited_count"] >= 10
        assert "Appendix B — Standards and Sources Cited" in result["markdown"]

    def test_status_badges_present(self, dairy_bundle):
        md = render_report(**dairy_bundle, write_file=False)["markdown"]
        assert "IMPLEMENTED%20v0" in md
        assert "ROADMAP%20v0.2" in md

    def test_no_caveat_when_balanced(self, dairy_bundle):
        """Canonical stack returns dispatch_status=BALANCED → §1 must not
        contain a heat-deficit caveat block."""
        md = render_report(**dairy_bundle, write_file=False)["markdown"]
        assert "heat deficit" not in md.lower()
        assert "Heat-deficit caveat" not in md

    def test_roadmap_modules_marked_not_fabricated(self, dairy_bundle):
        """The renderer must not invent numbers for the unimplemented
        pathway optimiser or grant tools — they appear as ROADMAP."""
        md = render_report(**dairy_bundle, write_file=False)["markdown"]
        # Each ROADMAP section should declare itself as such.
        assert "## §4 Pathway Analysis" in md
        assert "## §6 Funding and Grants" in md
        assert "## §7 Implementation Roadmap" in md
        # And at least one explicit ROADMAP callout in those sections.
        assert md.count("ROADMAP") >= 3


# ---------------------------------------------------------------------------
# §2 Numerical traceability test (the load-bearing one)
# ---------------------------------------------------------------------------


class TestHeatDeficitCaveat:
    """Under HEAT_DEFICIT the renderer must surface the deficit + an
    upper-bound carbon figure in §1; this is the bubble-up rule from the
    Tier A engine fixes."""

    def test_caveat_emitted_under_heat_deficit(self, dairy_deficit_bundle):
        # Sanity: engine must have produced HEAT_DEFICIT for this fixture.
        eb = dairy_deficit_bundle["dispatch_result"]["energy_balance"]
        assert eb["dispatch_status"] == "HEAT_DEFICIT"

        md = render_report(**dairy_deficit_bundle, write_file=False)["markdown"]
        assert "Heat-deficit caveat" in md
        # The upper-bound Scope 1 figure (engine-computed) must appear in the
        # rendered §1, formatted as integer with thousands separator.
        s1_upper = dairy_deficit_bundle["dispatch_result"]["deficit_analysis"][
            "scope_1_upper_bound_t_co2e"
        ]
        assert f"{int(round(s1_upper)):,}" in md, (
            f"upper-bound Scope 1 {s1_upper} not visible in rendered §1"
        )

    def test_caveat_appears_inside_section_1(self, dairy_deficit_bundle):
        """The caveat must be rendered before the §2 header — it's an
        executive-summary disclosure, not a footnote."""
        md = render_report(**dairy_deficit_bundle, write_file=False)["markdown"]
        s1_idx = md.index("## §1 Executive Summary")
        s2_idx = md.index("## §2 Site Baseline")
        caveat_idx = md.index("Heat-deficit caveat")
        assert s1_idx < caveat_idx < s2_idx


class TestNumericalTraceability:
    def test_no_untraceable_4plus_digit_numbers_dairy(self, dairy_bundle):
        md = render_report(
            **dairy_bundle, write_file=False, timestamp="RENDER_TS_TEST"
        )["markdown"]
        bad = _untraceable_numbers(
            md,
            dairy_bundle["site_brief"],
            dairy_bundle["parse_result"],
            dairy_bundle["carbon_result"],
            dairy_bundle["screen_result"],
            dairy_bundle["dispatch_result"],
        )
        assert not bad, (
            f"Untraceable 4+digit numbers in rendered markdown — every such "
            f"number must appear in an engine output dict (as a numeric leaf "
            f"or inside a citation string). Offenders: {bad[:20]}"
        )

    def test_no_untraceable_4plus_digit_numbers_brewery(self, brewery_bundle):
        md = render_report(
            **brewery_bundle, write_file=False, timestamp="RENDER_TS_TEST"
        )["markdown"]
        bad = _untraceable_numbers(
            md,
            brewery_bundle["site_brief"],
            brewery_bundle["parse_result"],
            brewery_bundle["carbon_result"],
            brewery_bundle["screen_result"],
            brewery_bundle["dispatch_result"],
        )
        assert not bad, f"Untraceable numbers (brewery): {bad[:20]}"

    def test_no_untraceable_4plus_digit_numbers_softdrinks(self, softdrinks_bundle):
        md = render_report(
            **softdrinks_bundle, write_file=False, timestamp="RENDER_TS_TEST"
        )["markdown"]
        bad = _untraceable_numbers(
            md,
            softdrinks_bundle["site_brief"],
            softdrinks_bundle["parse_result"],
            softdrinks_bundle["carbon_result"],
            softdrinks_bundle["screen_result"],
            softdrinks_bundle["dispatch_result"],
        )
        assert not bad, f"Untraceable numbers (soft drinks): {bad[:20]}"


# ---------------------------------------------------------------------------
# §3 Structural test against all 3 sites
# ---------------------------------------------------------------------------


EXPECTED_HEADERS = [
    "## §1 Executive Summary",
    "## §2 Site Baseline",
    "## §3 Decarb Options Considered",
    "## §4 Pathway Analysis",
    "## §5 Carbon Trajectory and Regulatory Compliance",
    "## §6 Funding and Grants",
    "## §7 Implementation Roadmap",
    "## §8 Risks and Assumptions",
    "## §9 Key Decisions for Senior Review",
    "## Appendix A — Calculation Provenance",
    "## Appendix B — Standards and Sources Cited",
]


@pytest.mark.parametrize(
    "bundle_fixture",
    ["dairy_bundle", "brewery_bundle", "softdrinks_bundle"],
)
class TestStructureAllSites:
    def test_all_11_section_headers_present(self, bundle_fixture, request):
        bundle = request.getfixturevalue(bundle_fixture)
        md = render_report(**bundle, write_file=False)["markdown"]
        for header in EXPECTED_HEADERS:
            assert header in md, f"missing section header: {header!r}"

    def test_no_nan_strings(self, bundle_fixture, request):
        bundle = request.getfixturevalue(bundle_fixture)
        md = render_report(**bundle, write_file=False)["markdown"]
        # 'nan' is a frequent silent leak in pandas/numpy paths; fail loudly.
        assert "nan" not in md.lower().split()  # whole-token check
        assert "NaN" not in md
        assert "None" not in md  # raw None leak from .get(...) without default

    def test_no_jinja_undefined_leaks(self, bundle_fixture, request):
        bundle = request.getfixturevalue(bundle_fixture)
        md = render_report(**bundle, write_file=False)["markdown"]
        # Jinja's default Undefined renders as '' but error markers leak as
        # 'Undefined' if str() is forced. Belt-and-braces check.
        assert "Undefined" not in md
        assert "{{" not in md and "}}" not in md
        assert "{%" not in md and "%}" not in md


# ---------------------------------------------------------------------------
# Phase 3 of assessment_2026_05_06_fixes — render-side grid-headroom
# consistency. The §4.1a / §4.1b split must be present, and any
# "requires DNO reinforcement" badge must appear only inside §4.1b.
# ---------------------------------------------------------------------------


class TestRenderGridHeadroomConsistency:
    """End-to-end render with the pathway optimiser wired in. The Balanced
    selection rule and ETS / IETF overlay match the regenerate-dairy-report
    script so this test exercises the same render path the GOLDEN reports
    use."""

    @pytest.fixture
    def dairy_with_pathway(self, dairy_5mw):
        parsed = parse_energy_profile(site_brief=dairy_5mw)
        carbon = compute_baseline_carbon(
            annual_balance_kwh=parsed["annual_balance_kwh"],
            year=2026,
            site_secr_reportable=dairy_5mw.get("regulatory", {}).get("secr_reportable", True),
            site_in_uk_ets=dairy_5mw.get("regulatory", {}).get("in_uk_ets", False),
            cca_subsector=dairy_5mw.get("regulatory", {}).get("cca_subsector"),
            cbam_exposed=dairy_5mw.get("regulatory", {}).get("cbam_exposed", False),
        )
        screen = screen_technologies(site_brief=dairy_5mw, energy_profile=parsed)
        dispatch = simulate_site_dispatch(
            energy_profile=parsed,
            technology_stack=_make_stack(),
            dispatch_policy="merit_order",
            year=2026,
        )
        pathway = optimise_investment_pathway(
            site_brief=dairy_5mw,
            energy_profile=parsed,
            screening=screen,
            base_year=2026,
            ets_allowance_price_gbp_per_tco2e=75.0,
            ietf_grant_fraction=0.30,
            pathway_selection_rule="max_reduction_positive_npv",
        )
        return {
            "site_brief": dairy_5mw,
            "parse_result": parsed,
            "carbon_result": carbon,
            "screen_result": screen,
            "dispatch_result": dispatch,
            "pathway_result": pathway,
        }

    def test_section_41a_header_present(self, dairy_with_pathway):
        md = render_report(**dairy_with_pathway, write_file=False)["markdown"]
        assert "§4.1a — Pathways without DNO reinforcement" in md, (
            "§4.1a subheader missing — Phase 3 dual-track render not in place."
        )

    def test_section_41b_header_present(self, dairy_with_pathway):
        md = render_report(**dairy_with_pathway, write_file=False)["markdown"]
        assert "§4.1b — Pathways with DNO reinforcement" in md, (
            "§4.1b subheader missing — Phase 3 dual-track render not in place."
        )

    def test_no_orphan_reinforcement_warnings(self, dairy_with_pathway):
        """Every '⚠️ requires DNO reinforcement decision' marker in the
        rendered output must appear AFTER the §4.1b header. Markers
        elsewhere — in §1, §3.3, §4.1a, the appendices — would be
        orphaned and contradict §3.3 / §4.1a."""
        md = render_report(**dairy_with_pathway, write_file=False)["markdown"]
        marker = "⚠️ requires DNO reinforcement decision"
        b_header = "§4.1b — Pathways with DNO reinforcement"
        b_idx = md.find(b_header)
        assert b_idx > 0, "§4.1b header not found — cannot validate marker placement"
        # Scan for any occurrence of the marker before §4.1b — that's an orphan.
        prefix = md[:b_idx]
        assert marker not in prefix, (
            f"Orphan '{marker}' found before §4.1b header. "
            "Reinforcement warnings must only appear inside §4.1b."
        )

    def test_no_reinforcement_envelope_quoted_in_section_41a(self, dairy_with_pathway):
        """§4.1a must quote the no-reinforcement envelope (kW) so the
        senior reader knows the constraint envelope explicitly."""
        md = render_report(**dairy_with_pathway, write_file=False)["markdown"]
        env = int(dairy_with_pathway["pathway_result"]["no_reinforcement_envelope_kw"])
        # Find §4.1a section
        a_idx = md.find("§4.1a — Pathways without DNO reinforcement")
        b_idx = md.find("§4.1b — Pathways with DNO reinforcement")
        assert 0 < a_idx < b_idx
        section_a = md[a_idx:b_idx]
        # Envelope appears as int kW, e.g. "1000 kW" for dairy.
        assert f"{env} kW" in section_a or f"{env:,} kW" in section_a, (
            f"Envelope ({env} kW) not quoted in §4.1a. Senior reader "
            "needs the explicit constraint number to evaluate the track."
        )


# ---------------------------------------------------------------------------
# Phase 4 of assessment_2026_05_06_fixes — renderer hygiene
# D4: §1 leads with year-15 figure when pathway available
# D5: CCL provenance arithmetic consistency
# ---------------------------------------------------------------------------


import re as _re_phase4


class TestRendererHygienePhase4:
    """D4 and D5 from plan/assessment_2026-05-06.md."""

    @pytest.fixture
    def dairy_with_pathway(self, dairy_5mw):
        parsed = parse_energy_profile(site_brief=dairy_5mw)
        carbon = compute_baseline_carbon(
            annual_balance_kwh=parsed["annual_balance_kwh"],
            year=2026,
            site_secr_reportable=dairy_5mw.get("regulatory", {}).get("secr_reportable", True),
            site_in_uk_ets=dairy_5mw.get("regulatory", {}).get("in_uk_ets", False),
            cca_subsector=dairy_5mw.get("regulatory", {}).get("cca_subsector"),
            cbam_exposed=dairy_5mw.get("regulatory", {}).get("cbam_exposed", False),
        )
        screen = screen_technologies(site_brief=dairy_5mw, energy_profile=parsed)
        dispatch = simulate_site_dispatch(
            energy_profile=parsed,
            technology_stack=_make_stack(),
            dispatch_policy="merit_order",
            year=2026,
        )
        pathway = optimise_investment_pathway(
            site_brief=dairy_5mw,
            energy_profile=parsed,
            screening=screen,
            base_year=2026,
            ets_allowance_price_gbp_per_tco2e=75.0,
            ietf_grant_fraction=0.30,
            pathway_selection_rule="max_reduction_positive_npv",
        )
        return {
            "site_brief": dairy_5mw,
            "parse_result": parsed,
            "carbon_result": carbon,
            "screen_result": screen,
            "dispatch_result": dispatch,
            "pathway_result": pathway,
        }

    # ----- D4 --------------------------------------------------------------

    def test_section_1_leads_with_year_15_when_pathway_present(self, dairy_with_pathway):
        """§1 must lead with the year-15 (horizon-end) figure when a
        pathway result is available, not the year-1 dispatch figure.
        Specifically: the first carbon-reduction sentence in §1 must
        mention the planning horizon ("Over the 15-year planning
        horizon" or similar), not "year-1 of the recommended stack"."""
        md = render_report(**dairy_with_pathway, write_file=False)["markdown"]
        s1_start = md.find("## §1 Executive Summary")
        s2_start = md.find("## §2 Site Baseline")
        assert 0 < s1_start < s2_start
        s1_body = md[s1_start:s2_start]
        assert "year-15" in s1_body or "planning horizon" in s1_body, (
            "§1 must reference the year-15 / planning-horizon figure in "
            "the headline. Got: " + s1_body[:300]
        )
        # The year-15 reduction percentage must appear in §1.
        bal = dairy_with_pathway["pathway_result"]["pathways"]["balanced"]
        red_str = f"{bal['year_15_reduction_pct']}%"
        assert red_str in s1_body, (
            f"§1 must quote the year-15 reduction {red_str}. "
            f"Section: {s1_body[:500]}"
        )

    def test_pathway_record_exposes_year_15_total_carbon(self, dairy_with_pathway):
        """The optimiser must expose `year_15_total_carbon_t_co2e` and
        `baseline_year_0_carbon_t_co2e` so the renderer never computes
        carbon deltas itself."""
        bal = dairy_with_pathway["pathway_result"]["pathways"]["balanced"]
        assert "year_15_total_carbon_t_co2e" in bal
        assert "baseline_year_0_carbon_t_co2e" in bal
        # Sanity: year-15 ≤ baseline (we expect reduction, not increase)
        assert bal["year_15_total_carbon_t_co2e"] < bal["baseline_year_0_carbon_t_co2e"]

    # ----- D5 --------------------------------------------------------------

    def test_ccl_provenance_arithmetic_consistent(self, dairy_with_pathway):
        """Phase 4 / D5: parse the rendered CCL provenance string,
        extract `rate × volume = product` for each fuel, and assert
        |rate × volume - product| < £1. Earlier output failed this for
        the gas line by ~£122 due to display rounding."""
        md = render_report(**dairy_with_pathway, write_file=False)["markdown"]
        # Match e.g. "elec 0.06200 p/kWh × 12,500,000 kWh = £7,750"
        pat = _re_phase4.compile(
            r"(elec|gas)\s+([\d.,]+)\s+p/kWh\s+×\s+([\d.,]+)\s+kWh\s+=\s+£([\d,]+)"
        )
        matches = pat.findall(md)
        assert len(matches) >= 2, (
            f"Expected ≥2 CCL provenance rows (elec + gas); found "
            f"{len(matches)}. Markdown excerpt: "
            + md[md.find("CCL"): md.find("CCL") + 400]
        )
        for fuel, rate_s, vol_s, prod_s in matches:
            rate = float(rate_s.replace(",", ""))
            volume = float(vol_s.replace(",", ""))
            product = float(prod_s.replace(",", ""))
            # Rate is in p/kWh (pence); product is in £. Convert: £ = p × kWh / 100.
            computed = rate * volume / 100.0
            err = abs(computed - product)
            assert err < 1.0, (
                f"CCL {fuel} arithmetic inconsistent: "
                f"{rate} p/kWh × {volume} kWh = computed £{computed:.2f}, "
                f"displayed £{product}, error £{err:.2f}."
            )

    def test_ccl_breakdown_structured_fields_exposed(self, dairy_with_pathway):
        """D5 also requires structured fields on the engine output so
        the renderer (or other consumers) can compose their own prose
        without parsing the human-readable string."""
        ccl = (
            dairy_with_pathway["carbon_result"]
            .get("regulatory_exposure", {})
            .get("ccl")
        )
        assert ccl is not None and "ccl_breakdown" in ccl, (
            "carbon.regulatory_exposure.ccl.ccl_breakdown missing — D5 fix incomplete."
        )
        bd = ccl["ccl_breakdown"]
        for key in (
            "electricity_rate_p_per_kwh", "electricity_volume_kwh",
            "electricity_ccl_gbp",
            "gas_rate_p_per_kwh", "gas_volume_kwh", "gas_ccl_gbp",
        ):
            assert key in bd, f"ccl_breakdown.{key} missing"
