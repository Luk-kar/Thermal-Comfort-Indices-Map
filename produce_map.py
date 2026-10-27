from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
import xarray as xr
from matplotlib.colors import LinearSegmentedColormap, ListedColormap, Normalize
from rasterio.transform import from_origin
import calendar

COLD_TOTAL_BAND = "days_daily_min_below_9_total"
HEAT_TOTAL_BAND = "days_daily_max_above_26_total"

DATA_DIR = Path("utci_iceland_sample")
START_YEAR = 2016
END_YEAR = 2025
REQUIRE_COMPLETE_PERIOD = True

OUTPUT_DIR = Path("output")
TIF_PATH = OUTPUT_DIR / "utci_summary.tif"
COLD_PNG_PATH = OUTPUT_DIR / "utci_cold_days.png"
HEAT_PNG_PATH = OUTPUT_DIR / "utci_heat_days.png"

COLD_COLORS = ["#daccc9", "#b8d4c8", "#72b6b5", "#4792b1", "#0f588f", "#042b48"]
HEAT_COLORS = ["#daccc9", "#fdbe9d", "#ef8a82", "#c8596c", "#993233"]
DISCRETE_COLORS = False  # True = use only the palette steps, no blending

PEAK_MAX = "utci_yearly_max"
PEAK_MIN = "utci_yearly_min"
INF = float("inf")

# Daily-max brackets come from cumulative "above" variables.
ABOVE_THRESHOLDS = (26, 32, 38, 46)
# Daily-min brackets come from cumulative "below" variables.
BELOW_THRESHOLDS = (-40, -27, -13, 0, 9)


def fmt(value: float) -> str:
    if value == INF:
        return "inf"
    if value == -INF:
        return "-inf"
    return f"{value:g}"


MAX_BRACKETS = [(26, 32), (32, 38), (38, 46), (46, INF)]
MIN_BRACKETS = [(-INF, -40), (-40, -27), (-27, -13), (-13, 0), (0, 9)]

MAX_BAND_NAMES = [f"days_daily_max_{fmt(lo)}_{fmt(hi)}" for lo, hi in MAX_BRACKETS]
MIN_BAND_NAMES = [f"days_daily_min_{fmt(lo)}_{fmt(hi)}" for lo, hi in MIN_BRACKETS]

REQUIRED_VARIABLES = (
    [PEAK_MAX, PEAK_MIN]
    + [f"utci_days_above_{t}_daily_max" for t in ABOVE_THRESHOLDS]
    + [f"utci_days_below_{t}_daily_min" for t in BELOW_THRESHOLDS]
)


# ---------------------------------------------------------------- loading
def load_yearly_statistics() -> xr.Dataset:
    records = []
    for nc_file in sorted(DATA_DIR.glob("*.nc")):
        with xr.open_dataset(nc_file) as ds:
            if PEAK_MAX not in ds or PEAK_MIN not in ds:
                continue
            missing = [v for v in REQUIRED_VARIABLES if v not in ds]
            if missing:
                raise KeyError(f"{nc_file.name} lacks variables: {missing}")
            records.append(ds[REQUIRED_VARIABLES].load())

    if not records:
        raise FileNotFoundError(f"No yearly-statistics files in {DATA_DIR.resolve()}")

    annual = xr.concat(
        records, dim="time", data_vars="minimal", coords="minimal",
        compat="override", join="exact",
    ).sortby("time")

    all_years = annual.time.dt.year.values.astype(int)
    keep = (all_years >= START_YEAR) & (all_years <= END_YEAR)
    annual = annual.isel(time=keep)
    years = annual.time.dt.year.values.astype(int)

    if years.size == 0:
        raise ValueError(f"No records within {START_YEAR}-{END_YEAR}")
    duplicates = sorted({int(y) for y in years if (years == y).sum() > 1})
    if duplicates:
        raise ValueError(f"Duplicate yearly records for: {duplicates}")
    missing_years = sorted(set(range(START_YEAR, END_YEAR + 1)) - set(years.tolist()))
    if missing_years and REQUIRE_COMPLETE_PERIOD:
        raise ValueError(f"Missing years: {missing_years}")
    if missing_years:
        print(f"WARNING: missing years {missing_years}; using {years.size} years")

    # North-up rows, west-to-east columns.
    return annual.sortby("lat", ascending=False).sortby("lon")


