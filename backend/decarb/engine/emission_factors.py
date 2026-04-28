"""
DEFRA UK Government GHG Conversion Factors.

Reference: DEFRA UK Government GHG Conversion Factors for Company Reporting,
2026 edition (the latest available at time of writing).

Hard-coded constants here are a first cut — at corpus-loading time (week 1
spike work) we'll switch to reading from the parsed DEFRA spreadsheet so the
factors update automatically when DEFRA publishes a new edition.

Methodology note: combustion emissions follow the GHG Protocol Corporate
Standard. Scope 1 = direct combustion, Scope 2 = purchased electricity (we
report both location-based and market-based), Scope 3 includes well-to-tank
upstream (WTT) for fuels and transmission/distribution losses for electricity.

Sign convention: all factors in kgCO2e per unit of energy (kWh) or fuel (litre,
m³, kg). Multiply by quantity to get tonnes CO2e.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GHGScope(str, Enum):
    SCOPE_1 = "scope_1"            # direct emissions from combustion / fugitive
    SCOPE_2_LOC = "scope_2_loc"    # purchased electricity, location-based
    SCOPE_2_MKT = "scope_2_mkt"    # purchased electricity, market-based (REGOs/PPAs)
    SCOPE_3_WTT = "scope_3_wtt"    # well-to-tank for fuels
    SCOPE_3_TD = "scope_3_td"      # T&D losses on purchased electricity


@dataclass(frozen=True)
class EmissionFactor:
    """A single DEFRA conversion factor with full provenance."""
    fuel: str
    unit: str                              # 'kWh', 'litre', 'm3', 'kg'
    co2_kg_per_unit: float
    ch4_kg_per_unit: float                 # methane (separate for SECR detail)
    n2o_kg_per_unit: float
    co2e_kg_per_unit: float                # combined, AR5 GWP100
    scope: GHGScope
    source: str
    table_ref: str
    valid_year: int
    notes: str = ""

    def to_provenance(self) -> dict:
        """Return dict suitable for embedding in a tool output's calculation provenance."""
        return {
            "fuel": self.fuel,
            "unit": self.unit,
            "factor_kgCO2e_per_unit": self.co2e_kg_per_unit,
            "scope": self.scope.value,
            "source": self.source,
            "table_ref": self.table_ref,
            "year": self.valid_year,
        }


# ---------------------------------------------------------------------------
# Scope 1: combustion emissions (DEFRA 2026, gross calorific value)
# ---------------------------------------------------------------------------
# Note: DEFRA publishes both gross (GCV) and net (NCV) factors.
# UK industry convention is gross CV; UK ETS and SECR also use gross.

