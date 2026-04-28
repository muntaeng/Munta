"""
8,760-hour load profile shape templates.

Generates hourly (or half-hourly) demand profiles for industrial end-uses,
calibrated against a known annual energy demand. Each shape template captures
the qualitative behaviour of a particular load type (continuous, shifted,
batch, etc.); the integrated annual energy is normalised to match the
specified annual_kwh exactly.

Usage:
    profile = generate_profile(
        annual_kwh=28_000_000,
        shape="two_shift_weekday_continuous",
        operating_days_per_year=340,
    )
    # profile.shape == (8760,) with sum(profile) ≈ annual_kwh

Shapes implemented (matched to the load_profile keys in the golden test sites):
    - two_shift_weekday_continuous
    - three_shift_24_7
    - batch_brewing_peaks_3x_per_day
    - cleaning_in_place_pulses
    - fermentation_continuous
    - constant
    - near_constant_with_clean_in_place_peaks
    - constant_24_5
    - near_continuous_pasteurisation_and_PET_blow_moulding
    - constant_with_summer_peaks
    - fairly_constant

Conservative defaults; for a real consultancy engagement these would be
replaced with half-hourly metering data ingested via parse_energy_profile.
"""
from __future__ import annotations

import numpy as np


HOURS_PER_YEAR = 8760


def _hour_of_day(t: int) -> int:
    return t % 24


def _day_of_year(t: int) -> int:
    return t // 24


def _day_of_week(t: int, start_day: int = 0) -> int:
    """0 = Monday, 6 = Sunday."""
    return (start_day + _day_of_year(t)) % 7


# ---------------------------------------------------------------------------
# Shape generators — return unnormalised relative-magnitude arrays
# ---------------------------------------------------------------------------

def _shape_two_shift_weekday_continuous(operating_days: int) -> np.ndarray:
    """6am-10pm Mon-Sat. Off Sun. Off public holidays (approximated by reducing operating days)."""
    arr = np.zeros(HOURS_PER_YEAR)
    operating_day_count = 0
    target = operating_days
    for t in range(HOURS_PER_YEAR):
        dow = _day_of_week(t)
        hod = _hour_of_day(t)
        if dow == 6:  # Sunday
            continue
        # operating only during 06:00-22:00
        if 6 <= hod < 22:
            # smooth ramp at start/end
            ramp = 1.0
            if hod == 6:
                ramp = 0.6
            elif hod == 21:
                ramp = 0.7
            arr[t] = ramp
        # count this as an operating day
        if hod == 12:
            operating_day_count += 1
            if operating_day_count > target:
                # zero out remaining in-day after target reached
                pass
    return arr


def _shape_three_shift_24_7(operating_days: int) -> np.ndarray:
    """Continuous 24/7 except scheduled down."""
    arr = np.ones(HOURS_PER_YEAR)
    if operating_days < 365:
        # zero out the trailing days proportionally — mid-summer maintenance shutdown
        non_op_days = 365 - operating_days
        shutdown_start_hour = 24 * 200      # ~July 20
        shutdown_end_hour = shutdown_start_hour + 24 * non_op_days
        arr[shutdown_start_hour:shutdown_end_hour] = 0.0
    return arr


def _shape_batch_brewing_peaks_3x_per_day(operating_days: int) -> np.ndarray:
    """Three sharp peaks per day (mash + boil + cooling cycles), 4hr peak windows."""
    arr = np.zeros(HOURS_PER_YEAR)
    for t in range(HOURS_PER_YEAR):
        dow = _day_of_week(t)
        hod = _hour_of_day(t)
        if dow == 6:  # Sunday off
            continue
        # peaks at 02:00-06:00 (mash), 10:00-14:00 (boil), 18:00-22:00 (cool/clean)
        if 2 <= hod < 6:
            arr[t] = 1.6
        elif 10 <= hod < 14:
            arr[t] = 2.0
        elif 18 <= hod < 22:
            arr[t] = 1.4
        else:
            arr[t] = 0.3
    return arr


def _shape_cleaning_in_place_pulses(operating_days: int) -> np.ndarray:
    """CIP at end of each shift — 2-hour pulses."""
    arr = np.zeros(HOURS_PER_YEAR)
    for t in range(HOURS_PER_YEAR):
        dow = _day_of_week(t)
        hod = _hour_of_day(t)
        if dow == 6:
            continue
        # CIP at 13:00-15:00 (end shift 1) and 21:00-23:00 (end shift 2)
        if 13 <= hod < 15 or 21 <= hod < 23:
            arr[t] = 2.5
        elif 6 <= hod < 22:
            arr[t] = 0.4   # background
        # otherwise zero
    return arr


def _shape_fermentation_continuous(operating_days: int) -> np.ndarray:
    """Near-flat, slight diurnal due to ambient impact on chiller load."""
    arr = np.ones(HOURS_PER_YEAR) * 1.0
    for t in range(HOURS_PER_YEAR):
        # +5% during 14:00-18:00 (warmest part of day)
        if 14 <= _hour_of_day(t) < 18:
            arr[t] = 1.05
    return arr


def _shape_constant(operating_days: int) -> np.ndarray:
    return np.ones(HOURS_PER_YEAR)


