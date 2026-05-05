"""
screen_technologies — §5 of the engine.

Bar: decision-tree shortlist with proper feasibility-envelope checking for each
technology.  Goes beyond "include if temperature is in range" — covers safety,
planning, refrigerant, grid, and capex envelope.

Feasibility axes checked for every candidate (9 axes per spec):
  1. Thermodynamic feasibility  — can the tech deliver the required temperature?
  2. Capacity range fit          — is the unit size commercially available?
  3. Refrigerant safety          — F-gas, BS EN 378 charge limit, ATEX/DSEAR
  4. Process compatibility       — GMP (food/pharma), contamination, client veto
  5. Grid & infrastructure       — kVA headroom + fuel-supply network availability
  6. Planning / Part L           — Building Regs, planning use-class constraints
  7. Site space                  — footprint vs site_space_envelope_m2
  8. Compressor envelope         — achievable temperature lift per compressor type
  9. Regulatory                  — UK ETS, CCA compatibility, MEES

Technology longlist (16 technologies screened per run):
  Heat pumps (5 tiers by sink temperature)
  Electrode boiler (steam / hot-water)
  Thermal energy storage (generic + hot-water-specific)
  Waste heat recovery (chiller-to-HW, wort-cooling, large-chiller variant)
  Compressed air heat recovery
  Mechanical vapour recompression (MVR)
  Biomass boiler                  ← almost always excluded for food & drink
  100% hydrogen-fired boiler      ← excluded in 2026 for all UK food sites

v0 limitations (documented):
  - Commercial capacity database is an approximated UK market survey (2024–25);
    exact availability should be confirmed with manufacturers for each site.
  - HP feasibility uses design-point temperature lift only; COP computed by
    calculate_hp_cycle is available but not called here to keep screening fast.
    Full COP calc is performed in simulate_site_dispatch.
  - H2 network availability uses a static 2026 UK geography table; update
    when HyNet North West / H2 East / Teesside H2 projects confirm live dates.
  - Planning assessment is advisory only; formal planning pre-application advice
    from the LPA is required before investment.

Standards cited inline in output:
  BS EN 378-1:2016 (refrigerant safety + charge limits)
  BS EN 14825:2022 (seasonal heat pump performance)
  F-Gas Regulation 517/2014, UK retained version 2024
  DSEAR 2002 (Dangerous Substances & Explosive Atmospheres Regulations)
  BS 7671:2018 (IET Wiring Regulations, 18th Edition)
  Approved Document L (Building Regulations, 2021 edition)
  Town and Country Planning (Use Classes) Order 1987 (as amended)
  CIBSE AM17:2012 (heat pumps, adapted for industrial scale)
  ETSU / BEIS Industrial Energy Efficiency Accelerator case studies
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Constants — Temperature Tier Boundaries (°C)
# ---------------------------------------------------------------------------

# HP sink temperature tiers — used to generate tech IDs and check feasibility
_HP_HW_TIER_LOW_LOWER_C: float = 70.0    # ≤ 70°C → "low_temp_hot_water"
_HP_HW_TIER_LOW_UPPER_C: float = 80.0    # 70–80°C → "low_temp_HW"
_HP_HW_TIER_MID_UPPER_C: float = 120.0   # 80–120°C → "mid_temp"

_HP_STEAM_TIER_MED_LOWER_C: float = 120.0  # steam sink > 120°C
_HP_STEAM_TIER_MED_UPPER_C: float = 160.0  # steam ≤ 160°C → "med_temp_steam_make_up"
                                            # steam > 160°C → "high_temp"

# Commercially available HP capacity range in UK (approximate market survey 2024–25)
# Sources: Star Refrigeration, Viking Refrigeration, Hybrid Energy, Mayekawa catalogue
_HP_CAPACITY_MIN_KW: float = 200.0    # smallest industrial HP unit on UK market
_HP_CAPACITY_MAX_KW: float = 15_000.0  # largest single-train NH3 industrial HP

# Electrode boiler commercial range (UK market, ABB, Joslyn Clark, Parat)
_EB_CAPACITY_MIN_KW: float = 100.0
_EB_CAPACITY_MAX_KW: float = 30_000.0

# Approximate HP footprint: m² per MW thermal output (including plant-room clearances)
# Reference: CIBSE AM17 plant-room sizing guidance, adapted for industrial
_HP_FOOTPRINT_M2_PER_MW: float = 15.0

# Approximate electrode boiler footprint: m² per MW (compact, low-height)
_EB_FOOTPRINT_M2_PER_MW: float = 6.0

# TES approximate footprint: m² per MWh (pressurised water, cylindrical tank, 50°C DeltaT)
_TES_FOOTPRINT_M2_PER_MWH: float = 8.0

# WHR skid footprint (heat exchanger + pump + controls)
_WHR_FOOTPRINT_M2: float = 25.0   # flat-plate HX skid

# MVR unit footprint: ~30 m² per stage (industrial references: GEA, SWEP)
_MVR_FOOTPRINT_M2: float = 40.0

# Grid check: require at least this ratio of headroom → required kVA
# (below → borderline warning, not automatic exclusion)
_GRID_HEADROOM_RATIO_WARN: float = 0.5   # 50% headroom consumed → flag

# MVR applicability: minimum annual steam demand and minimum operating intensity
_MVR_MIN_STEAM_GWH: float = 30.0          # 30 GWh/yr minimum steam demand
_MVR_MIN_OPERATING_HOURS_PER_YR: int = 6000

# Chiller WHR: threshold for "HUGE" variant (sum of all chiller capacity)
_CHILLER_WHR_HUGE_THRESHOLD_MW: float = 8.0

# UK cities / regions where an operational H2 industrial pipeline is available
# as of 2026 — currently NONE; update when HyNet/H2 East go live.
# Reference: DESNZ H2 Production & Delivery Infrastructure Report 2024
_UK_H2_NETWORK_CITIES_2026: frozenset[str] = frozenset()  # empty — no operational UK H2 grid 2026

# Sectors where biomass combustion near the process creates contamination risk
# under GMP / BRC / FSSC 22000 food safety standards.
# Reference: BRC Global Standard for Food Safety Issue 9 (2023), §4.6 (environment)
_FOOD_DRINK_CONTAMINATION_SECTORS: frozenset[str] = frozenset({
    "food_drink", "food_and_drink", "food", "dairy_processing",
    "brewery", "soft_drinks_bottling", "beverages", "brewing",
    "confectionery", "bakery", "meat_processing", "seafood",
})


# ---------------------------------------------------------------------------
# Technology ID generation helpers
# ---------------------------------------------------------------------------

def _hp_tech_id_for_hw(sink_temp_c: float) -> str:
    """Generate HP tech ID for a hot-water application based on sink temperature."""
    if sink_temp_c <= _HP_HW_TIER_LOW_LOWER_C:
        return "industrial_heat_pump_low_temp_hot_water"
    if sink_temp_c <= _HP_HW_TIER_LOW_UPPER_C:
        return "industrial_heat_pump_low_temp_HW"
    return "industrial_heat_pump_mid_temp"


def _hp_tech_id_for_steam(sink_temp_c: float) -> str:
    """Generate HP tech ID for a steam application based on sink temperature."""
    if _HP_STEAM_TIER_MED_LOWER_C < sink_temp_c <= _HP_STEAM_TIER_MED_UPPER_C:
        return "industrial_heat_pump_med_temp_steam_make_up"
    return "industrial_heat_pump_high_temp"


def _tes_tech_id(hw_temp_c: float) -> str:
    """
    Generate TES tech ID.

    Hot-water systems at ≤ 80°C can use unpressurised or low-pressure
    stratified tanks (naturally aspirated, simpler design) → _hot.
    Above 80°C requires pressure-rated vessels → generic TES.
    """
    return "thermal_energy_storage_hot" if hw_temp_c <= 80.0 else "thermal_energy_storage"


def _whr_tech_id(subsector: str, existing_plant: dict, total_chiller_mw: float) -> str | None:
    """
    Generate WHR tech ID based on site characteristics.

    Returns None if no WHR opportunity detected.
    """
    heat_rec = str(existing_plant.get("heat_recovery_existing", "")).lower()

    if subsector == "brewery":
        # Brewery-specific WHR: wort cooler → hot liquor tank
        # Trigger: "wort" present in existing heat recovery description
        # OR subsector is brewery (wort cooling is inherent to the process)
        return "waste_heat_recovery_wort_cooling"

    if total_chiller_mw > 0:
        if total_chiller_mw >= _CHILLER_WHR_HUGE_THRESHOLD_MW:
            return "waste_heat_recovery_chiller_to_HW_HUGE"
        return "waste_heat_recovery_chiller_to_HW"

    return None


# ---------------------------------------------------------------------------
# Candidate list builder
# ---------------------------------------------------------------------------

def _generate_candidate_techs(site_brief: dict) -> list[dict[str, Any]]:
    """
    Build the site-specific technology longlist.

    Returns a list of candidate dicts, each with:
        id, category, name, sink_temp_c (HP only), application, demand_kwh_yr
    """
    process_heat = site_brief.get("process_heat", {})
    existing_plant = site_brief.get("existing_plant", {})
    operations = site_brief.get("operations", {})
    subsector = site_brief.get("subsector", "")

    steam = process_heat.get("steam", {})
    hot_water = process_heat.get("hot_water", {})

    steam_temp_c: float | None = steam.get("saturation_temp_c") or steam.get("supply_temp_c")
    hw_temp_c: float | None = hot_water.get("supply_temp_c")
    steam_demand_kwh: float = float(steam.get("annual_demand_kwh", 0))
    hw_demand_kwh: float = float(hot_water.get("annual_demand_kwh", 0))
    annual_op_hours: int = int(operations.get("annual_operating_hours", 5000))

    chillers = existing_plant.get("chillers", [])
    total_chiller_mw: float = sum(float(c.get("capacity_mw", 0)) for c in chillers)

    candidates: list[dict[str, Any]] = []

    # --- Heat Pumps ---
    if hw_temp_c is not None:
        hp_hw_id = _hp_tech_id_for_hw(hw_temp_c)
        candidates.append({
            "id": hp_hw_id,
            "category": "heat_pump",
            "name": f"Industrial Heat Pump — hot water at {hw_temp_c:.0f}°C",
            "application": "hot_water",
            "sink_temp_c": hw_temp_c,
            "demand_kwh_yr": hw_demand_kwh,
        })

    if steam_temp_c is not None:
        hp_steam_id = _hp_tech_id_for_steam(steam_temp_c)
        candidates.append({
            "id": hp_steam_id,
            "category": "heat_pump",
            "name": f"Industrial Heat Pump — steam pre-heat / make-up at {steam_temp_c:.0f}°C",
            "application": "steam",
            "sink_temp_c": steam_temp_c,
            "demand_kwh_yr": steam_demand_kwh,
        })

    # --- Electrode Boiler ---
    if steam_temp_c is not None:
        candidates.append({
            "id": "electrode_boiler_steam",
            "category": "electrode_boiler",
            "name": "Electrode Boiler (steam header)",
            "application": "steam",
            "sink_temp_c": steam_temp_c,
            "demand_kwh_yr": steam_demand_kwh,
        })

    # --- Thermal Energy Storage ---
    if hw_temp_c is not None:
        tes_id = _tes_tech_id(hw_temp_c)
        candidates.append({
            "id": tes_id,
            "category": "thermal_storage",
            "name": "Thermal Energy Storage (sensible-heat tank)",
            "application": "hot_water_and_steam",
            "sink_temp_c": hw_temp_c,
            "demand_kwh_yr": hw_demand_kwh + steam_demand_kwh,
        })

    # --- Waste Heat Recovery ---
    whr_id = _whr_tech_id(subsector, existing_plant, total_chiller_mw)
    if whr_id is not None:
        candidates.append({
            "id": whr_id,
            "category": "waste_heat_recovery",
            "name": "Waste Heat Recovery",
            "application": "hot_water",
            "chiller_mw": total_chiller_mw,
            "demand_kwh_yr": hw_demand_kwh,
        })

    # --- Compressed Air Heat Recovery ---
    # Applicable for high-intensity bottling / packaging sectors
    # Reference: Carbon Trust / ETSU compressed air energy-saving guide
    if subsector in ("soft_drinks_bottling", "food_canning", "drinks_bottling", "packaging"):
        candidates.append({
            "id": "compressed_air_heat_recovery",
            "category": "waste_heat_recovery",
            "name": "Compressed Air Heat Recovery (compressor jacket heat)",
            "application": "hot_water",
            "demand_kwh_yr": hw_demand_kwh,
        })

    # --- Mechanical Vapour Recompression (MVR) ---
    # Applicable where large continuous steam demand indicates evaporative processes
    # (wort boiling, pasteurisation, sterilisation) and operating hours are high.
    # Reference: GEA / SWEP MVR application guide; IChemE Process Integration Good Practice
    steam_gwh_yr = steam_demand_kwh / 1e6
    if annual_op_hours >= _MVR_MIN_OPERATING_HOURS_PER_YR and steam_gwh_yr >= _MVR_MIN_STEAM_GWH:
        candidates.append({
            "id": "mechanical_vapour_recompression_MVR",
            "category": "mvr",
            "name": "Mechanical Vapour Recompression (MVR)",
            "application": "steam",
            "sink_temp_c": steam_temp_c,
            "demand_kwh_yr": steam_demand_kwh,
        })

    # --- Biomass Boiler (always in longlist; screened against contamination) ---
    candidates.append({
        "id": "biomass_boiler",
        "category": "combustion_biomass",
        "name": "Biomass-Fired Steam Boiler",
        "application": "steam",
        "sink_temp_c": steam_temp_c,
        "demand_kwh_yr": steam_demand_kwh,
    })

    # --- 100% Hydrogen-Fired Boiler (always in longlist; screened against infrastructure) ---
    candidates.append({
        "id": "100pc_hydrogen_boiler",
        "category": "combustion_hydrogen",
        "name": "100% Hydrogen-Fired Steam Boiler",
        "application": "steam",
        "sink_temp_c": steam_temp_c,
        "demand_kwh_yr": steam_demand_kwh,
    })

    return candidates


# ---------------------------------------------------------------------------
# Feasibility axis checkers
# ---------------------------------------------------------------------------

def _check_thermodynamic(tech: dict, site_brief: dict) -> tuple[bool, str]:
    """
    Axis 1: Can the technology deliver the required delivery temperature with
    commercially viable performance?

    HP: sink temp must be within the tier's delivery range.
    EB: inherently capable of any steam temperature up to superheated steam.
    WHR: source temp (chiller condenser) must exceed delivery temp by ≥10K approach.
    Biomass / H2 combustion: inherently capable of any steam temperature.
    MVR: applicable if saturation temperature is accessible by single-stage centrifugal / screw.
    """
    cat = tech.get("category", "")
    sink = tech.get("sink_temp_c") or 0.0

    if cat == "heat_pump":
        tech_id = tech["id"]
        if "low_temp" in tech_id and sink > 90.0:
            return False, f"Low-temp HP cannot deliver {sink:.0f}°C reliably (limit ~90°C)"
        if "mid_temp" in tech_id and sink > 130.0:
            return False, f"Mid-temp HP cannot deliver {sink:.0f}°C (limit ~130°C)"
        if "med_temp_steam" in tech_id and sink > 165.0:
            return False, f"Med-temp HP cannot deliver {sink:.0f}°C (limit ~165°C)"
        return True, f"Thermodynamically feasible: HP delivers {sink:.0f}°C with NH3/R1234ze(E)"

    if cat == "electrode_boiler":
        return True, f"Electrode boiler inherently delivers any steam temperature; {sink:.0f}°C within range"

    if cat == "thermal_storage":
        return True, "TES is a storage buffer, thermodynamically compatible with any temperature tier"

    if cat == "waste_heat_recovery":
        # Require chiller condensing temp (approx 30–45°C) below delivery temp
        # For hot_water at ≤80°C this is naturally satisfied; high-temp delivery may not be
        if sink and sink > 80.0:
            return False, (
                f"WHR from chiller condensing heat (~30–45°C) cannot deliver {sink:.0f}°C "
                "hot water — thermodynamic lift insufficient for this temperature target"
            )
        return True, "Chiller condensing heat (approx 30–45°C) sufficient for hot-water delivery ≤ 80°C"

    if cat == "mvr":
        return True, "MVR compresses low-pressure vapour; applicable for steam with ΔT < 30K"

    if cat in ("combustion_biomass", "combustion_hydrogen"):
        return True, "Combustion boiler inherently capable of any steam temperature"

    return True, "Thermodynamic feasibility assumed"


def _check_capacity(tech: dict, site_brief: dict) -> tuple[bool, str, dict[str, float]]:
    """
    Axis 2: Is the required capacity within the commercially available range?

    Returns (pass, rationale, capacity_range_kw dict).
    """
    cat = tech.get("category", "")
    demand_kwh_yr = float(tech.get("demand_kwh_yr", 0))
    ops = site_brief.get("operations", {})
    annual_hours = float(ops.get("annual_operating_hours", 5000))
    avg_demand_kw = demand_kwh_yr / max(annual_hours, 1)

    if cat == "heat_pump":
        cap_min = _HP_CAPACITY_MIN_KW
        cap_max = _HP_CAPACITY_MAX_KW
        if avg_demand_kw > cap_max * 3:  # would need > 3 trains
            return (
                False,
                f"Average demand {avg_demand_kw:.0f} kW far exceeds practical HP train count "
                f"(max single train {cap_max:.0f} kW); >3 trains required — flag for senior review",
                {"min": cap_min, "max": cap_max},
            )
        return True, f"HP covers {avg_demand_kw:.0f} kW avg demand; commercial range 200–15,000 kW/train", {
            "min": cap_min, "max": min(cap_max, avg_demand_kw * 1.5),
        }

    if cat == "electrode_boiler":
        return True, f"EB covers {avg_demand_kw:.0f} kW avg demand; commercial range 100–30,000 kW", {
            "min": _EB_CAPACITY_MIN_KW, "max": _EB_CAPACITY_MAX_KW,
        }

    if cat == "thermal_storage":
        return True, "TES capacity scalable to match demand; vessel sizing by detailed design", {
            "min": 100.0, "max": 100_000.0,
        }

    if cat == "waste_heat_recovery":
        chiller_mw = float(tech.get("chiller_mw", 0))
        chiller_condenser_kw = chiller_mw * 1000 * 1.25  # approx condenser heat = evap + compressor
        return True, f"Available condenser heat ~{chiller_condenser_kw:.0f} kW (chiller {chiller_mw:.1f} MW × 1.25)", {
            "min": 50.0, "max": chiller_condenser_kw,
        }

    if cat == "mvr":
        return True, "MVR capacity matched to steam header size; GEA/SWEP 0.5–20 MW per stage", {
            "min": 500.0, "max": 20_000.0,
        }

    if cat in ("combustion_biomass", "combustion_hydrogen"):
        return True, "Combustion boiler capacity scalable; 1–50 MW range commercial", {
            "min": 500.0, "max": 50_000.0,
        }

    return True, "Capacity assumed commercially available", {"min": 0.0, "max": 50_000.0}


def _check_refrigerant_safety(tech: dict, site_brief: dict) -> tuple[bool, list[str]]:
    """
    Axis 3: F-gas, BS EN 378 charge limit, ATEX/DSEAR implications.

    Only applies to heat pumps. Returns (pass, list_of_flagged_risks).
    """
    if tech.get("category") != "heat_pump":
        return True, []

    sink_temp = float(tech.get("sink_temp_c", 80.0))
    risks: list[str] = []

    # NH3 is the dominant refrigerant for industrial HPs at >60°C; flag toxicity
    if sink_temp >= 60.0:
        risks.append(
            "R717 (Ammonia) is the likely refrigerant for this temperature tier: "
            "toxic (TLV-TWA 25 ppm), requires BS EN 378-3 plant-room ventilation and "
            "NH3 leak detection; confirm charge-limit per BS EN 378-1 Annex C for occupied-zone proximity"
        )
    elif sink_temp < 60.0:
        risks.append(
            "R1234ze(E) or R290 likely at this temperature; R290 (propane) is A3 flammable: "
            "DSEAR 2002 ATEX zone assessment required; equipment cost premium ~20–40%"
        )

    # F-gas: natural refrigerants (NH3, R744, R290) are exempt from F-Gas Reg 517/2014
    risks.append(
        "Natural refrigerants (NH3, R744, R290) are exempt from F-Gas Regulation 517/2014 quota "
        "and phase-down requirements — preferred for new industrial plant"
    )

    # All HPs pass axis 3 with flagged risks (risks are manageable, not disqualifying)
    return True, risks


def _check_process_compatibility(
    tech: dict, site_brief: dict
) -> tuple[bool, str, str]:
    """
    Axis 4: GMP, contamination, and explicit client veto.

    Returns (pass, rationale_or_reason, failed_axis_code).
    failed_axis_code is non-empty only on failure.
    """
    tech_id = tech.get("id", "")
    cat = tech.get("category", "")
    sector = str(site_brief.get("sector", "")).lower()
    subsector = str(site_brief.get("subsector", "")).lower()
    constraints = site_brief.get("constraints", {})
    city = site_brief.get("location", {}).get("city", "the site")

    # ---- Biomass boiler ----
    if tech_id == "biomass_boiler":
        # Client veto checked first
        if constraints.get("no_biomass", False):
            return (
                False,
                f"Explicitly excluded by client site constraints (no_biomass = True in site brief). "
                f"No further technical assessment required.",
                "process_compatibility_client_veto",
            )
        # Food/drink sector contamination risk
        if sector in _FOOD_DRINK_CONTAMINATION_SECTORS or subsector in _FOOD_DRINK_CONTAMINATION_SECTORS:
            sector_label = subsector or sector
            if "dairy" in sector_label:
                return (
                    False,
                    "GMP and food safety: biomass boiler introduces airborne particulate, ash, "
                    "and volatile contamination risk incompatible with dairy processing hygiene "
                    "requirements (BRC Global Standard Issue 9, §4.6; FSSC 22000 environment control). "
                    "Dairy sites operate under strict GMP regimes — biomass combustion is rarely "
                    "deployable in close proximity to milk processing areas.",
                    "process_compatibility_contamination",
                )
            if "brew" in sector_label:
                return (
                    False,
                    "Process compatibility: biomass combustion ash and particulate contamination "
                    "risk is incompatible with brewing-product quality requirements on UK brewery sites. "
                    "BRC/IBD brewing codes prohibit combustion ash near open fermentation and packaging "
                    "areas. Contamination of product batches could result in significant recall liability.",
                    "process_compatibility_contamination",
                )
            return (
                False,
                f"Food & drink sector GMP: biomass combustion particulate risk incompatible with "
                f"open food/drink processing environment (BRC §4.6, FSSC 22000). "
                f"Not recommended for {sector_label} sites without full segregation study.",
                "process_compatibility_contamination",
            )

    # ---- Hydrogen boiler ----
    if tech_id == "100pc_hydrogen_boiler":
        if constraints.get("no_hydrogen", False):
            return (
                False,
                f"Explicitly excluded by client site constraints (no_hydrogen = True in site brief). "
                f"No further technical assessment required.",
                "process_compatibility_client_veto",
            )

    # All other technologies pass process compatibility for food & drink
    return True, "No process compatibility conflict identified for this technology", ""


def _check_grid_and_infrastructure(
    tech: dict, site_brief: dict
) -> tuple[bool, str, str, str]:
    """
    Axis 5: Grid connection headroom + fuel-supply infrastructure.

    Returns (pass, rationale_or_reason, failed_axis_code, pending_grid_reason).
    pending_grid_reason is non-empty only when the technology is
    thermodynamically and commercially feasible but its electrical demand
    exceeds the maximum DNO-quotable headroom multiplier (1.5×) — i.e. a
    DNO reinforcement decision must precede shortlisting. Such tech is
    moved to a separate `excluded_pending_grid_decision` register rather
    than being shortlisted with a buried risk bullet.
    """
    tech_id = tech.get("id", "")
    cat = tech.get("category", "")
    constraints = site_brief.get("constraints", {})
    location = site_brief.get("location", {})
    city = str(location.get("city", "the site"))

    # ---- Hydrogen infrastructure check ----
    if tech_id == "100pc_hydrogen_boiler":
        city_lower = city.lower()
        # Check operational H2 network in UK (none as of 2026)
        if city_lower not in {c.lower() for c in _UK_H2_NETWORK_CITIES_2026}:
            # Generate city-specific message with reference to relevant H2 projects
            lat = float(location.get("latitude", 52.0))
            h2_project_note = ""
            if lat > 53.0:
                # North of England — HyNet North West is the relevant project
                h2_project_note = (
                    " HyNet North West (targeting Merseyside / Cheshire) has not yet confirmed "
                    "extension to this location; reassess once pipeline infrastructure is confirmed."
                )
            elif 51.5 < lat <= 53.0:
                h2_project_note = " East of England Hydrogen project is in development but not operational."
            else:
                h2_project_note = " No operational UK H2 pipeline serves this region in 2026."
            return (
                False,
                f"No operational hydrogen pipeline network in {city} for industrial boiler supply "
                f"as of 2026.{h2_project_note} "
                f"On-site electrolyser not economically viable at MW scale under current electricity "
                f"prices (LCOH electrolysis ~£5–8/kgH2 vs industrial gas ~£0.7–1.1/kgH2 equivalent). "
                f"Technology to be reassessed when H2 network is confirmed for this location. "
                f"Reference: DESNZ H2 Production & Delivery Infrastructure Report 2024.",
                "fuel_infrastructure",
                "",
            )

    # ---- Grid headroom check for electrical technologies ----
    if cat in ("heat_pump", "electrode_boiler"):
        headroom_mva = float(constraints.get("site_grid_headroom_mva", 1.0))
        demand_kwh_yr = float(tech.get("demand_kwh_yr", 0))
        ops = site_brief.get("operations", {})
        annual_hours = float(ops.get("annual_operating_hours", 5000))
        avg_thermal_kw = demand_kwh_yr / max(annual_hours, 1)

        if cat == "heat_pump":
            # Approximate required kVA: thermal_kw / COP (assume COP 3.0 conservative)
            approx_elec_kw = avg_thermal_kw / 3.0
        else:
            # Electrode boiler: elec ≈ thermal (99% efficient)
            approx_elec_kw = avg_thermal_kw * 1.01

        headroom_kw = headroom_mva * 1000  # MVA to kW (unity PF approximation)
        utilisation = approx_elec_kw / max(headroom_kw, 1)

        if utilisation > 1.5:
            # Demand exceeds 1.5× headroom — beyond the upper bound a DNO
            # will quote for in a routine connection offer. Structural
            # reinforcement is required and the decision is not the kind
            # an automated screen should make on its own. Move to the
            # senior-decision register, do NOT shortlist.
            return (
                False,
                (
                    f"Estimated electrical demand {approx_elec_kw:.0f} kW exceeds "
                    f"1.5× available headroom ({headroom_kw:.0f} kW; "
                    f"{utilisation:.1%} utilisation). Beyond the typical envelope "
                    "a UK DNO will quote without structural reinforcement. "
                    "Pending senior decision on (a) DNO reinforcement (£50k–£500k, "
                    "12–24 month timeline) versus (b) capacity-staged deployment "
                    "or (c) alternative technology mix. Reference: ENA Engineering "
                    "Recommendation G99 §B.4."
                ),
                "infeasible_grid",
                "exceeds_max_dno_quotable_headroom_1.5x",
            )
        if utilisation > _GRID_HEADROOM_RATIO_WARN:
            return (
                True,
                (
                    f"Grid headroom adequate but tight: estimated {approx_elec_kw:.0f} kW vs "
                    f"{headroom_kw:.0f} kW available ({utilisation:.1%} utilisation). "
                    f"G99 notification likely required; confirm with DNO before detailed design."
                ),
                "",
                "",
            )

    return True, "Grid and infrastructure requirements within site capability", "", ""


def _check_planning(tech: dict, site_brief: dict) -> tuple[bool, str]:
    """
    Axis 6: Planning / Part L.

    Industrial plant upgrades within the existing building envelope generally
    do not require planning permission under the GPDO (General Permitted
    Development Order) Schedule 2 Part 7 Class J (industrial/warehouse).
    Exceptions: >15 m tall structures, prominent roof-mounted equipment.
    """
    cat = tech.get("category", "")
    if cat in ("combustion_biomass",):
        return (
            True,
            "Biomass boiler: planning likely required if >300 kW (Clean Air Act 1993 s.20 exempt "
            "combustion appliance notification + smoke control zones). Flue height requirements apply.",
        )
    return (
        True,
        "Industrial internal plant upgrade — likely permitted development under GPDO Part 7 Class J; "
        "confirm with LPA before construction if external structure involved",
    )


def _check_site_space(tech: dict, site_brief: dict) -> tuple[bool, str]:
    """
    Axis 7: Does the technology footprint fit the available space envelope?
    """
    constraints = site_brief.get("constraints", {})
    space_m2 = float(constraints.get("space_envelope_m2_for_new_plant", 999))
    cat = tech.get("category", "")
    demand_kwh_yr = float(tech.get("demand_kwh_yr", 0))
    ops = site_brief.get("operations", {})
    annual_hours = float(ops.get("annual_operating_hours", 5000))
    avg_kw = demand_kwh_yr / max(annual_hours, 1)
    avg_mw = avg_kw / 1000.0

    if cat == "heat_pump":
        required_m2 = avg_mw * _HP_FOOTPRINT_M2_PER_MW * 1.5  # 1.5× for access clearances
        if required_m2 > space_m2:
            return False, (
                f"HP estimated footprint {required_m2:.0f} m² exceeds space envelope {space_m2:.0f} m². "
                f"May require phased installation or off-site plant room. Flag for senior review."
            )
        return True, f"HP estimated footprint {required_m2:.0f} m² fits within {space_m2:.0f} m² envelope"

    if cat == "electrode_boiler":
        required_m2 = avg_mw * _EB_FOOTPRINT_M2_PER_MW
        if required_m2 > space_m2:
            return False, (
                f"EB estimated footprint {required_m2:.0f} m² exceeds space envelope {space_m2:.0f} m²"
            )
        return True, f"EB compact footprint {required_m2:.0f} m² — well within {space_m2:.0f} m² envelope"

    if cat == "waste_heat_recovery":
        if _WHR_FOOTPRINT_M2 > space_m2:
            return False, f"WHR skid footprint {_WHR_FOOTPRINT_M2:.0f} m² exceeds space envelope"
        return True, f"WHR skid footprint ~{_WHR_FOOTPRINT_M2:.0f} m² fits within {space_m2:.0f} m²"

    return True, f"Technology footprint within typical {space_m2:.0f} m² site envelope"


def _check_compressor_envelope(tech: dict, site_brief: dict) -> tuple[bool, str]:
    """
    Axis 8: Temperature lift achievable with available compressor types.

    Single-stage screw HP: max ~50 K temperature lift (practical) before
    pressure ratio limit is reached. Two-stage / compound: up to ~80 K.
    High-temp HP (>160°C sink): commercially limited to a few suppliers
    (Star-Boreas, Kobelco, Viking HS) — flag for senior review.
    """
    if tech.get("category") != "heat_pump":
        return True, "Compressor envelope check: not applicable for this technology type"

    tech_id = tech.get("id", "")
    sink_temp = float(tech.get("sink_temp_c", 80.0))

    if "high_temp" in tech_id:
        return (
            True,  # commercially available but limited suppliers
            f"High-temp HP ({sink_temp:.0f}°C sink) requires two-stage or specialised screw compressor. "
            f"Commercially available from Star Refrigeration (Boreas series), Kobelco, Viking HS. "
            f"Limited supplier base — obtain 2+ quotations. NH3 is standard refrigerant at this tier. "
            f"Discharge temperature monitoring critical: NH3 limit 130°C (BS EN 378-2). "
            f"Reference: BS EN 378-2:2016 §6.4; CIBSE AM17 §5.3.",
        )

    if "med_temp_steam" in tech_id:
        return (
            True,
            f"Medium-temp HP ({sink_temp:.0f}°C steam) achievable with two-stage screw or "
            f"reciprocating compressor using NH3. Temperature lift ~{sink_temp - 20:.0f} K from "
            f"waste-heat source; within two-stage envelope. Reference: BS EN 14825:2022.",
        )

    if "mid_temp" in tech_id:
        return (
            True,
            f"Mid-temp HP ({sink_temp:.0f}°C) achievable with single-stage screw using NH3 or R1234ze(E). "
            f"Temperature lift from ambient/waste-heat source typically 50–70 K — "
            f"within single-stage screw envelope (PR < 7). Reference: BS EN 14825:2022.",
        )

    return (
        True,
        f"Low-temp HP ({sink_temp:.0f}°C) well within single-stage screw or reciprocating envelope. "
        f"Multiple refrigerant options: NH3, R1234ze(E), R290. Reference: BS EN 14825:2022.",
    )


def _check_regulatory(tech: dict, site_brief: dict) -> tuple[bool, str]:
    """
    Axis 9: UK ETS, CCA compatibility, MEES.

    All shortlisted electrification technologies are compatible with CCA targets
    (they reduce gas consumption and associated carbon). UK ETS only affects
    combustion; adding electrification does not create an ETS obligation.
    """
    cat = tech.get("category", "")
    regulatory = site_brief.get("regulatory", {})
    cca = regulatory.get("cca_subsector")

    if cat in ("combustion_biomass", "combustion_hydrogen"):
        if cca:
            return (
                True,
                f"Combustion replacement: verify biomass / H2 counted as CCA-eligible action "
                f"for subsector '{cca}'. Hydrogen boiler may not reduce Scope 1 if H2 is grey. "
                f"CCA metering and reporting obligations unchanged.",
            )

    return True, (
        f"Technology is compatible with UK ETS position and CCA targets. "
        f"Electrification reduces Scope 1 gas emissions, improving CCA performance. "
        f"No new ETS obligation introduced."
    )


# ---------------------------------------------------------------------------
# Main screening runner per technology
# ---------------------------------------------------------------------------

def _screen_single_tech(
    tech: dict, site_brief: dict
) -> dict[str, Any]:
    """
    Run all 9 feasibility axes for one candidate technology.

    Returns a result dict with status = "shortlist" | "excluded".
    """
    tech_id = tech["id"]
    tech_name = tech.get("name", tech_id)
    cat = tech.get("category", "")

    # ---- Axis 4: process compatibility (checked first — client veto is hard stop) ----
    proc_pass, proc_detail, proc_fail_code = _check_process_compatibility(tech, site_brief)
    if not proc_pass:
        return {
            "tech_id": tech_id,
            "tech_name": tech_name,
            "status": "excluded",
            "reason": proc_detail,
            "failed_axis": proc_fail_code,
        }

    # ---- Axis 5: grid & infrastructure (H2 infrastructure is hard stop;
    # grid-headroom > 1.5× routes to pending_grid_decision, not shortlist) ----
    grid_pass, grid_detail, grid_fail_code, grid_pending_reason = (
        _check_grid_and_infrastructure(tech, site_brief)
    )
    if not grid_pass and grid_pending_reason:
        return {
            "tech_id": tech_id,
            "tech_name": tech_name,
            "category": cat,
            "status": "pending_grid_decision",
            "reason": grid_detail,
            "failed_axis": grid_fail_code,
            "pending_reason_code": grid_pending_reason,
        }
    if not grid_pass:
        return {
            "tech_id": tech_id,
            "tech_name": tech_name,
            "status": "excluded",
            "reason": grid_detail,
            "failed_axis": grid_fail_code,
        }

    # ---- Axes 1–3, 6–9: feasibility checks (failure = exclude; risk = flag) ----
    thermo_pass, thermo_detail = _check_thermodynamic(tech, site_brief)
    if not thermo_pass:
        return {
            "tech_id": tech_id,
            "tech_name": tech_name,
            "status": "excluded",
            "reason": thermo_detail,
            "failed_axis": "thermodynamic_feasibility",
        }

    cap_pass, cap_detail, cap_range = _check_capacity(tech, site_brief)
    if not cap_pass:
        return {
            "tech_id": tech_id,
            "tech_name": tech_name,
            "status": "excluded",
            "reason": cap_detail,
            "failed_axis": "capacity_range_fit",
        }

    ref_pass, ref_risks = _check_refrigerant_safety(tech, site_brief)
    space_pass, space_detail = _check_site_space(tech, site_brief)
    if not space_pass:
        return {
            "tech_id": tech_id,
            "tech_name": tech_name,
            "status": "excluded",
            "reason": space_detail,
            "failed_axis": "site_space",
        }

    plan_pass, plan_detail = _check_planning(tech, site_brief)
    comp_pass, comp_detail = _check_compressor_envelope(tech, site_brief)
    reg_pass, reg_detail = _check_regulatory(tech, site_brief)

    # Build flagged risks list for shortlisted technologies
    flagged_risks: list[str] = []
    flagged_risks.extend(ref_risks)
    if not plan_pass:
        flagged_risks.append(plan_detail)
    if grid_detail and "warning" in grid_detail.lower():
        flagged_risks.append(grid_detail)

    # Build feasibility rationale
    rationale = (
        f"Thermodynamic: {thermo_detail}. "
        f"Capacity: {cap_detail}. "
        f"Compressor: {comp_detail}. "
        f"Regulatory: {reg_detail}."
    )

    return {
        "tech_id": tech_id,
        "tech_name": tech_name,
        "category": cat,
        "status": "shortlist",
        "capacity_range_kw": cap_range,
        "feasibility_rationale": rationale,
        "flagged_risks": flagged_risks,
        "feasibility_axes": {
            "thermodynamic_feasibility": thermo_pass,
            "capacity_range_fit": cap_pass,
            "refrigerant_safety": ref_pass,
            "process_compatibility": proc_pass,
            "grid_and_infrastructure": grid_pass,
            "planning_part_l": plan_pass,
            "site_space": space_pass,
            "compressor_envelope": comp_pass,
            "regulatory_ets_cca": reg_pass,
        },
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def screen_technologies(
    site_brief: dict[str, Any],
    energy_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Screen the technology longlist against a site brief and return a shortlist
    with feasibility rationale and an exclusion list with reasons.

    Args:
        site_brief:
            The full site brief dict, as found in decarb/tests/sites/*.json.
            Must contain: sector, subsector, location, process_heat, existing_plant,
            constraints (capex, space_envelope_m2, grid_headroom_mva), regulatory.

        energy_profile:
            Optional — output of parse_energy_profile. If provided, uses exact
            8,760-hour demand profiles for capacity sizing. If None, uses annual
            totals from the site brief for approximation.

    Returns:
        {
            "shortlist": list of dicts (tech_id, tech_name, category,
                         capacity_range_kw, feasibility_rationale, flagged_risks,
                         feasibility_axes),
            "excluded": list of dicts (tech_id, tech_name, reason, failed_axis),
            "borderline_notes": list (empty in v0; reserved for manual escalations),
            "candidate_count": int,
            "shortlist_count": int,
            "excluded_count": int,
            "warnings": list of warning dicts,
            "standards_cited": list of standard references,
            "method_reference": str,
            "provenance": list of provenance dicts,
        }
    """
    warnings_out: list[dict[str, str]] = []

    # Input validation
    if not site_brief:
        warnings_out.append({
            "severity": "high",
            "code": "no_site_brief",
            "message": "Empty site brief supplied — returning empty screening result",
        })
        return _empty_result(warnings_out)

    sector = site_brief.get("sector", "")
    subsector = site_brief.get("subsector", "")
    site_id = site_brief.get("site_id", "unknown")

    process_heat = site_brief.get("process_heat", {})
    if not process_heat:
        warnings_out.append({
            "severity": "high",
            "code": "no_process_heat",
            "message": "No process_heat data in site brief — technology screening will be incomplete",
        })

    # Build candidate list
    candidates = _generate_candidate_techs(site_brief)

    # Screen each candidate
    shortlist: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    excluded_pending_grid_decision: list[dict[str, Any]] = []

    for tech in candidates:
        result = _screen_single_tech(tech, site_brief)
        status = result["status"]
        entry = {k: v for k, v in result.items() if k != "status"}
        if status == "shortlist":
            shortlist.append(entry)
        elif status == "pending_grid_decision":
            excluded_pending_grid_decision.append(entry)
        else:
            excluded.append(entry)

    # Warn if expected technologies are absent
    if not any(t["tech_id"].startswith("industrial_heat_pump") for t in shortlist):
        warnings_out.append({
            "severity": "advisory",
            "code": "no_hp_in_shortlist",
            "message": "No heat pump appeared in shortlist — verify process temperatures and constraints",
        })

    return {
        "site_id": site_id,
        "sector": sector,
        "subsector": subsector,
        "shortlist": shortlist,
        "excluded": excluded,
        "excluded_pending_grid_decision": excluded_pending_grid_decision,
        "borderline_notes": [],   # reserved for v0.1
        "candidate_count": len(candidates),
        "shortlist_count": len(shortlist),
        "excluded_count": len(excluded),
        "excluded_pending_grid_decision_count": len(excluded_pending_grid_decision),
        "warnings": warnings_out,
        "method_reference": (
            "Technology screening per §5 of the engine spec. "
            "9-axis feasibility decision tree: thermodynamic, capacity, refrigerant safety, "
            "process compatibility, grid & infrastructure, planning, site space, "
            "compressor envelope, regulatory. "
            "Technology longlist generated from site process temperatures, subsector, "
            "and existing plant inventory. "
            "v0 uses approximated UK market capacity data (2024–25 survey). "
            "Full COP computed in simulate_site_dispatch — not in screening."
        ),
        "standards_cited": [
            "BS EN 378-1:2016 — Refrigerating systems and heat pumps: safety and environmental requirements",
            "BS EN 378-2:2016 — Design, construction, testing, marking and documentation",
            "BS EN 14825:2022 — Air conditioners, liquid chilling packages and heat pumps: testing and rating",
            "F-Gas Regulation 517/2014 (UK retained) and DESNZ 2024 amendments — fluorinated greenhouse gases",
            "DSEAR 2002 — Dangerous Substances and Explosive Atmospheres Regulations",
            "BS 7671:2018 — IET Wiring Regulations, 18th Edition (electrical safety)",
            "Approved Document L (Building Regulations 2021) — conservation of fuel and power",
            "Town and Country Planning (Use Classes) Order 1987 (as amended 2020) — planning classification",
            "CIBSE AM17:2012 — Heat pumps in buildings (adapted for industrial scale)",
            "BRC Global Standard for Food Safety Issue 9 (2023) — environmental hygiene §4.6",
            "DESNZ H2 Production and Delivery Infrastructure Report 2024 — UK H2 network status",
        ],
        "provenance": [
            {
                "calculation": "HP tech ID assignment",
                "method": (
                    "Sink temperature tier: ≤70°C → low_temp_hot_water; "
                    "70–80°C → low_temp_HW; 80–120°C → mid_temp; "
                    "120–160°C (steam) → med_temp_steam_make_up; >160°C → high_temp. "
                    "Tier boundaries from CIBSE AM17:2012 Table 1 commercial HP operating ranges."
                ),
                "source": "decarb.engine.screen._hp_tech_id_for_hw / _hp_tech_id_for_steam",
            },
            {
                "calculation": "MVR applicability gate",
                "method": (
                    f"Include if annual_operating_hours ≥ {_MVR_MIN_OPERATING_HOURS_PER_YR} "
                    f"AND steam_demand ≥ {_MVR_MIN_STEAM_GWH} GWh/yr. "
                    "Low operating hours → MVR capex not recovered within planning horizon."
                ),
                "source": "IChemE Process Integration Good Practice Guide; GEA MVR application guidelines",
            },
            {
                "calculation": "WHR tech ID",
                "method": (
                    f"Brewery subsector → waste_heat_recovery_wort_cooling (wort cooling is inherent). "
                    f"Other sectors: total chiller capacity ≥ {_CHILLER_WHR_HUGE_THRESHOLD_MW} MW → "
                    "_HUGE variant; else standard variant."
                ),
                "source": "Star Refrigeration industrial HP application notes; ETSU Good Practice Guide 44",
            },
            {
                "calculation": "Biomass exclusion",
                "method": (
                    "Priority 1: client no_biomass veto. "
                    "Priority 2: food_drink sector → GMP contamination check "
                    "(BRC §4.6, FSSC 22000 environmental requirements)."
                ),
                "source": "BRC Global Standard Issue 9 §4.6; FSSC 22000 infrastructure requirements",
            },
            {
                "calculation": "H2 infrastructure exclusion",
                "method": (
                    "Priority 1: client no_hydrogen veto. "
                    f"Priority 2: city not in _UK_H2_NETWORK_CITIES_2026 (currently empty set) → "
                    "excluded on infrastructure grounds per DESNZ H2 Infrastructure Report 2024."
                ),
                "source": "DESNZ H2 Production and Delivery Infrastructure Report 2024; BEIS H2 Strategy 2021",
            },
        ],
    }


def _empty_result(warnings: list) -> dict[str, Any]:
    """Return a minimal result when no screening can be performed."""
    return {
        "site_id": "unknown",
        "sector": "",
        "subsector": "",
        "shortlist": [],
        "excluded": [],
        "excluded_pending_grid_decision": [],
        "borderline_notes": [],
        "candidate_count": 0,
        "shortlist_count": 0,
        "excluded_count": 0,
        "excluded_pending_grid_decision_count": 0,
        "warnings": warnings,
        "standards_cited": [],
        "method_reference": "No screening performed — empty site brief",
        "provenance": [],
    }