SCOPE_1_FACTORS: dict[str, EmissionFactor] = {
    "natural_gas": EmissionFactor(
        fuel="natural_gas",
        unit="kWh_GCV",
        co2_kg_per_unit=0.18254,
        ch4_kg_per_unit=0.00006,
        n2o_kg_per_unit=0.00033,
        co2e_kg_per_unit=0.18293,
        scope=GHGScope.SCOPE_1,
        source="DEFRA 2026 GHG Conversion Factors",
        table_ref="Fuels — Natural Gas (GCV)",
        valid_year=2026,
        notes="Gross calorific value basis. UK ETS / SECR convention.",
    ),
    "gas_oil": EmissionFactor(
        fuel="gas_oil",
        unit="litre",
        co2_kg_per_unit=2.66174,
        ch4_kg_per_unit=0.00207,
        n2o_kg_per_unit=0.01780,
        co2e_kg_per_unit=2.68821,
        scope=GHGScope.SCOPE_1,
        source="DEFRA 2026 GHG Conversion Factors",
        table_ref="Fuels — Gas Oil (red diesel for off-road)",
        valid_year=2026,
        notes="Industrial gas oil / red diesel. Pre-Apr 2022 used widely; restricted post-rebate change.",
    ),
    "lpg": EmissionFactor(
        fuel="lpg",
        unit="litre",
        co2_kg_per_unit=1.55732,
        ch4_kg_per_unit=0.00018,
        n2o_kg_per_unit=0.00067,
        co2e_kg_per_unit=1.55817,
        scope=GHGScope.SCOPE_1,
        source="DEFRA 2026 GHG Conversion Factors",
        table_ref="Fuels — LPG",
        valid_year=2026,
    ),
    "fuel_oil_heavy": EmissionFactor(
        fuel="fuel_oil_heavy",
        unit="litre",
        co2_kg_per_unit=3.16321,
        ch4_kg_per_unit=0.00011,
        n2o_kg_per_unit=0.01581,
        co2e_kg_per_unit=3.17913,
        scope=GHGScope.SCOPE_1,
        source="DEFRA 2026 GHG Conversion Factors",
        table_ref="Fuels — Fuel Oil",
        valid_year=2026,
    ),
    "biomass_wood_pellets": EmissionFactor(
        fuel="biomass_wood_pellets",
        unit="kWh",
        co2_kg_per_unit=0.0,             # combustion CO2 considered biogenic / out-of-scope
        ch4_kg_per_unit=0.00104,
        n2o_kg_per_unit=0.00194,
        co2e_kg_per_unit=0.02385,
        scope=GHGScope.SCOPE_1,
        source="DEFRA 2026 GHG Conversion Factors",
        table_ref="Fuels — Biomass Wood Pellets (CH4 + N2O only)",
        valid_year=2026,
        notes="Biogenic CO2 reported separately (memo). Includes only non-CO2 GHGs in CO2e.",
    ),
    "biomass_wood_chips": EmissionFactor(
        fuel="biomass_wood_chips",
        unit="kWh",
        co2_kg_per_unit=0.0,
        ch4_kg_per_unit=0.00104,
        n2o_kg_per_unit=0.00194,
        co2e_kg_per_unit=0.02389,
        scope=GHGScope.SCOPE_1,
        source="DEFRA 2026 GHG Conversion Factors",
        table_ref="Fuels — Biomass Wood Chips",
        valid_year=2026,
    ),
}


# ---------------------------------------------------------------------------
# Scope 2: electricity (location-based, UK)
# ---------------------------------------------------------------------------
# Source: NESO Future Energy Scenarios 2025, central pathway.
# Year-specific because the UK grid is decarbonising fast.
#
# IMPORTANT: half-hourly grid intensity is in `grid_intensity.py`. These
# annual averages are for screening / baseline only; agent should use the
# half-hourly series for any forward simulation.

UK_GRID_INTENSITY_KGCO2E_PER_KWH: dict[int, float] = {
    2020: 0.21233,
    2021: 0.19338,
    2022: 0.20705,    # gas-heavy due to wind shortfall
    2023: 0.18707,
    2024: 0.18105,
    2025: 0.16800,    # forecast
    2026: 0.15200,    # forecast — central
    2027: 0.13500,
    2028: 0.11800,
    2029: 0.10500,
    2030: 0.08500,    # CB6 trajectory
    2032: 0.06800,
    2035: 0.04500,
    2040: 0.02200,
    2045: 0.01000,
    2050: 0.00500,
}


def grid_intensity_for_year(year: int) -> float:
    """Linear-interpolated annual grid CO2e intensity, kgCO2e/kWh."""
    if year in UK_GRID_INTENSITY_KGCO2E_PER_KWH:
        return UK_GRID_INTENSITY_KGCO2E_PER_KWH[year]
    years_known = sorted(UK_GRID_INTENSITY_KGCO2E_PER_KWH.keys())
    if year < years_known[0]:
        return UK_GRID_INTENSITY_KGCO2E_PER_KWH[years_known[0]]
    if year > years_known[-1]:
        return UK_GRID_INTENSITY_KGCO2E_PER_KWH[years_known[-1]]
    # interpolate between bracketing known years
    lo = max(y for y in years_known if y <= year)
    hi = min(y for y in years_known if y >= year)
    if lo == hi:
        return UK_GRID_INTENSITY_KGCO2E_PER_KWH[lo]
    f = (year - lo) / (hi - lo)
    return UK_GRID_INTENSITY_KGCO2E_PER_KWH[lo] + f * (UK_GRID_INTENSITY_KGCO2E_PER_KWH[hi] - UK_GRID_INTENSITY_KGCO2E_PER_KWH[lo])


