"""Check the summary bands that build_bands derives from yearly UTCI statistics.

Cover band names, values and units, missing pixels, record years, and rejection of invalid
inputs.
"""

from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip("rasterio")
from utci_map.source.computation.thermal_stress_summary import build_bands  # noqa: E402

EXPECTED = [
    ("days_daily_max_26_32", 4, "days"),
    ("days_daily_max_32_38", 3, "days"),
    ("days_daily_max_38_46", 2, "days"),
    ("days_daily_max_46_inf", 2, "days"),
    ("days_daily_min_-inf_-40", 2, "days"),
    ("days_daily_min_-40_-27", 2, "days"),
    ("days_daily_min_-27_-13", 3, "days"),
    ("days_daily_min_-13_0", 4, "days"),
    ("days_daily_min_0_9", 5, "days"),
    ("days_daily_min_below_9_total", 16, "days"),
    ("days_daily_max_above_26_total", 11, "days"),
    ("record_max_utci_c", 32, "degC"),
    ("record_max_utci_year", 2018, "year"),
    ("record_min_utci_c", -22, "degC"),
    ("record_min_utci_year", 2018, "year"),
]


@pytest.mark.parametrize("units", ["degC", "K", ""])
def test_summary_values_names_units_and_missing_pixels(yearly_statistics, units):
    """
    Check summary band names, values, units, and missing pixels.

    Cover yearly UTCI extremes declared in Celsius or Kelvin, and Celsius
    values without declared units. In every case, expect the same summary:
    median yearly day counts, record extremes in Celsius, and record years.

    Verify band order and preserve NaN at the pixel missing in every year.
    """

    data = yearly_statistics

    for name in ("utci_yearly_max", "utci_yearly_min"):
        data.peak_units[name] = units
        if units == "K":
            data.cubes[name][:] += 273.15
    result = build_bands(data)

    assert len(result) == len(EXPECTED)

    for (name, values, unit), (expected_name, expected_value, expected_unit) in zip(
        result, EXPECTED
    ):
        assert (name, unit) == (expected_name, expected_unit)

        expected = np.full((4, 4), float(expected_value))
        expected[0, 0] = np.nan
        np.testing.assert_allclose(values, expected, equal_nan=True)


def test_record_ties_return_first_year(yearly_statistics):
    """
    Check that tied UTCI records are assigned to their earliest year.

    Give every year the same maximum and minimum values. Since the fixture
    orders years chronologically (2016–2018), the first occurrence of each
    record is in 2016, which both record-year bands should report.
    """

    for name in ("utci_yearly_max", "utci_yearly_min"):
        yearly_statistics.cubes[name][1:] = yearly_statistics.cubes[name][0]

    result = {name: values for name, values, _ in build_bands(yearly_statistics)}

    for name in ("record_max_utci_year", "record_min_utci_year"):
        assert result[name][1, 1] == 2016


@pytest.mark.parametrize(
    "case", ["negative_counts", "too_many_days", "unsupported_units", "inconsistent_units"]
)
def test_invalid_statistics_raise_value_error(yearly_statistics, case):
    if case == "negative_counts":
        yearly_statistics.cubes["utci_days_above_32_daily_max"][:] = 100
    elif case == "too_many_days":
        yearly_statistics.cubes["utci_days_above_26_daily_max"][:] = 367
    elif case == "unsupported_units":
        yearly_statistics.peak_units.update(utci_yearly_max="F", utci_yearly_min="F")
    else:
        yearly_statistics.peak_units["utci_yearly_min"] = "K"
    with pytest.raises(ValueError):
        build_bands(yearly_statistics)


@pytest.mark.parametrize("year, days, valid", [(2016, 366, True), (2017, 366, False)])
def test_totals_respect_calendar_year_length(yearly_statistics, year, days, valid):
    cubes = {name: values[:1].copy() for name, values in yearly_statistics.cubes.items()}
    cubes["utci_days_above_26_daily_max"][:] = days
    data = replace(yearly_statistics, years=np.array([year]), cubes=cubes)

    if valid:
        result = {name: values for name, values, _ in build_bands(data)}
        assert result["days_daily_max_above_26_total"][1, 1] == days

    else:
        with pytest.raises(ValueError):
            build_bands(data)


def test_total_stress_days_are_summed_per_year_before_taking_median(
    yearly_statistics,
):
    """Check that total stress days are calculated before summarizing years.

    Distribute 100 heat-stress days across different categories in each
    year. Each year still totals 100 days, so the median yearly total
    must be 100, even though each individual category has a median of zero.
    """

    yearly_counts = [(26, [100, 100, 100]), (32, [100, 100, 0]), (38, [100, 0, 0]), (46, [0, 0, 0])]
    for threshold, counts in yearly_counts:
        field = f"utci_days_above_{threshold}_daily_max"
        yearly_statistics.cubes[field][:] = np.array(counts)[:, None, None]

    result = {name: values for name, values, _ in build_bands(yearly_statistics)}

    assert result["days_daily_max_above_26_total"][1, 1] == 100

    for name in (
        "days_daily_max_26_32",
        "days_daily_max_32_38",
        "days_daily_max_38_46",
        "days_daily_max_46_inf",
    ):
        assert result[name][1, 1] == 0


def test_pixel_missing_in_one_year_remains_missing(yearly_statistics):
    for values in yearly_statistics.cubes.values():
        values[1, 2, 2] = np.nan

    for _, values, _ in build_bands(yearly_statistics):
        assert np.isnan(values[2, 2])