def grid_transform(annual: xr.Dataset):
    lat = annual["lat"].values.astype(float)
    lon = annual["lon"].values.astype(float)
    if lat.size < 2 or lon.size < 2:
        raise ValueError("Need at least a 2x2 grid")
    dlat, dlon = np.diff(lat), np.diff(lon)
    if not (np.allclose(dlat, dlat[0]) and np.allclose(dlon, dlon[0])):
        raise ValueError("Latitude/longitude spacing is not regular")
    dy, dx = abs(float(dlat[0])), float(dlon[0])
    # Coordinates are pixel centres; the raster origin is the outer corner.
    return from_origin(lon[0] - dx / 2, lat[0] + dy / 2, dx, dy)


def cube(annual: xr.Dataset, name: str) -> np.ndarray:
    return annual[name].transpose("time", "lat", "lon").values.astype(np.float64)


# ------------------------------------------------------------ computation
def peaks_to_celsius(annual: xr.Dataset):
    hot, cold = cube(annual, PEAK_MAX), cube(annual, PEAK_MIN)
    kelvin_units = {"k", "kelvin", "degrees_k", "degree_k"}
    celsius_units = {"c", "°c", "degc", "celsius", "degree_celsius", "degrees_celsius"}
    units = {
        str(annual[n].attrs.get("units", "")).strip().lower()
        for n in (PEAK_MAX, PEAK_MIN)
    }
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


def disjoint_counts(annual, direction, thresholds, stat, brackets):
    """Differences of cumulative counts -> per-year counts per bracket."""
    cum = {t: cube(annual, f"utci_days_{direction}_{t}_{stat}") for t in thresholds}
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


def record_with_year(values, years, use_max: bool):
    """Record value per pixel and the first year it occurred."""
    if use_max:
        record, idx = np.max(values, axis=0), np.argmax(values, axis=0)
    else:
        record, idx = np.min(values, axis=0), np.argmin(values, axis=0)
    year = years[idx].astype(np.float64)
    year[~np.isfinite(record)] = np.nan
    return record, year


def build_bands(annual: xr.Dataset):
    years = annual.time.dt.year.values.astype(int)
    bands = []  # (name, 2-D array, units)

    max_parts = disjoint_counts(annual, "above", ABOVE_THRESHOLDS, "daily_max", MAX_BRACKETS)
    min_parts = disjoint_counts(annual, "below", BELOW_THRESHOLDS, "daily_min", MIN_BRACKETS)

    # np.median propagates NaN: a pixel missing in any year stays NaN.
    for name, part in zip(MAX_BAND_NAMES, max_parts):
        bands.append((name, np.median(part, axis=0), "days"))
    for name, part in zip(MIN_BAND_NAMES, min_parts):
        bands.append((name, np.median(part, axis=0), "days"))

    # Per-year totals first, then the median across years (never exceeds 366).
    days_in_year = np.array(
        [366 if calendar.isleap(int(y)) else 365 for y in years], dtype=float
    ).reshape(-1, 1, 1)

    cold_total = np.sum(min_parts, axis=0)   # shape: (time, lat, lon)
    heat_total = np.sum(max_parts, axis=0)

    for label, total in (("cold", cold_total), ("heat", heat_total)):
        if np.isfinite(total).any() and (np.nanmax(total - days_in_year) > 1e-6):
            raise ValueError(
                f"{label}: an annual total exceeds the number of days in its year."
            )

    bands.append((COLD_TOTAL_BAND, np.median(cold_total, axis=0), "days"))
    bands.append((HEAT_TOTAL_BAND, np.median(heat_total, axis=0), "days"))

    hot, cold = peaks_to_celsius(annual)
    rec_max, rec_max_year = record_with_year(hot, years, use_max=True)
    rec_min, rec_min_year = record_with_year(cold, years, use_max=False)
    bands += [
        ("record_max_utci_c", rec_max, "degC"),
        ("record_max_utci_year", rec_max_year, "year"),
        ("record_min_utci_c", rec_min, "degC"),
        ("record_min_utci_year", rec_min_year, "year"),
    ]
    return bands


