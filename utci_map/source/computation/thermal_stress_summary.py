"""
Compute summary bands from yearly UTCI statistics.

UTCI thermal-stress categories and thresholds:
https://www.ipma.pt/en/enciclopedia/amb.atmosfera/index.bioclima/index.html?page=utci.xml
"""

import calendar
from collections.abc import Sequence
from typing import Literal

import numpy as np

from utci_map.source.models import Band, YearlyStats
from utci_map.source.schema import (
    ABOVE_THRESHOLDS,
    BELOW_THRESHOLDS,
    COLD_TOTAL_BAND,
    HEAT_TOTAL_BAND,
    MAX_BAND_NAMES,
    MAX_BRACKETS,
    MIN_BAND_NAMES,
    MIN_BRACKETS,
    PEAK_MAX,
    PEAK_MIN,
)

Direction = Literal["above", "below"]

KELVIN_OFFSET = 273.15
KELVIN_UNITS = frozenset({"k", "kelvin", "degrees_k", "degree_k"})
CELSIUS_UNITS = frozenset({"c", "°c", "degc", "celsius", "degree_celsius", "degrees_celsius"})
# Plausible UTCI ranges used to guess the unit when the units attribute is empty.
KELVIN_RANGE = (150.0, 350.0)
CELSIUS_RANGE = (-100.0, 80.0)
# Tolerance for floating-point noise in day counts.
DAY_COUNT_TOLERANCE = 1e-6


def build_bands(annual: YearlyStats) -> list[Band]:
    """
    Summarize yearly UTCI statistics into bands for the output GeoTIFF.

    Include median yearly day counts for each thermal-stress category,
    median yearly totals of cold and heat days, and record maximum and
    minimum UTCI values in Celsius with the first years they occurred.
    """
    heat_counts = _yearly_days_by_stress_category(
        annual,
        direction="above",
        thresholds=ABOVE_THRESHOLDS,
        stat="daily_max",
        brackets=MAX_BRACKETS,
    )
    cold_counts = _yearly_days_by_stress_category(
        annual,
        direction="below",
        thresholds=BELOW_THRESHOLDS,
        stat="daily_min",
        brackets=MIN_BRACKETS,
    )

    bands = _category_day_bands(heat_counts, cold_counts)
    bands.extend(_total_stress_day_bands(annual.years, heat_counts, cold_counts))
    bands.extend(_utci_record_bands(annual))
    return bands


def _yearly_days_by_stress_category(
    annual: YearlyStats,
    direction: Direction,
    thresholds: tuple[float, ...],
    stat: str,
    brackets: Sequence[tuple[float, float]],
) -> list[np.ndarray]:
    """
    Turn cumulative yearly day counts into disjoint per-category counts.

    Each returned array has shape (number_of_years, height, width).
    E.g. above thresholds (26, 32, 38, 46) give the categories
    26-32 = days_above_26 - days_above_32, ..., 46+ = days_above_46.
    """
    cumulative = [annual.cubes[f"utci_days_{direction}_{t}_{stat}"] for t in thresholds]

    if direction == "above":
        parts = [low - high for low, high in zip(cumulative, cumulative[1:])]
        parts.append(cumulative[-1])
    elif direction == "below":
        parts = [cumulative[0]]
        parts.extend(high - low for low, high in zip(cumulative, cumulative[1:]))
    else:
        raise ValueError(f"direction must be 'above' or 'below', got {direction!r}")

    _check_non_negative(parts, brackets, stat)
    return parts


def _check_non_negative(
    parts: list[np.ndarray], brackets: Sequence[tuple[float, float]], stat: str
) -> None:
    """Reject negative category counts, which mean the cumulative counts are not nested."""
    for part, bracket in zip(parts, brackets):
        if np.isfinite(part).any() and np.nanmin(part) < -DAY_COUNT_TOLERANCE:
            raise ValueError(
                f"{stat} bracket {bracket}: negative counts; "
                "the cumulative variables are not nested as assumed."
            )


def _category_day_bands(heat_counts: list[np.ndarray], cold_counts: list[np.ndarray]) -> list[Band]:
    """Summarize each stress category using its median yearly day count."""
    # np.median propagates NaN, so a pixel missing in any year stays missing.
    return [
        (name, np.median(yearly_counts, axis=0), "days")
        for names, counts in ((MAX_BAND_NAMES, heat_counts), (MIN_BAND_NAMES, cold_counts))
        for name, yearly_counts in zip(names, counts)
    ]


