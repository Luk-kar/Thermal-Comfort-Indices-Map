"""
Compute summary bands from yearly UTCI statistics.

UTCI thermal-stress categories and thresholds:
https://www.ipma.pt/en/enciclopedia/amb.atmosfera/index.bioclima/index.html?page=utci.xml
"""

import calendar

import numpy as np

from .models import YearlyStats
from .schema import (
    ABOVE_THRESHOLDS, BELOW_THRESHOLDS, COLD_TOTAL_BAND, HEAT_TOTAL_BAND,
    MAX_BAND_NAMES, MAX_BRACKETS, MIN_BAND_NAMES, MIN_BRACKETS, PEAK_MAX, PEAK_MIN,
)

def yearly_values(annual: YearlyStats, name: str) -> np.ndarray:
    return annual.cubes[name]


def yearly_extremes_to_celsius(annual: YearlyStats):

    hot, cold = yearly_values(annual, PEAK_MAX), yearly_values(annual, PEAK_MIN)
    kelvin_units = {"k", "kelvin", "degrees_k", "degree_k"}
    celsius_units = {"c", "°c", "degc", "celsius", "degree_celsius", "degrees_celsius"}
    units = {annual.peak_units[n].strip().lower() for n in (PEAK_MAX, PEAK_MIN)}

    if len(units) != 1:
        raise ValueError(f"Inconsistent units on yearly peaks: {units}")
    unit = units.pop()

    if unit in kelvin_units:
        is_kelvin = True

    elif unit in celsius_units:
        is_kelvin = False

    elif unit == "":

        low = float(np.nanmin([np.nanmin(hot), np.nanmin(cold)]))
        high = float(np.nanmax([np.nanmax(hot), np.nanmax(cold)]))

        if 150.0 <= low and high <= 350.0:
            is_kelvin = True
        elif -100.0 <= low and high <= 80.0:
            is_kelvin = False
        else:
            raise ValueError(f"Ambiguous peak value range {low:.2f}..{high:.2f}")
        print(f"No units attribute; inferred {'Kelvin' if is_kelvin else 'Celsius'}.")

    else:
        raise ValueError(f"Unsupported units on yearly peaks: {unit!r}")

    return (hot - 273.15, cold - 273.15) if is_kelvin else (hot, cold)


def yearly_days_by_stress_category(annual, direction, thresholds, stat, brackets):
    """Return yearly day counts for each UTCI thermal-stress category."""

    cum = {t: yearly_values(annual, f"utci_days_{direction}_{t}_{stat}") for t in thresholds}
    if direction == "above":
        parts = [cum[26] - cum[32], cum[32] - cum[38], cum[38] - cum[46], cum[46]]

    else:
        parts = [
            cum[-40],
            cum[-27] - cum[-40],
            cum[-13] - cum[-27],
            cum[0] - cum[-13],
            cum[9] - cum[0],
        ]

    for part, bracket in zip(parts, brackets):

        if np.isfinite(part).any() and np.nanmin(part) < -1e-6:
            raise ValueError(
                f"{stat} bracket {bracket}: negative counts; "
                "the cumulative variables are not nested as assumed."
            )

    return parts


def find_record_value_and_year(values, years, use_max: bool):
    """Record value per pixel and the first year it occurred."""

    if use_max:
        record, idx = np.max(values, axis=0), np.argmax(values, axis=0)

    else:
        record, idx = np.min(values, axis=0), np.argmin(values, axis=0)

    year = years[idx].astype(np.float64)
    year[~np.isfinite(record)] = np.nan

    return record, year


def calculate_yearly_category_counts(annual: YearlyStats):
    """Calculate yearly day counts for heat- and cold-stress categories."""
    heat_counts = yearly_days_by_stress_category(
        annual, "above", ABOVE_THRESHOLDS, "daily_max", MAX_BRACKETS
    )
    cold_counts = yearly_days_by_stress_category(
        annual, "below", BELOW_THRESHOLDS, "daily_min", MIN_BRACKETS
    )

    return heat_counts, cold_counts


def build_category_day_bands(heat_counts, cold_counts):
    """Summarise each stress category using its median yearly day count."""

    bands = []

    # A pixel missing in any year remains missing in the summary.
    for names, counts in (
        (MAX_BAND_NAMES, heat_counts),
        (MIN_BAND_NAMES, cold_counts),
    ):
        for name, yearly_counts in zip(names, counts):
            bands.append((name, np.median(yearly_counts, axis=0), "days"))

    return bands


def build_total_stress_day_bands(years, heat_counts, cold_counts):
    """Validate yearly cold/heat totals and summarise their median day counts."""

    days_in_year = np.array(
        [366 if calendar.isleap(int(year)) else 365 for year in years],
        dtype=float,
    ).reshape(-1, 1, 1)

    cold_total = np.sum(cold_counts, axis=0)
    heat_total = np.sum(heat_counts, axis=0)

    for label, total in (("cold", cold_total), ("heat", heat_total)):
        if np.isfinite(total).any() and np.nanmax(total - days_in_year) > 1e-6:
            raise ValueError(
                f"{label}: an annual total exceeds the number of days in its year."
            )

    # Sum categories within each year before taking the median across years.
    return [
        (COLD_TOTAL_BAND, np.median(cold_total, axis=0), "days"),
        (HEAT_TOTAL_BAND, np.median(heat_total, axis=0), "days"),
    ]


def collect_utci_records(annual: YearlyStats):
    """Find record maximum and minimum UTCI values and their first years."""

    yearly_maximums, yearly_minimums = yearly_extremes_to_celsius(annual)

    record_maximum, record_maximum_year = find_record_value_and_year(
        yearly_maximums, annual.years, use_max=True
    )
    record_minimum, record_minimum_year = find_record_value_and_year(
        yearly_minimums, annual.years, use_max=False
    )

    return [
        ("record_max_utci_c", record_maximum, "degC"),
        ("record_max_utci_year", record_maximum_year, "year"),
        ("record_min_utci_c", record_minimum, "degC"),
        ("record_min_utci_year", record_minimum_year, "year"),
    ]


def build_bands(annual: YearlyStats):
    """Summarise yearly UTCI statistics into bands for the output GeoTIFF.

    Include median yearly day counts for each thermal-stress category,
    median yearly totals of cold and heat days, and record maximum and
    minimum UTCI values in Celsius with the first years they occurred.

    Return a list of (name, values, units) tuples.
    """
    heat_counts, cold_counts = calculate_yearly_category_counts(annual)

    bands = build_category_day_bands(heat_counts, cold_counts)
    bands.extend(
        build_total_stress_day_bands(annual.years, heat_counts, cold_counts)
    )
    bands.extend(collect_utci_records(annual))

    return bands