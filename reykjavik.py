from math import ceil
from pathlib import Path
import re

import numpy as np
import pandas as pd
import xarray as xr


DATA_DIR = Path("utci_iceland_sample")
START_YEAR = 2016
END_YEAR = 2025
REQUIRE_COMPLETE_PERIOD = False

REYK_LAT = 64.1466
REYK_LON = -21.9426

MIN_PRESENT_FRACTION = 0.7
DAYS_IN_YEAR = 365
PEAKS = ("utci_yearly_max", "utci_yearly_min")

ABOVE_BELOW = re.compile(
    r"^utci_days_(above|below)_(-?\d+)_(daily_(?:min|max))$"
)
IN_RANGE = re.compile(
    r"^utci_days_in_range_(-?\d+)_(-?\d+)_(daily_(?:min|max))$"
)


def classify_cold_stress(utci_c: float) -> str:
    if utci_c > 9.0:
        return "No thermal stress"
    if utci_c > 0.0:
        return "Slight cold stress"
    if utci_c > -13.0:
        return "Moderate cold stress"
    if utci_c > -27.0:
        return "Strong cold stress"
    if utci_c > -40.0:
        return "Very strong cold stress"
    return "Extreme cold stress"


def describe_bracket(name: str):
    """Return (label, stat, is_comfort_range, sort_key) or None."""
    m = IN_RANGE.match(name)
    if m:
        lo, hi, stat = m.groups()
        return f"{lo}–{hi} °C", stat, (lo, hi) == ("9", "26"), (int(lo), 1)
    m = ABOVE_BELOW.match(name)
    if m:
        direction, threshold, stat = m.groups()
        sign = ">" if direction == "above" else "<"
        return f"{sign} {threshold} °C", stat, False, (int(threshold), 0)
    return None


def infer_kelvin(values: np.ndarray, name: str) -> bool:
    low, high = float(np.nanmin(values)), float(np.nanmax(values))
    if 150.0 <= low and high <= 350.0:
        return True
    if -100.0 <= low and high <= 80.0:
        return False
    raise ValueError(f"{name}: ambiguous value range {low:.2f}..{high:.2f}")


# 1. Read the Reykjavík grid cell from each yearly-statistics file
records, cell = [], None

for nc_file in sorted(DATA_DIR.glob("*.nc")):
    with xr.open_dataset(nc_file) as ds:
        if not all(name in ds for name in PEAKS):
            continue

        point = ds.sel(lat=REYK_LAT, lon=REYK_LON, method="nearest")
        this_cell = (float(point["lat"]), float(point["lon"]))
        if cell is not None and this_cell != cell:
            raise ValueError(f"Inconsistent grid cell in {nc_file.name}")
        cell = this_cell

        records.append(point.drop_vars("time_bnds", errors="ignore").load())

if not records:
    raise FileNotFoundError(f"No yearly-statistics files in {DATA_DIR.resolve()}")

annual = xr.concat(records, dim="time", data_vars="minimal", coords="minimal")
annual = annual.sortby("time")

all_years = annual.time.dt.year.values.astype(int)
annual = annual.isel(time=(all_years >= START_YEAR) & (all_years <= END_YEAR))
years = annual.time.dt.year.values.astype(int)

if years.size == 0:
    raise ValueError(f"No records within {START_YEAR}–{END_YEAR}")

duplicates = sorted({int(y) for y in years if (years == y).sum() > 1})
if duplicates:
    raise ValueError(f"Duplicate yearly records for: {duplicates}")

missing = sorted(set(range(START_YEAR, END_YEAR + 1)) - set(years.tolist()))
if missing and REQUIRE_COMPLETE_PERIOD:
    raise ValueError(f"Missing years: {missing}")

n_years = len(years)
required_years = ceil(MIN_PRESENT_FRACTION * n_years)

print(f"Query: ({REYK_LAT}, {REYK_LON}) -> grid cell {cell}")
print(f"Years found ({n_years}): {years.tolist()}")
if missing:
    print(f"WARNING: missing years {missing}")
print(f"Non-comfort brackets need a non-zero count in >= {required_years} years")


# 2. Annual peaks (°C)
peaks_raw = pd.DataFrame(
    {name: annual[name].values.reshape(n_years) for name in PEAKS},
    index=pd.Index(years, name="year"),
)
if not np.isfinite(peaks_raw.to_numpy()).all():
    raise ValueError("Non-finite values in yearly peaks")

for name in PEAKS:
    if str(annual[name].attrs.get("units", "")).strip():
        raise ValueError(f"{name} now has units; handle them explicitly.")

if infer_kelvin(peaks_raw.to_numpy(), "yearly peaks"):
    peaks = peaks_raw - 273.15
    print("Peaks: no units attribute; inferred Kelvin and converted to °C.")