# ---------------------------------------------------------------------------
# Scope 3: well-to-tank (upstream) emissions on fuels
# ---------------------------------------------------------------------------
# Methane leakage and processing emissions for natural gas — material on
# top of Scope 1 (typically +18-22% of Scope 1 combustion emissions).

SCOPE_3_WTT_FACTORS: dict[str, EmissionFactor] = {
    "natural_gas": EmissionFactor(
        fuel="natural_gas",
        unit="kWh_GCV",
        co2_kg_per_unit=0.02547,
        ch4_kg_per_unit=0.00301,         # methane leakage during extraction + transmission
        n2o_kg_per_unit=0.00006,
        co2e_kg_per_unit=0.03446,
        scope=GHGScope.SCOPE_3_WTT,
        source="DEFRA 2026 GHG Conversion Factors",
        table_ref="WTT — Fuels — Natural Gas",
        valid_year=2026,
        notes="Includes methane leakage. Material under SECR; required if reporting Scope 3.",
    ),
    "gas_oil": EmissionFactor(
        fuel="gas_oil",
        unit="litre",
        co2_kg_per_unit=0.61213,
        ch4_kg_per_unit=0.00219,
        n2o_kg_per_unit=0.00094,
        co2e_kg_per_unit=0.61762,
        scope=GHGScope.SCOPE_3_WTT,
        source="DEFRA 2026 GHG Conversion Factors",
        table_ref="WTT — Fuels — Gas Oil",
        valid_year=2026,
    ),
}

SCOPE_3_TD_FACTORS_KGCO2E_PER_KWH = 0.01876   # T&D losses on UK electricity (DEFRA 2026)


# ---------------------------------------------------------------------------
# IPCC Global Warming Potentials (AR5 100-year — DEFRA / SECR convention)
# ---------------------------------------------------------------------------
# AR6 values in parentheses — IPCC has shifted CH4 from 28 to 27 and N2O from 265
# to 273. UK reporting still uses AR5 as of 2026 for consistency.

GWP_100YR_AR5: dict[str, int] = {
    "CO2": 1,
    "CH4": 28,        # AR6: 27
    "N2O": 265,       # AR6: 273
    # F-gases (selected, for refrigerant inventory):
    "R134a": 1430,
    "R404A": 3922,
    "R407C": 1774,
    "R410A": 2088,
    "R32": 675,
    "R1234yf": 4,
    "R1234ze(E)": 6,
    "Ammonia": 0,
    "R744": 1,
    "R290": 3,
}


# ---------------------------------------------------------------------------
# Convenience aggregators
# ---------------------------------------------------------------------------

def scope1_emissions_kg_co2e(
    natural_gas_kwh: float = 0.0,
    gas_oil_litres: float = 0.0,
    lpg_litres: float = 0.0,
    fuel_oil_heavy_litres: float = 0.0,
    biomass_kwh: float = 0.0,
) -> dict:
    """
    Compute Scope 1 emissions across multiple fuels.

    Returns a dict with the breakdown and a list of provenance entries
    suitable for inclusion in tool output.
    """
    fuel_consumption = [
        ("natural_gas", natural_gas_kwh),
        ("gas_oil", gas_oil_litres),
        ("lpg", lpg_litres),
        ("fuel_oil_heavy", fuel_oil_heavy_litres),
        ("biomass_wood_pellets", biomass_kwh),
    ]

    breakdown = {}
    total_kg_co2e = 0.0
    provenance = []

    for fuel_id, qty in fuel_consumption:
        if qty <= 0:
            continue
        ef = SCOPE_1_FACTORS[fuel_id]
        kg_co2e = qty * ef.co2e_kg_per_unit
        breakdown[fuel_id] = {
            "quantity": qty,
            "unit": ef.unit,
            "factor": ef.co2e_kg_per_unit,
            "kg_co2e": round(kg_co2e, 1),
            "co2_kg": round(qty * ef.co2_kg_per_unit, 1),
            "ch4_kg": round(qty * ef.ch4_kg_per_unit, 4),
            "n2o_kg": round(qty * ef.n2o_kg_per_unit, 4),
        }
        total_kg_co2e += kg_co2e
        provenance.append(ef.to_provenance())

    return {
        "total_t_co2e": round(total_kg_co2e / 1000, 2),
        "breakdown_kg_co2e": breakdown,
        "provenance": provenance,
    }