# -------------------------------------------------------------------- I/O
def write_geotiff(path: Path, bands, transform):
    path.parent.mkdir(parents=True, exist_ok=True)
    height, width = bands[0][1].shape
    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width,
        count=len(bands), dtype="float32", crs="EPSG:4326",
        transform=transform, nodata=np.nan, compress="deflate", predictor=3,
    ) as dst:
        for index, (name, array, units) in enumerate(bands, start=1):
            dst.write(array.astype("float32"), index)
            dst.set_band_description(index, name)
            dst.update_tags(index, units=units)
        dst.update_tags(start_year=START_YEAR, end_year=END_YEAR)


def read_sum(src, band_names, index) -> np.ndarray:
    return sum(src.read(index[n]).astype(np.float64) for n in band_names)


def render_png(total, bounds, title, colors, png_path: Path):
    if not np.isfinite(total).any():
        raise ValueError(f"No valid pixels to plot for {png_path.name}")

    vmin, vmax = float(np.nanmin(total)), float(np.nanmax(total))
    print(f"{png_path.name}: min {vmin:.1f} (lightest), max {vmax:.1f} (darkest)")
    if vmax == vmin:
        print(f"  All pixels equal ({vmin:.1f}); the whole map will be the lightest colour.")
        vmax = vmin + 1.0

    cmap = (
        ListedColormap(colors)
        if DISCRETE_COLORS
        else LinearSegmentedColormap.from_list("palette", colors)
    )
    cmap.set_bad("#eff6fe")

    mean_lat = 0.5 * (bounds.bottom + bounds.top)
    fig, ax = plt.subplots(figsize=(10, 6))
    image = ax.imshow(
        np.ma.masked_invalid(total), cmap=cmap, norm=Normalize(vmin, vmax),
        extent=(bounds.left, bounds.right, bounds.bottom, bounds.top),
        origin="upper", interpolation="nearest",
    )
    ax.set_aspect(1.0 / np.cos(np.deg2rad(mean_lat)))
    ax.set_xlabel("Longitude (°)")
    ax.set_ylabel("Latitude (°)")
    ax.set_title(f"{title}\n{START_YEAR}-{END_YEAR}; sum of bracket medians")
    colorbar = fig.colorbar(image, ax=ax, shrink=0.85)
    colorbar.set_label("Days per year")
    colorbar.set_ticks([vmin, vmax])

    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def render_pngs(tif_path: Path):

    with rasterio.open(tif_path) as src:
        index = {desc: i for i, desc in enumerate(src.descriptions, start=1)}
        missing = [n for n in MIN_BAND_NAMES + MAX_BAND_NAMES if n not in index]
        if missing:
            raise KeyError(f"Bands missing in {tif_path}: {missing}")
        missing = [n for n in (COLD_TOTAL_BAND, HEAT_TOTAL_BAND) if n not in index]
        if missing:
            raise KeyError(f"Bands missing in {tif_path}: {missing}")
        cold_days = src.read(index[COLD_TOTAL_BAND]).astype(np.float64)
        heat_days = src.read(index[HEAT_TOTAL_BAND]).astype(np.float64)
        bounds = src.bounds

    render_png(
        cold_days, bounds,
        "Median days/year with daily minimum UTCI below 9 °C (cold)",
        COLD_COLORS, COLD_PNG_PATH,
    )
    render_png(
        heat_days, bounds,
        "Median days/year with daily maximum UTCI above 26 °C (heat)",
        HEAT_COLORS, HEAT_PNG_PATH,
    )

def main():
    annual = load_yearly_statistics()
    years = annual.time.dt.year.values.astype(int)
    print(f"Years used ({years.size}): {years.tolist()}")
    print(f"Grid: {annual.sizes['lat']} x {annual.sizes['lon']} pixels")

    bands = build_bands(annual)
    write_geotiff(TIF_PATH, bands, grid_transform(annual))
    print(f"Wrote {TIF_PATH} ({len(bands)} bands)")

    render_pngs(TIF_PATH)
    print(f"Wrote {COLD_PNG_PATH} and {HEAT_PNG_PATH}")


if __name__ == "__main__":
    main()