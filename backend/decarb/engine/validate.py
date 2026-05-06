"""validate_pathway — §4.4 of the engine.

Cross-module consistency and arithmetic checks over the full engine
bundle, run before render. Each check is a small function returning a
``check`` dict; the public ``validate_pathway`` aggregates them.

Severities:
  - ``error``   → blocks render (agent loop gates on ``passed``)
  - ``warning`` → reported but does not block (e.g. known reconciliation
                  follow-ups)
  - ``info``    → reported only

The implementation is deliberately lightweight: the validators read
fields already exposed by upstream modules and never re-derive numerical
content. Every check is independently re-runnable from a saved bundle.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check(check_id: str, severity: str, passed: bool, message: str,
           details: dict | None = None) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "severity": severity,
        "passed": bool(passed),
        "message": message,
        "details": details or {},
    }


def _named_pathways(pathway: dict, key: str) -> list[tuple[str, dict]]:
    """Return [(name, record), ...] for a non-None pathway record."""
    out: list[tuple[str, dict]] = []
    pw_set = (pathway or {}).get(key) or {}
    for name, rec in pw_set.items():
        if rec is None:
            continue
        out.append((name, rec))
    return out


# Map action tech_kind → screening category. Actions with tech_kind not
# in this map are always permitted (e.g. waste_heat_recovery is a
# baseline measure auto-included by the optimiser regardless of
# screening).
_ACTION_KIND_TO_CATEGORY = {
    "heat_pump_mid_temp": "heat_pump",
    "heat_pump_high_temp": "heat_pump",
    "heat_pump_med_temp_steam": "heat_pump",
    "electrode_boiler": "electrode_boiler",
    "thermal_storage": "thermal_storage",
}
_ALWAYS_PERMITTED_TECH_KINDS = {"waste_heat_recovery"}


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_discounted_ge_simple_payback(pathway: dict) -> dict[str, Any]:
    """For each named pathway, discounted payback ≥ simple payback (or
    both None, or simple-non-None & discounted-None — the same logic
    the Phase 2 invariant tests encode)."""
    failures: list[dict[str, Any]] = []
    for src in ("pathways_with_reinforcement", "pathways_no_reinforcement"):
        for name, rec in _named_pathways(pathway, src):
            simple = rec.get("simple_payback_years")
            disc = rec.get("discounted_payback_years")
            if simple is None and disc is None:
                continue
            if simple is not None and disc is None:
                continue  # legitimate: discounted never crosses zero
            if simple is None and disc is not None:
                failures.append({"pathway": f"{src}.{name}",
                                 "simple": simple, "discounted": disc,
                                 "reason": "discounted set but simple None"})
                continue
            if disc < simple - 1e-6:
                failures.append({"pathway": f"{src}.{name}",
                                 "simple": simple, "discounted": disc})
    return _check(
        "discounted_ge_simple_payback", "error",
        passed=not failures,
        message=("All pathways satisfy discounted ≥ simple payback."
                 if not failures
                 else f"{len(failures)} pathway(s) violate the payback invariant."),
        details={"failures": failures},
    )


def check_screen_pathway_grid_consistency(pathway: dict) -> dict[str, Any]:
    """No action in any ``pathways_no_reinforcement`` named pathway
    carries ``requires_grid_decision=True``."""
    failures: list[dict[str, Any]] = []
    for name, rec in _named_pathways(pathway, "pathways_no_reinforcement"):
        for a in rec.get("actions", []) or []:
            if a.get("requires_grid_decision"):
                failures.append({"pathway": f"no_reinforcement.{name}",
                                 "tech_id": a.get("tech_id"),
                                 "tech_kind": a.get("tech_kind")})
    return _check(
        "screen_pathway_grid_consistency", "error",
        passed=not failures,
        message=("No-reinforcement pathways are free of requires_grid_decision actions."
                 if not failures
                 else f"{len(failures)} requires_grid_decision action(s) leaked into no-reinforcement pathways."),
        details={"failures": failures},
    )


def check_carbon_balance_year_15(pathway: dict) -> dict[str, Any]:
    """For each named pathway, the y0→y15 reduction ratio derived from
    raw carbon totals matches the reported ``year_15_reduction_pct``
    within 0.5 percentage points."""
    failures: list[dict[str, Any]] = []
    for src in ("pathways_with_reinforcement", "pathways_no_reinforcement"):
        for name, rec in _named_pathways(pathway, src):
            base = rec.get("baseline_year_0_carbon_t_co2e")
            y15 = rec.get("year_15_total_carbon_t_co2e")
            pct = rec.get("year_15_reduction_pct")
            if base is None or y15 is None or pct is None:
                continue
            if base <= 0:
                continue
            derived = (base - y15) / base * 100.0
            if abs(derived - pct) > 0.5:
                failures.append({"pathway": f"{src}.{name}",
                                 "baseline_y0": base, "y15": y15,
                                 "reported_pct": pct,
                                 "derived_pct": round(derived, 3)})
    return _check(
        "carbon_balance_year_15", "error",
        passed=not failures,
        message=("Carbon balance reconciles to year-15 reduction across all named pathways."
                 if not failures
                 else f"{len(failures)} pathway(s) have y15 reduction inconsistent with raw totals."),
        details={"failures": failures},
    )


def check_exec_summary_baseline_consistency(
    baseline_carbon: dict, pathway: dict,
) -> dict[str, Any]:
    """The baseline-y0 number used by §1 of the report (the pathway
    record's ``baseline_year_0_carbon_t_co2e``) and
    ``baseline_carbon.totals.scope_1_2_loc_t_co2e`` should agree to
    within 5%. Fires as a warning — the underlying engine
    reconciliation is a v0.2 ticket."""
    bc_total = (baseline_carbon or {}).get("totals", {}).get(
        "scope_1_2_loc_t_co2e"
    )
    pw_balanced = ((pathway or {}).get("pathways") or {}).get("balanced") or {}
    pw_baseline = pw_balanced.get("baseline_year_0_carbon_t_co2e")
    if bc_total is None or pw_baseline is None or bc_total <= 0:
        return _check(
            "exec_summary_baseline_consistency", "warning",
            passed=True,
            message="Baseline-y0 not available on both sources — skipped.",
            details={"compute_baseline_carbon_t_co2e": bc_total,
                     "pathway_balanced_y0_t_co2e": pw_baseline},
        )
    delta_pct = abs(pw_baseline - bc_total) / bc_total * 100.0
    passed = delta_pct <= 5.0
    return _check(
        "exec_summary_baseline_consistency", "warning",
        passed=passed,
        message=(
            f"Baseline-y0 sources agree to {delta_pct:.1f}% — within 5% tolerance."
            if passed
            else f"Baseline-y0 sources disagree by {delta_pct:.1f}% (>5%): "
                 f"compute_baseline_carbon={bc_total:.1f} t vs pathway={pw_baseline:.1f} t. "
                 "Reconciliation is a v0.2 follow-up."
        ),
        details={"compute_baseline_carbon_t_co2e": bc_total,
                 "pathway_balanced_y0_t_co2e": pw_baseline,
                 "delta_pct": round(delta_pct, 2)},
    )


# Provenance arithmetic patterns
_NUM = r"(\d[\d,]*(?:\.\d+)?)"
_PROV_PAT_PENCE = re.compile(
    rf"{_NUM}\s*p/kWh\s*[×x\*]\s*{_NUM}\s*kWh\s*=\s*£\s*{_NUM}",
    re.IGNORECASE,
)
_PROV_PAT_GENERIC = re.compile(
    rf"£?\s*{_NUM}\s*[×x\*]\s*£?\s*{_NUM}\s*=\s*£?\s*{_NUM}",
)


def _parse_num(s: str) -> float:
    return float(s.replace(",", ""))


def check_provenance_arithmetic_self_consistent(*sources: dict) -> dict[str, Any]:
    """Iterate provenance rows and check parseable arithmetic.

    Patterns:
        <a> p/kWh × <b> kWh = £<c>     # pence-rate × kWh = £
        <a> × <b> = <c>                # generic same-unit multiplication
    """
    failures: list[dict[str, Any]] = []
    parsed = 0
    seen = 0
    for src in sources:
        if not src:
            continue
        for entry in src.get("provenance", []) or []:
            method = (entry or {}).get("method") or ""
            if not method:
                continue
            seen += 1
            matched = False
            for m in _PROV_PAT_PENCE.finditer(method):
                rate_p = _parse_num(m.group(1))
                kwh = _parse_num(m.group(2))
                product_gbp = _parse_num(m.group(3))
                expected = rate_p * kwh / 100.0
                tol = max(1.0, 0.005 * abs(product_gbp))
                if abs(expected - product_gbp) > tol:
                    failures.append({
                        "field": entry.get("field"),
                        "module_method_excerpt": method[:200],
                        "rate_p_per_kwh": rate_p,
                        "volume_kwh": kwh,
                        "stated_gbp": product_gbp,
                        "computed_gbp": round(expected, 2),
                    })
                parsed += 1
                matched = True
            if matched:
                continue
            for m in _PROV_PAT_GENERIC.finditer(method):
                a = _parse_num(m.group(1))
                b = _parse_num(m.group(2))
                c = _parse_num(m.group(3))
                expected = a * b
                tol = max(1.0, 0.005 * abs(c))
                if abs(expected - c) > tol:
                    failures.append({
                        "field": entry.get("field"),
                        "module_method_excerpt": method[:200],
                        "a": a, "b": b, "stated": c,
                        "computed": round(expected, 4),
                    })
                parsed += 1
    return _check(
        "provenance_arithmetic_self_consistent", "error",
        passed=not failures,
        message=(
            f"Parsed {parsed} arithmetic provenance row(s) of {seen}; all consistent."
            if not failures
            else f"{len(failures)} arithmetic provenance row(s) failed self-consistency."
        ),
        details={"parsed": parsed, "seen": seen, "failures": failures},
    )


def check_mc_pathway_consistency(monte_carlo: dict | None,
                                 pathway: dict) -> dict[str, Any]:
    """If MC is present, P50 NPV is within ±20% of the deterministic
    Balanced NPV."""
    if not monte_carlo:
        return _check(
            "mc_pathway_consistency", "warning",
            passed=True,
            message="No Monte Carlo result — skipped.",
            details={},
        )
    p50 = (monte_carlo.get("npv_distribution") or {}).get("p50_gbp")
    pw_balanced = ((pathway or {}).get("pathways") or {}).get("balanced") or {}
    det_npv = pw_balanced.get("npv_gbp")
    if p50 is None or det_npv is None:
        return _check(
            "mc_pathway_consistency", "warning",
            passed=True,
            message="MC P50 or deterministic NPV unavailable — skipped.",
            details={"mc_p50_gbp": p50, "det_npv_gbp": det_npv},
        )
    if det_npv == 0:
        passed = abs(p50) <= 1.0
        delta_pct = None
    else:
        delta_pct = abs(p50 - det_npv) / abs(det_npv) * 100.0
        passed = delta_pct <= 20.0
    return _check(
        "mc_pathway_consistency", "warning",
        passed=passed,
        message=(
            f"MC P50 within {delta_pct:.1f}% of deterministic Balanced NPV."
            if delta_pct is not None and passed
            else (f"MC P50 deviates {delta_pct:.1f}% from deterministic Balanced NPV (>20%)."
                  if delta_pct is not None
                  else "MC P50 vs deterministic NPV check (det_npv=0).")
        ),
        details={"mc_p50_gbp": p50, "det_npv_gbp": det_npv,
                 "delta_pct": (round(delta_pct, 2)
                               if delta_pct is not None else None)},
    )


def check_shortlist_in_pathway_or_excluded(screening: dict,
                                           pathway: dict) -> dict[str, Any]:
    """Every action tech_kind appears (by category) in
    ``screening.shortlist`` ∪ ``screening.excluded_pending_grid_decision``.

    ``waste_heat_recovery`` actions are exempt: the pathway optimiser
    auto-includes WHR as a baseline measure regardless of screening.
    """
    pool: set[str] = set()
    for t in (screening or {}).get("shortlist", []) or []:
        if t.get("category"):
            pool.add(t["category"])
    for t in (screening or {}).get(
        "excluded_pending_grid_decision", []
    ) or []:
        if t.get("category"):
            pool.add(t["category"])
    failures: list[dict[str, Any]] = []
    for src in ("pathways_with_reinforcement", "pathways_no_reinforcement"):
        for name, rec in _named_pathways(pathway, src):
            for a in rec.get("actions", []) or []:
                kind = a.get("tech_kind") or ""
                if kind in _ALWAYS_PERMITTED_TECH_KINDS:
                    continue
                cat = _ACTION_KIND_TO_CATEGORY.get(kind)
                if cat is None:
                    failures.append({"pathway": f"{src}.{name}",
                                     "tech_kind": kind,
                                     "reason": "unmapped tech_kind"})
                    continue
                if cat not in pool:
                    failures.append({"pathway": f"{src}.{name}",
                                     "tech_kind": kind,
                                     "category": cat,
                                     "reason": "category not in shortlist+pending"})
    return _check(
        "shortlist_in_pathway_or_excluded", "error",
        passed=not failures,
        message=("All pathway action tech_kinds map to a screening entry."
                 if not failures
                 else f"{len(failures)} action(s) reference a tech not in screening shortlist or pending-grid set."),
        details={"failures": failures, "screening_categories": sorted(pool)},
    )


def check_standards_register_no_dupes(*sources: dict) -> dict[str, Any]:
    seen_norm: dict[str, list[str]] = {}
    for src in sources:
        if not src:
            continue
        for s in src.get("standards_cited", []) or []:
            norm = re.sub(r"\s+", " ", str(s)).strip()
            seen_norm.setdefault(norm, []).append(str(s))
    dupes = {k: v for k, v in seen_norm.items() if len(v) > 1}
    return _check(
        "standards_register_no_dupes", "info",
        passed=not dupes,
        message=("Standards register has no whitespace-normalised duplicates."
                 if not dupes
                 else f"{len(dupes)} duplicate standard entry name(s) detected."),
        details={"duplicates": dupes},
    )


# Mapping from methodology §3.X / §4.4 section to the engine bundle key
# whose presence indicates "implemented". v0 hard-codes the mapping; a
# v0.2 enhancement is to derive it from a tool registry.
_METHODOLOGY_SECTION_TO_KEY = {
    "3.1": "parse_energy_profile",
    "3.2": "compute_baseline_carbon",
    "3.3": "simulate_site_dispatch",
    # §3.4 multi-stage stays ROADMAP — single-stage handled implicitly.
    "3.5": "screen_technologies",
    "3.6": "optimise_investment_pathway",
    "3.7": "monte_carlo_uncertainty",
    "4.4": "validate_pathway",
}

_METHODOLOGY_HEADER_RE = re.compile(
    r"^###\s+(?P<num>\d+\.\d+)\s+[^▍]+▍\s*`?(?P<badge>[^`]+?)`?\s*$"
)
_METHODOLOGY_44_RE = re.compile(
    r"^###\s+4\.4\s+Self-critique loop\s+▍\s*\*?Status:\s*(?P<badge>[^*]+?)\*?\s*$"
)


def check_methodology_status_matches_engine(
    bundle: dict, methodology_path: Path | str | None = None,
) -> dict[str, Any]:
    """Compare each §3.X / §4.4 status badge in methodology.md against
    the engine bundle's key presence. Mismatch → warning.

    v0 limitation: the §3.X-to-key mapping is hard-coded. A v0.2
    enhancement is to derive it from a tool registry.
    """
    if methodology_path is None:
        methodology_path = (
            Path(__file__).resolve().parents[3]
            / "docs" / "methodology" / "methodology.md"
        )
    methodology_path = Path(methodology_path)
    if not methodology_path.exists():
        return _check(
            "methodology_status_matches_engine", "warning",
            passed=True,
            message=f"methodology.md not found at {methodology_path} — skipped.",
            details={},
        )
    text = methodology_path.read_text(encoding="utf-8")
    mismatches: list[dict[str, Any]] = []
    found: dict[str, str] = {}
    for line in text.splitlines():
        m = _METHODOLOGY_HEADER_RE.match(line)
        if m:
            found[m.group("num")] = m.group("badge").strip()
            continue
        m = _METHODOLOGY_44_RE.match(line)
        if m:
            found["4.4"] = m.group("badge").strip()
    for section, key in _METHODOLOGY_SECTION_TO_KEY.items():
        badge = found.get(section)
        if badge is None:
            continue
        impl_in_engine = key in (bundle or {}) and (bundle or {}).get(key)
        is_implemented_badge = "IMPLEMENTED" in badge
        if is_implemented_badge and not impl_in_engine:
            mismatches.append({"section": section, "badge": badge,
                               "engine_key": key,
                               "reason": "badge IMPLEMENTED but key absent in bundle"})
        elif (not is_implemented_badge) and impl_in_engine:
            mismatches.append({"section": section, "badge": badge,
                               "engine_key": key,
                               "reason": "badge ROADMAP but key present in bundle"})
    return _check(
        "methodology_status_matches_engine", "warning",
        passed=not mismatches,
        message=("Methodology section badges align with engine bundle state."
                 if not mismatches
                 else f"{len(mismatches)} methodology badge(s) disagree with engine bundle."),
        details={"mismatches": mismatches,
                 "checked_sections": sorted(_METHODOLOGY_SECTION_TO_KEY)},
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


_STANDARDS_CITED = [
    "HM Treasury Green Book §A4 (assurance and validation)",
    "ISO 14064-3 — Greenhouse gas verification (cross-module consistency principle)",
]


def validate_pathway(
    *,
    site_brief: dict,
    energy_profile: dict,
    screening: dict,
    baseline_carbon: dict,
    dispatch: dict,
    pathway: dict,
    monte_carlo: dict | None = None,
    methodology_path: Path | str | None = None,
) -> dict[str, Any]:
    """Run cross-module consistency and arithmetic checks over the
    full engine bundle. Returns a dict with ``passed``, ``checks``,
    ``summary``, ``standards_cited`` and ``provenance``.

    ``passed`` is True iff zero error-severity checks failed.
    """
    checks: list[dict[str, Any]] = []

    checks.append(check_discounted_ge_simple_payback(pathway))
    checks.append(check_screen_pathway_grid_consistency(pathway))
    checks.append(check_carbon_balance_year_15(pathway))
    checks.append(check_exec_summary_baseline_consistency(baseline_carbon, pathway))
    checks.append(check_provenance_arithmetic_self_consistent(
        energy_profile, baseline_carbon, screening, dispatch, pathway,
        monte_carlo,
    ))
    checks.append(check_mc_pathway_consistency(monte_carlo, pathway))
    checks.append(check_shortlist_in_pathway_or_excluded(screening, pathway))
    checks.append(check_standards_register_no_dupes(
        energy_profile, baseline_carbon, screening, dispatch, pathway,
        monte_carlo,
    ))
    bundle_for_methodology = {
        "parse_energy_profile": energy_profile,
        "compute_baseline_carbon": baseline_carbon,
        "simulate_site_dispatch": dispatch,
        "screen_technologies": screening,
        "optimise_investment_pathway": pathway,
        "monte_carlo_uncertainty": monte_carlo,
        # validate_pathway is implemented iff this function runs;
        # by being inside it, the key is "present" in the bundle.
        "validate_pathway": True,
    }
    checks.append(check_methodology_status_matches_engine(
        bundle_for_methodology, methodology_path=methodology_path,
    ))

    errors = sum(1 for c in checks if c["severity"] == "error" and not c["passed"])
    warnings = sum(1 for c in checks if c["severity"] == "warning" and not c["passed"])
    infos = sum(1 for c in checks if c["severity"] == "info" and not c["passed"])

    standards_seen: list[str] = []
    seen_set: set[str] = set()
    for src in (energy_profile, baseline_carbon, screening, dispatch,
                pathway, monte_carlo):
        for s in (src or {}).get("standards_cited", []) or []:
            if s not in seen_set:
                seen_set.add(s)
                standards_seen.append(s)
    for s in _STANDARDS_CITED:
        if s not in seen_set:
            seen_set.add(s)
            standards_seen.append(s)

    provenance = [
        {
            "field": c["check_id"],
            "method": (
                f"validate.{c['check_id']} (severity={c['severity']}, "
                f"passed={c['passed']}); see decarb/engine/validate.py."
            ),
            "value": "passed" if c["passed"] else "failed",
        }
        for c in checks
    ]

    return {
        "passed": errors == 0,
        "checks": checks,
        "summary": {"errors": errors, "warnings": warnings, "infos": infos},
        "standards_cited": standards_seen,
        "provenance": provenance,
        "method_reference": (
            "decarb.engine.validate.validate_pathway — methodology §4.4"
        ),
    }


__all__ = [
    "validate_pathway",
    "check_discounted_ge_simple_payback",
    "check_screen_pathway_grid_consistency",
    "check_carbon_balance_year_15",
    "check_exec_summary_baseline_consistency",
    "check_provenance_arithmetic_self_consistent",
    "check_mc_pathway_consistency",
    "check_shortlist_in_pathway_or_excluded",
    "check_standards_register_no_dupes",
    "check_methodology_status_matches_engine",
]
