"""Tests for load_profiles module."""
from __future__ import annotations

import numpy as np
import pytest

from decarb.engine.load_profiles import (
    HOURS_PER_YEAR,
    SHAPE_REGISTRY,
    generate_profile,
    load_duration_curve,
    peak_demand_metrics,
)


class TestProfileNormalisation:
    @pytest.mark.parametrize("shape", list(SHAPE_REGISTRY.keys()))
    def test_annual_energy_matches_input(self, shape):
        """Every shape must integrate to the specified annual_kwh exactly."""
        target = 28_000_000
        profile = generate_profile(annual_kwh=target, shape=shape)
        assert profile.shape == (HOURS_PER_YEAR,)
        recovered = float(profile.sum())
        assert abs(recovered - target) / target < 1e-6, f"{shape}: {recovered} vs {target}"

    def test_zero_energy_handled(self):
        """Zero annual energy → all-zero profile, no error."""
        profile = generate_profile(annual_kwh=0, shape="constant")
        assert profile.shape == (HOURS_PER_YEAR,)
        assert profile.sum() == 0.0

    def test_unknown_shape_raises(self):
        with pytest.raises(ValueError, match="Unknown load shape"):
            generate_profile(annual_kwh=100, shape="not_a_real_shape")

    def test_negative_input_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            generate_profile(annual_kwh=-100, shape="constant")


class TestProfileShapes:
    def test_two_shift_has_zero_during_off_hours(self):
        profile = generate_profile(annual_kwh=10_000_000, shape="two_shift_weekday_continuous")
        # 03:00 on a weekday should be zero (off-shift)
        assert profile[3] == 0.0
        # Sunday all hours should be zero (assuming start_day=0=Mon, day 6 = Sun)
        sunday_start = 24 * 6
        assert profile[sunday_start:sunday_start + 24].sum() == 0.0

    def test_24_7_has_no_zeros_in_operating_period(self):
        profile = generate_profile(
            annual_kwh=10_000_000, shape="three_shift_24_7", operating_days_per_year=365
        )
        assert (profile > 0).all()

    def test_batch_brewing_has_three_peaks_per_day(self):
        profile = generate_profile(
            annual_kwh=10_000_000, shape="batch_brewing_peaks_3x_per_day"
        )
        # Mon (day 0) — peaks at 02-06, 10-14, 18-22
        mon = profile[0:24]
        assert mon[12] > mon[8]   # boil peak
        assert mon[3] > mon[0]    # mash peak
        assert mon[19] > mon[16]  # cool/clean peak

    def test_constant_with_summer_peaks_summer_higher(self):
        profile = generate_profile(annual_kwh=10_000_000, shape="constant_with_summer_peaks")
        # Mid-July (day 200) should be higher than mid-January
        winter_avg = profile[15 * 24 : 16 * 24].mean()
        summer_avg = profile[200 * 24 : 201 * 24].mean()
        assert summer_avg > winter_avg * 1.3


class TestMetrics:
    def test_peak_demand_metrics_structure(self):
        profile = generate_profile(annual_kwh=1_000_000, shape="two_shift_weekday_continuous")
        metrics = peak_demand_metrics(profile)
        for key in ("peak_kw", "p99_kw", "p95_kw", "average_kw", "base_load_kw", "capacity_factor", "annual_kwh"):
            assert key in metrics
        assert metrics["peak_kw"] >= metrics["p99_kw"] >= metrics["p95_kw"] > metrics["average_kw"]

    def test_load_duration_curve_descending(self):
        profile = generate_profile(annual_kwh=1_000_000, shape="batch_brewing_peaks_3x_per_day")
        ldc = load_duration_curve(profile)
        assert ldc.shape == profile.shape
        # First element ≥ last element
        assert ldc[0] >= ldc[-1]
        # Each element ≥ next
        diffs = np.diff(ldc)
        assert (diffs <= 0).all()

    def test_capacity_factor_in_unit_range(self):
        profile = generate_profile(annual_kwh=1_000_000, shape="constant")
        metrics = peak_demand_metrics(profile)
        assert 0 <= metrics["capacity_factor"] <= 1.0
        # constant profile → capacity factor near 1
        assert metrics["capacity_factor"] > 0.99
