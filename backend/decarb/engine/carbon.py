"""
compute_baseline_carbon — §2 of the engine.

GHG Protocol Corporate Standard compliant. Scope 1 + Scope 2 (location AND
market based) + Scope 3 upstream (well-to-tank for fuels, T&D losses for
electricity).

Output is suitable for direct use in SECR / TCFD reporting and as the
"baseline" against which decarbonisation pathway scenarios are compared.
"""
from __future__ import annotations

from typing import Any

from decarb.engine.emission_factors import (
    grid_intensity_for_year,
    scope1_emissions_kg_co2e,
    scope2_emissions_kg_co2e,
    scope3_upstream_fuel_emissions_kg_co2e,
)


def compute_baseline_carbon(
    annual_balance_kwh: dict[str, float],
    year: int = 2026,
    market_based_factor_kg_co2e_per_kwh: float | None = None,
    site_in_uk_ets: bool = False,
    site_secr_reportable: bool = True,
    cca_subsector: str | None = None,
    cbam_exposed: bool = False,
    annual_revenue_gbp: float | None = None,
) -> dict[str, Any]:
    """
    Compute Scope 1 + 2 + 3 baseline emissions for a site.

    Args:
        annual_balance_kwh: dict from parse_energy_profile output
        year: reporting year (DEFRA factors and grid intensity are time-varying)
        market_based_factor_kg_co2e_per_kwh: supplier-specific or REGO-backed factor
        site_in_uk_ets: site is in UK ETS (typically combustion >20 MW or in Annex I activities)
        site_secr_reportable: large UK company / quoted company / LLP — SECR applies
        cca_subsector: Climate Change Agreement subsector identifier (if applicable)
        cbam_exposed: produces CBAM-listed goods (cement, iron, steel, fertilisers, hydrogen, aluminium)
        annual_revenue_gbp: optional, used for SECR proportionality assessment

    Returns:
        Full GHG inventory + regulatory exposure analysis.
    """
    elec_kwh = float(annual_balance_kwh.get("electricity_kwh", 0))
    gas_kwh = float(annual_balance_kwh.get("natural_gas_kwh", 0))
    oil_litres = float(annual_balance_kwh.get("fuel_oil_litres", 0))
    biomass_kwh = float(annual_balance_kwh.get("biomass_kwh", 0))

    # ---------- Scope 1: combustion ----------
    scope1 = scope1_emissions_kg_co2e(
        natural_gas_kwh=gas_kwh,
        gas_oil_litres=oil_litres,
        biomass_kwh=biomass_kwh,
    )

    # ---------- Scope 2: purchased electricity ----------
    scope2 = scope2_emissions_kg_co2e(
        electricity_kwh=elec_kwh,
        year=year,
        market_based_factor_kg_co2e_per_kwh=market_based_factor_kg_co2e_per_kwh,
    )

    # ---------- Scope 3: upstream WTT + T&D ----------
    scope3 = scope3_upstream_fuel_emissions_kg_co2e(
        natural_gas_kwh=gas_kwh,
        gas_oil_litres=oil_litres,
        electricity_kwh=elec_kwh,
    )

    total_loc = scope1["total_t_co2e"] + scope2["location_based_t_co2e"]
    total_loc_with_s3 = total_loc + scope3["total_t_co2e"]
    total_mkt = scope1["total_t_co2e"] + scope2["market_based_t_co2e"]

    # ---------- Carbon intensity per revenue ----------
    intensity = {}
    if annual_revenue_gbp and annual_revenue_gbp > 0:
        intensity["t_co2e_per_million_gbp_revenue"] = round(
            total_loc * 1_000_000 / annual_revenue_gbp, 1
        )

    # ---------- Baseline carbon trajectory under no-action ----------
    # Useful for comparison vs decarb pathways. Holds fuel use constant,
    # only the grid intensity changes year-on-year.
    trajectory_horizon = 15
    trajectory = []
    for offset in range(trajectory_horizon + 1):
        y = year + offset
        gi = grid_intensity_for_year(y)
        s1_t = scope1["total_t_co2e"]
        s2_t = round(elec_kwh * gi / 1000, 2)
        trajectory.append({"year": y, "scope_1_t_co2e": s1_t, "scope_2_t_co2e": s2_t, "total_t_co2e": round(s1_t + s2_t, 2)})

    # ---------- Regulatory exposure ----------
    # All four registers are resolved against the site's declared state in
    # the brief — no "If in..." templates leak to the renderer. Each `note`
    # is a direct factual statement; auxiliary fields (allowance estimates,
    # references) are populated where applicable.
    if site_in_uk_ets:
        ets_note = (
            f"This site IS in UK ETS scope. Estimated allowance "
            f"requirement {round(scope1['total_t_co2e'])} tCO2e/yr. Free "
            f"allocation typically covers ~80% of historic emissions; the "
            f"balance is bought at auction. Forward UK ETS price 2026 "
            f"range: £60–90/tCO2e. Reference: UK ETS Operator's Guide."
        )
    else:
        ets_note = (
            "This site is NOT in UK ETS scope (combustion below the 20 MW "
            "threshold and not in the regulated activities list). No ETS "
            "allowance liability. Monitor scope expansion proposals "
            "(DESNZ consultations 2024–25) — stationary combustion above "
            "10 MW has been floated for inclusion."
        )
    ets_assessment = {
        "in_uk_ets": site_in_uk_ets,
        "ets_allowance_estimate_t_co2e": (
            scope1["total_t_co2e"] if site_in_uk_ets else 0
        ),
        "note": ets_note,
    }

    if site_secr_reportable:
        secr_note = (
            "This site is SECR-reportable (size thresholds met). Annual "
            "disclosure required of Scope 1, Scope 2 location-based, an "
            "intensity metric (typically tCO2e per unit of production or "
            "per £m turnover), and the energy-efficiency actions taken in "
            "the year. Reference: Companies (Directors' Report) and "
            "Limited Liability Partnerships (Energy and Carbon Report) "
            "Regulations 2018."
        )
    else:
        secr_note = (
            "This site is NOT SECR-reportable (below the size thresholds: "
            "<250 employees, <£36 m turnover, <£18 m balance sheet — any "
            "two). Voluntary disclosure under TCFD or sector-specific "
            "schemes may still be expected by lenders or customers."
        )
    secr_assessment = {
        "secr_reportable": site_secr_reportable,
        "intensity_metric_required": bool(site_secr_reportable),
        "note": secr_note,
    }

    if cca_subsector:
        cca_note = (
            f"This site participates in a Climate Change Agreement under "
            f"sub-sector '{cca_subsector}'. The CCL reduced rate applies "
            f"(see CCL block: ~92% relief on electricity, ~89% on gas, "
            f"per HMRC 2024+). CCA targets typically tighten at 2-year "
            f"intervals; achievement is measured against an energy-"
            f"intensity baseline (kWh per tonne / hectolitre / unit). "
            f"Maintain target compliance to retain the relief. "
            f"Reference: HMRC CCL guidance and sector trade-body CCA."
        )
    else:
        cca_note = (
            "This site does NOT participate in a Climate Change Agreement. "
            "Full main CCL rates apply (no reduced-rate relief). If the "
            "sub-sector has a CCA available, joining is usually material — "
            "see the CCL block for the value of relief at this site."
        )
    cca_assessment = {
        "cca_subsector": cca_subsector,
        "applies": cca_subsector is not None,
        "note": cca_note,
    }

    if cbam_exposed:
        cbam_note = (
            "This site IS CBAM-exposed (produces or exports CBAM-listed "
            "goods: cement, iron, steel, fertilisers, hydrogen, aluminium, "
            "or electricity to the EU). Embedded emissions in exported "
            "goods are reportable to EU CBAM (transitional 2023–2025, "
            "full from January 2026); the UK CBAM regime begins 2027. "
            "Verified-emissions disclosure is required and an eventual "
            "financial obligation applies."
        )
    else:
        cbam_note = (
            "This site is NOT CBAM-exposed (no listed goods exported to "
            "the EU). No CBAM declaration or charge applies. Monitor UK "
            "CBAM (live from 2027) for any sub-sector additions."
        )
    cbam_assessment = {
        "cbam_exposed": cbam_exposed,
        "note": cbam_note,
    }

    # CCL (Climate Change Levy) — main rates 2026 (HMRC).
    ccl_main_rates_2026 = {
        "electricity_p_per_kwh": 0.775,
        "natural_gas_p_per_kwh": 0.388,
    }
    # CCA reduced-rate fractions (HMRC, 2024+, indicative). CCA holders pay
    # the main rate × these fractions. Sub-sector specific in reality;
    # to be replaced with per-scheme values once lookup_grants is wired.
    cca_reduced_fractions = {"electricity": 0.08, "natural_gas": 0.11}

    elec_main = elec_kwh * ccl_main_rates_2026["electricity_p_per_kwh"] / 100.0
    gas_main = gas_kwh * ccl_main_rates_2026["natural_gas_p_per_kwh"] / 100.0
    ccl_gross_gbp = elec_main + gas_main

    if cca_subsector:
        f_elec = cca_reduced_fractions["electricity"]
        f_gas = cca_reduced_fractions["natural_gas"]
        elec_applied = elec_main * f_elec
        gas_applied = gas_main * f_gas
        ccl_applied_gbp = elec_applied + gas_applied
        elec_p_applied = ccl_main_rates_2026["electricity_p_per_kwh"] * f_elec
        gas_p_applied = ccl_main_rates_2026["natural_gas_p_per_kwh"] * f_gas
        ccl_method = (
            f"CCA reduced rates (HMRC 2024+): "
            f"elec {elec_p_applied:.3f} p/kWh × {elec_kwh/1e6:.1f}M kWh = £{elec_applied:,.0f}; "
            f"gas {gas_p_applied:.3f} p/kWh × {gas_kwh/1e6:.1f}M kWh = £{gas_applied:,.0f}."
        )
    else:
        ccl_applied_gbp = ccl_gross_gbp
        ccl_method = (
            f"Main CCL rates (no CCA): "
            f"elec {ccl_main_rates_2026['electricity_p_per_kwh']} p/kWh × "
            f"{elec_kwh/1e6:.1f}M kWh + gas {ccl_main_rates_2026['natural_gas_p_per_kwh']} p/kWh × "
            f"{gas_kwh/1e6:.1f}M kWh."
        )

    ccl_relief_gbp = ccl_gross_gbp - ccl_applied_gbp

    ccl_assessment = {
        "ccl_liability_gbp_year": round(ccl_applied_gbp, 0),
        "ccl_gross_no_cca_gbp_year": round(ccl_gross_gbp, 0),
        "ccl_relief_value_gbp_year": round(ccl_relief_gbp, 0),
        "ccl_method": ccl_method,
        "main_rates_used": ccl_main_rates_2026,
        "cca_reduced_fractions_used": cca_reduced_fractions if cca_subsector else None,
        "cca_applied": cca_subsector is not None,
        # Legacy alias retained until v0.2 readers migrate.
        "annual_ccl_liability_gbp_estimate": round(ccl_applied_gbp, 0),
    }

    return {
        "year": year,
        "scope_1": {
            "t_co2e_year": scope1["total_t_co2e"],
            "breakdown": scope1["breakdown_kg_co2e"],
        },
        "scope_2_location_based": {
            "t_co2e_year": scope2["location_based_t_co2e"],
            "factor_kgCO2e_per_kWh": scope2["location_factor_kgCO2e_per_kWh"],
        },
        "scope_2_market_based": {
            "t_co2e_year": scope2["market_based_t_co2e"],
            "factor_kgCO2e_per_kWh": scope2["market_factor_kgCO2e_per_kWh"],
        },
        "scope_3_upstream_wtt_and_td": {
            "t_co2e_year": scope3["total_t_co2e"],
            "breakdown": scope3["breakdown_kg_co2e"],
        },
        "totals": {
            "scope_1_2_loc_t_co2e": round(total_loc, 2),
            "scope_1_2_3_t_co2e": round(total_loc_with_s3, 2),
            "scope_1_2_mkt_t_co2e": round(total_mkt, 2),
        },
        "intensity": intensity,
        "carbon_trajectory_no_action": trajectory,
        "regulatory_exposure": {
            "uk_ets": ets_assessment,
            "secr": secr_assessment,
            "cca": cca_assessment,
            "cbam": cbam_assessment,
            "ccl": ccl_assessment,
        },
        "method_reference": (
            "GHG Protocol Corporate Standard (revised) + Scope 2 Guidance (2015). "
            "Emission factors: DEFRA UK Government GHG Conversion Factors (current year). "
            "Grid intensity forecast: NESO Future Energy Scenarios 2025 central pathway. "
            "Reporting alignment: SECR, TCFD."
        ),
        "provenance": (
            scope1["provenance"]
            + scope2["provenance"]
            + [{"source": "DEFRA 2026 WTT", "method": scope3["method_reference"]}]
            + [{
                "calculation": "CCL liability",
                "method": ccl_method,
                "rates_source": "HMRC CCL main rates 2026; CCA reduced fractions 2024+",
            }]
        ),
    }