else:
    peaks = peaks_raw.copy()

peaks = peaks.rename(
    columns={"utci_yearly_max": "peak_heat_c", "utci_yearly_min": "peak_cold_c"}
)

peak_summary = pd.DataFrame(
    {
        "median_c": peaks.median(),
        "sd_c": peaks.std(ddof=1) if n_years > 1 else np.nan,
        "record_min_c": peaks.min(),
        "record_max_c": peaks.max(),
    }
)
peak_summary["record_min_year"] = peaks.idxmin()
peak_summary["record_max_year"] = peaks.idxmax()

print("\n=== ANNUAL UTCI PEAKS ===")
print(peak_summary.to_string(float_format=lambda v: f"{v:.2f}"))
print(
    "Median annual peak cold category: "
    f"{classify_cold_stress(float(peaks['peak_cold_c'].median()))}"
)
print(
    "Coldest value on record category: "
    f"{classify_cold_stress(float(peaks['peak_cold_c'].min()))}"
)


# 3. Day-count brackets
import calendar

THRESHOLDS_BELOW = (-40, -27, -13, 0, 9)
THRESHOLDS_ABOVE = (26, 32, 38, 46)
STATS = ("daily_min", "daily_max")
INF = float("inf")


def yearly_counts(direction: str, threshold: int, stat: str) -> np.ndarray:
    name = f"utci_days_{direction}_{threshold}_{stat}"
    if name not in annual:
        raise KeyError(f"Missing variable: {name}")
    values = annual[name].values.reshape(n_years).astype(float)
    if not np.isfinite(values).all():
        raise ValueError(f"{name}: non-finite values")
    return values


def comfort_counts(stat: str) -> np.ndarray:
    name = f"utci_days_in_range_9_26_{stat}"
    if name not in annual:
        raise KeyError(f"Missing variable: {name}")
    values = annual[name].values.reshape(n_years).astype(float)
    if not np.isfinite(values).all():
        raise ValueError(f"{name}: non-finite values")
    return values


def disjoint_brackets(stat: str):
    """Return [(lower, upper, yearly_counts, is_comfort)] for one statistic."""
    below = {t: yearly_counts("below", t, stat) for t in THRESHOLDS_BELOW}
    above = {t: yearly_counts("above", t, stat) for t in THRESHOLDS_ABOVE}

    return [
        (-INF, -40.0, below[-40], False),
        (-40.0, -27.0, below[-27] - below[-40], False),
        (-27.0, -13.0, below[-13] - below[-27], False),
        (-13.0, 0.0, below[0] - below[-13], False),
        (0.0, 9.0, below[9] - below[0], False),
        (9.0, 26.0, comfort_counts(stat), True),
        (26.0, 32.0, above[26] - above[32], False),
        (32.0, 38.0, above[32] - above[38], False),
        (38.0, 46.0, above[38] - above[46], False),
        (46.0, INF, above[46], False),
    ]


days_in_year = np.array([366 if calendar.isleap(int(y)) else 365 for y in years])

rows, skipped = [], []

for stat in STATS:
    brackets = disjoint_brackets(stat)

    for lower, upper, values, _ in brackets:
        if (values < -1e-6).any():
            raise ValueError(
                f"{stat} ({lower}, {upper}): negative counts; "
                "the cumulative variables are not nested as assumed."
            )

    total = np.sum([values for _, _, values, _ in brackets], axis=0)
    residual = days_in_year - total
    print(
        f"{stat}: sum of brackets vs days in year -> "
        f"max |difference| = {np.abs(residual).max():.1f} days"
    )

    for lower, upper, values, is_comfort in brackets:
        years_present = int((values > 0).sum())

        if not is_comfort and years_present < required_years:
            skipped.append((stat, lower, upper, years_present))
            continue

        median_days = float(np.median(values))
        rows.append(
            {
                "stat": stat,
                "lower_bound": lower,
                "upper_bound": upper,
                "median_days": median_days,
                "sd_days": float(values.std(ddof=1)) if n_years > 1 else np.nan,
                "min_days": float(values.min()),
                "max_days": float(values.max()),
                "years_present": f"{years_present}/{n_years}",
                "median_pct_of_year": (
                    100.0 * median_days / DAYS_IN_YEAR if is_comfort else np.nan
                ),
            }
        )

summary = (
    pd.DataFrame(rows)
    .sort_values(["stat", "lower_bound"])
    .reset_index(drop=True)
)

print("\n=== DAYS PER YEAR BY DISJOINT UTCI BRACKET (°C) ===")
print(
    summary.to_string(
        index=False,
        float_format=lambda v: f"{v:.1f}",
        na_rep="",
    )
)

summary.to_csv("reykjavik_bracket_summary.csv", index=False)
peak_summary.to_csv("reykjavik_peak_summary.csv")