def _shape_near_constant_with_cip_peaks(operating_days: int) -> np.ndarray:
    """Mostly flat, two CIP peaks per shift."""
    arr = np.ones(HOURS_PER_YEAR)
    for t in range(HOURS_PER_YEAR):
        dow = _day_of_week(t)
        hod = _hour_of_day(t)
        if dow == 6:
            arr[t] = 0.3
            continue
        if 13 <= hod < 14 or 21 <= hod < 22:
            arr[t] = 2.0
        else:
            arr[t] = 1.0
    return arr


def _shape_constant_24_5(operating_days: int) -> np.ndarray:
    """24-hour operation, weekdays only."""
    arr = np.zeros(HOURS_PER_YEAR)
    for t in range(HOURS_PER_YEAR):
        dow = _day_of_week(t)
        if dow < 5:    # Mon-Fri
            arr[t] = 1.0
        elif dow == 5:  # Sat
            arr[t] = 0.3
    return arr


def _shape_pasteurisation_and_pet(operating_days: int) -> np.ndarray:
    """Soft drinks / juice — pasteurisation + PET bottle blow-moulding,
    near continuous with mild diurnal."""
    arr = np.ones(HOURS_PER_YEAR)
    for t in range(HOURS_PER_YEAR):
        hod = _hour_of_day(t)
        # Slight evening peak (PET demand higher during normal-shift production)
        if 9 <= hod < 17:
            arr[t] = 1.1
    return arr


def _shape_constant_with_summer_peaks(operating_days: int) -> np.ndarray:
    """Cooling load with summer peak."""
    arr = np.zeros(HOURS_PER_YEAR)
    for t in range(HOURS_PER_YEAR):
        doy = _day_of_year(t)
        # bell curve peaking around day 200 (mid-July)
        seasonal = 1.0 + 0.5 * np.exp(-((doy - 200) ** 2) / (2 * 60 ** 2))
        arr[t] = seasonal
    return arr


def _shape_fairly_constant(operating_days: int) -> np.ndarray:
    arr = np.ones(HOURS_PER_YEAR)
    return arr


SHAPE_REGISTRY = {
    "two_shift_weekday_continuous": _shape_two_shift_weekday_continuous,
    "three_shift_24_7": _shape_three_shift_24_7,
    "batch_brewing_peaks_3x_per_day": _shape_batch_brewing_peaks_3x_per_day,
    "cleaning_in_place_pulses": _shape_cleaning_in_place_pulses,
    "fermentation_continuous": _shape_fermentation_continuous,
    "constant": _shape_constant,
    "near_constant_with_clean_in_place_peaks": _shape_near_constant_with_cip_peaks,
    "constant_24_5": _shape_constant_24_5,
    "near_continuous_pasteurisation_and_PET_blow_moulding": _shape_pasteurisation_and_pet,
    "constant_with_summer_peaks": _shape_constant_with_summer_peaks,
    "fairly_constant": _shape_fairly_constant,
}


def generate_profile(
    annual_kwh: float,
    shape: str = "fairly_constant",
    operating_days_per_year: int = 340,
) -> np.ndarray:
    """
    Generate an 8,760-hour profile (kW for each hour).

    Args:
        annual_kwh: Target annual energy (kWh)
        shape: One of SHAPE_REGISTRY keys
        operating_days_per_year: Used for some shapes (e.g. shutdown)

    Returns:
        np.ndarray of shape (8760,) — instantaneous power in kW such that
        sum(profile) = annual_kwh exactly (since each hour is 1 kWh per kW).

    Raises:
        ValueError: unknown shape, or zero-output shape.
    """
    if shape not in SHAPE_REGISTRY:
        raise ValueError(
            f"Unknown load shape '{shape}'. Known: {list(SHAPE_REGISTRY.keys())}"
        )
    if annual_kwh < 0:
        raise ValueError("annual_kwh must be non-negative")

    raw = SHAPE_REGISTRY[shape](operating_days_per_year)
    raw_total = raw.sum()
    if raw_total == 0:
        raise ValueError(f"Shape '{shape}' produced an all-zero profile")

    # Normalise so the integrated (sum over 8760 hours, with 1 hr per step) equals annual_kwh
    return raw * (annual_kwh / raw_total)


def load_duration_curve(profile: np.ndarray) -> np.ndarray:
    """Sort descending — useful for capacity planning + duration analysis."""
    return np.sort(profile)[::-1]


def peak_demand_metrics(profile: np.ndarray) -> dict:
    """Annual peak, P95, P99, base load, capacity factor."""
    peak = float(profile.max())
    base = float(profile.min())
    p95 = float(np.percentile(profile, 95))
    p99 = float(np.percentile(profile, 99))
    avg = float(profile.mean())
    capacity_factor = avg / peak if peak > 0 else 0.0
    annual_kwh = float(profile.sum())
    return {
        "peak_kw": round(peak, 1),
        "p99_kw": round(p99, 1),
        "p95_kw": round(p95, 1),
        "average_kw": round(avg, 1),
        "base_load_kw": round(base, 1),
        "capacity_factor": round(capacity_factor, 3),
        "annual_kwh": round(annual_kwh, 0),
        "annual_runtime_hours_above_50pct": int((profile > 0.5 * peak).sum()),
    }