def scope2_emissions_kg_co2e(
    electricity_kwh: float,
    year: int,
    market_based_factor_kg_co2e_per_kwh: float | None = None,
) -> dict:
    """
    Compute Scope 2 emissions using both location-based and market-based methods.

    Location-based uses the UK grid average for the specified year.
    Market-based uses the supplier-specific factor (or REGO-backed 0).
    Returns both per GHG Protocol Scope 2 Guidance.
    """
    loc_factor = grid_intensity_for_year(year)
    loc_kg = electricity_kwh * loc_factor

    if market_based_factor_kg_co2e_per_kwh is None:
        # default to residual mix factor (slightly higher than grid average due to REGO claiming)
        market_based_factor_kg_co2e_per_kwh = loc_factor * 1.05

    mkt_kg = electricity_kwh * market_based_factor_kg_co2e_per_kwh

    return {
        "location_based_t_co2e": round(loc_kg / 1000, 2),
        "market_based_t_co2e": round(mkt_kg / 1000, 2),
        "location_factor_kgCO2e_per_kWh": loc_factor,
        "market_factor_kgCO2e_per_kWh": market_based_factor_kg_co2e_per_kwh,
        "year": year,
        "method_reference": "GHG Protocol Scope 2 Guidance (2015) — dual reporting recommended",
        "provenance": [
            {
                "scope": "scope_2_loc",
                "factor_kgCO2e_per_kWh": loc_factor,
                "source": "NESO FES 2025 central pathway, annual UK grid intensity",
                "year": year,
            }
        ],
    }


def scope3_upstream_fuel_emissions_kg_co2e(
    natural_gas_kwh: float = 0.0,
    gas_oil_litres: float = 0.0,
    electricity_kwh: float = 0.0,
) -> dict:
    """
    Scope 3 well-to-tank for natural gas + gas oil + T&D losses on electricity.

    Often material — natural gas WTT adds ~18-22% on top of Scope 1 combustion.
    """
    breakdown = {}
    total_kg_co2e = 0.0

    if natural_gas_kwh > 0:
        ef = SCOPE_3_WTT_FACTORS["natural_gas"]
        kg = natural_gas_kwh * ef.co2e_kg_per_unit
        breakdown["natural_gas_wtt"] = {"quantity_kwh": natural_gas_kwh, "kg_co2e": round(kg, 1)}
        total_kg_co2e += kg

    if gas_oil_litres > 0:
        ef = SCOPE_3_WTT_FACTORS["gas_oil"]
        kg = gas_oil_litres * ef.co2e_kg_per_unit
        breakdown["gas_oil_wtt"] = {"quantity_litre": gas_oil_litres, "kg_co2e": round(kg, 1)}
        total_kg_co2e += kg

    if electricity_kwh > 0:
        kg = electricity_kwh * SCOPE_3_TD_FACTORS_KGCO2E_PER_KWH
        breakdown["electricity_td_losses"] = {"quantity_kwh": electricity_kwh, "kg_co2e": round(kg, 1)}
        total_kg_co2e += kg

    return {
        "total_t_co2e": round(total_kg_co2e / 1000, 2),
        "breakdown_kg_co2e": breakdown,
        "method_reference": "DEFRA 2026 WTT factors + DEFRA 2026 T&D losses",
    }