def _total_stress_day_bands(
    years: np.ndarray, heat_counts: list[np.ndarray], cold_counts: list[np.ndarray]
) -> list[Band]:
    """Validate yearly cold and heat totals and summarize their median day counts."""
    days_in_year = np.array(
        [366 if calendar.isleap(int(year)) else 365 for year in years], dtype=float
    ).reshape(-1, 1, 1)

    # Sum categories within each year before taking the median across years.
    cold_total = np.sum(cold_counts, axis=0)
    heat_total = np.sum(heat_counts, axis=0)

    for label, total in (("cold", cold_total), ("heat", heat_total)):
        if np.isfinite(total).any() and np.nanmax(total - days_in_year) > DAY_COUNT_TOLERANCE:
            raise ValueError(f"{label}: an annual total exceeds the number of days in its year.")

    return [
        (COLD_TOTAL_BAND, np.median(cold_total, axis=0), "days"),
        (HEAT_TOTAL_BAND, np.median(heat_total, axis=0), "days"),
    ]


def _utci_record_bands(annual: YearlyStats) -> list[Band]:
    """Find record maximum and minimum UTCI values and their first years."""
    yearly_maximums, yearly_minimums = _yearly_extremes_to_celsius(annual)

    record_maximum, record_maximum_year = _record_value_and_year(
        yearly_maximums, annual.years, use_max=True
    )
    record_minimum, record_minimum_year = _record_value_and_year(
        yearly_minimums, annual.years, use_max=False
    )

    return [
        ("record_max_utci_c", record_maximum, "degC"),
        ("record_max_utci_year", record_maximum_year, "year"),
        ("record_min_utci_c", record_minimum, "degC"),
        ("record_min_utci_year", record_minimum_year, "year"),
    ]


def _yearly_extremes_to_celsius(annual: YearlyStats) -> tuple[np.ndarray, np.ndarray]:
    """Return yearly maximum and minimum UTCI in Celsius, each shaped (years, height, width)."""
    hot, cold = annual.cubes[PEAK_MAX], annual.cubes[PEAK_MIN]

    if _peaks_are_kelvin(annual, hot, cold):
        return hot - KELVIN_OFFSET, cold - KELVIN_OFFSET
    return hot, cold


def _peaks_are_kelvin(annual: YearlyStats, hot: np.ndarray, cold: np.ndarray) -> bool:
    """Decide from the declared units, or from the value range if none are declared."""
    units = {annual.peak_units[name].strip().lower() for name in (PEAK_MAX, PEAK_MIN)}
    if len(units) != 1:
        raise ValueError(f"Inconsistent units on yearly peaks: {units}")
    unit = units.pop()

    if unit in KELVIN_UNITS:
        return True
    if unit in CELSIUS_UNITS:
        return False
    if unit == "":
        return _infer_kelvin_from_range(hot, cold)
    raise ValueError(f"Unsupported units on yearly peaks: {unit!r}")


def _infer_kelvin_from_range(hot: np.ndarray, cold: np.ndarray) -> bool:
    """Guess whether undeclared peak values are Kelvin or Celsius."""
    low = float(np.nanmin([np.nanmin(hot), np.nanmin(cold)]))
    high = float(np.nanmax([np.nanmax(hot), np.nanmax(cold)]))

    if KELVIN_RANGE[0] <= low and high <= KELVIN_RANGE[1]:
        is_kelvin = True
    elif CELSIUS_RANGE[0] <= low and high <= CELSIUS_RANGE[1]:
        is_kelvin = False
    else:
        raise ValueError(f"Ambiguous peak value range {low:.2f}..{high:.2f}")

    print(f"No units attribute; inferred {'Kelvin' if is_kelvin else 'Celsius'}.")
    return is_kelvin


def _record_value_and_year(
    values: np.ndarray, years: np.ndarray, use_max: bool
) -> tuple[np.ndarray, np.ndarray]:
    """Return the record value per pixel and the first year it occurred, each (height, width)."""
    if use_max:
        record, index = np.max(values, axis=0), np.argmax(values, axis=0)
    else:
        record, index = np.min(values, axis=0), np.argmin(values, axis=0)

    year = years[index].astype(np.float64)
    year[~np.isfinite(record)] = np.nan
    return record, year
