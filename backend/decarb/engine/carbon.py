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
    # UK ETS: large stationary combustion (>20 MW thermal) or specific activities
    # Many food & drink and chemicals sites NOT in ETS but increasingly in expanded scope discussion
    ets_assessment = {
        "in_uk_ets": site_in_uk_ets,
        "ets_allowance_estimate_t_co2e": scope1["total_t_co2e"] if site_in_uk_ets else 0,
        "note": (
            "If in UK ETS, free allocation typically covers ~80% of historic emissions; "
            "balance bought at auction. Forward UK ETS price ~£60-90/t (2026). "
            "Confirm scope via UK ETS Operator's Guide."
        ),
    }

    # SECR: applies to large companies + quoted companies + LLPs
    secr_assessment = {
        "secr_reportable": site_secr_reportable,
        "intensity_metric_required": True if site_secr_reportable else False,
        "note": (
            "If SECR-reportable: must disclose Scope 1, Scope 2 (location-based), "
            "intensity metric, and energy-efficiency actions. "
            "Reference: Companies (Directors' Report) and Limited Liability Partnerships "
            "(Energy and Carbon Report) Regulations 2018."
        ),
    }

    # CCA: Climate Change Agreement — sector-specific energy-efficiency targets
    cca_assessment = {
        "cca_subsector": cca_subsector,
        "applies": cca_subsector is not None,
        "note": (
            "If site is in a CCA: Climate Change Levy discount applies (95% on electricity, "
            "100% on gas in some sectors). Targets typically tighten at 2 yr intervals. "
            "Achievement usually energy-intensity (kWh/tonne). "
            "Reference: HMRC CCL guidance, sector trade body."
            if cca_subsector else "No CCA — full CCL liability."
        ),
    }

    # CBAM (UK & EU): only material if exporting CBAM-listed goods
    cbam_assessment = {
        "cbam_exposed": cbam_exposed,
        "note": (
            "CBAM-exposed: embedded emissions in exported goods reportable to EU CBAM "
            "(transitional 2023-2025, full from 2026); UK CBAM regime starts 2027. "
            "Verified emissions disclosure required; eventual financial obligation."
            if cbam_exposed else "Not CBAM-exposed — no emissions border adjustment."
        ),
    }

    # CCL (Climate Change Levy)
    ccl_main_rates_2026 = {
        "electricity_p_per_kwh": 0.775,
        "natural_gas_p_per_kwh": 0.388,
        "lpg_p_per_kg": 1.241,
    }
    ccl_liability_gbp = (
        elec_kwh * ccl_main_rates_2026["electricity_p_per_kwh"] / 100
        + gas_kwh * ccl_main_rates_2026["natural_gas_p_per_kwh"] / 100
    )
    if cca_subsector:
        ccl_liability_gbp *= 0.10  # rough — discount varies
    ccl_assessment = {
        "annual_ccl_liability_gbp_estimate": round(ccl_liability_gbp, 0),
        "main_rates_used": ccl_main_rates_2026,
        "discount_applied": 0.90 if cca_subsector else 0.0,
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
        ),
    }
