"""
Build the UTCI extreme-day summary GeoTIFF, 
plain PNG maps and MapLibre sidecars.
"""

import calendar
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import Affine, array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds

WEBMERCATOR_CRS: CRS = CRS.from_epsg(3857)
WGS84_CRS: CRS = CRS.from_epsg(4326)

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
COLD_JSON_PATH = OUTPUT_DIR / "utci_cold_days.json"
HEAT_JSON_PATH = OUTPUT_DIR / "utci_heat_days.json"

# Cold map: days/year with daily minimum UTCI below 9 °C.
# Runs from a neutral warm grey (few cold days) to deep navy (many).
COLD_COLORS = [
    "#daccc9",  # pale warm grey (light taupe) - fewest days; shared start colour
    "#b8d4c8",  # pale sage green / light seafoam
    "#72b6b5",  # muted teal (soft aqua)
    "#4792b1",  # steel blue
    "#0f588f",  # deep azure blue
    "#042b48",  # very dark navy - most days
]

# Heat map: days/year with daily maximum UTCI above 26 °C.
# Runs from the same neutral grey (few hot days) to dark red (many).
HEAT_COLORS = [
    "#daccc9",  # pale warm grey (light taupe) - fewest days; shared start colour
    "#fdbe9d",  # light peach (pale apricot)
    "#ef8a82",  # salmon / coral pink
    "#c8596c",  # dusty rose (raspberry)
    "#993233",  # dark brick red (burgundy) - most days
]

DISCRETE_COLORS = False  # True = use only the palette steps, no blending
PNG_SCALE = 1  # 1 = native size; >1 enlarges with nearest-neighbour (coordinates are unaffected)

MAX_INDEX = 254  # palette indices 0..254 hold data; 255 is nodata
NODATA_INDEX = 255
COLOR_MAP_STEP = 17  # spacing of the entries listed in the sidecar's "color_map"

PEAK_MAX = "utci_yearly_max"
PEAK_MIN = "utci_yearly_min"
INF = float("inf")



def format_bound(value: float) -> str:
    """
    Format a bracket bound for 
    band/variable names and messages
    """

    if value == INF:
        return "inf"

    if value == -INF:
        return "-inf"

    return f"{value:g}"


MAX_BRACKETS = [(26, 32), (32, 38), (38, 46), (46, INF)]
MIN_BRACKETS = [(-INF, -40), (-40, -27), (-27, -13), (-13, 0), (0, 9)]

def bracket_thresholds(brackets, threshold_direction):
    """
    Cumulative-count thresholds that the brackets are built from.

    "above": the lower edge of every bracket (the last one must be open-ended).
    "below": the upper edge of every bracket (the first one must be open-ended).
    """

    THRESHOLD_STATISTIC = {"above": "daily_max", "below": "daily_min"}

    if threshold_direction not in THRESHOLD_STATISTIC:
        raise ValueError(
            f"threshold_direction must be 'above' or 'below', got {threshold_direction!r}"
        )

    for (_, upper_bound), (lower_bound, _) in zip(brackets, brackets[1:]):
        if upper_bound != lower_bound:
            raise ValueError(f"Brackets are not contiguous: {upper_bound} != {lower_bound}")

    if threshold_direction == "above":

        if brackets[-1][1] != INF:
            raise ValueError(
                "The last 'above' bracket must be open-ended (upper bound inf), "
                f"but its upper bound is {format_bound(brackets[-1][1])} "
                f"(bracket: {format_bound(brackets[-1][0])} to {format_bound(brackets[-1][1])})"
            )
        return tuple(lower_bound for lower_bound, _ in brackets)

    if brackets[0][0] != -INF:

        raise ValueError(
            "The first 'below' bracket must be open-ended (lower bound -inf), "
            f"but its lower bound is {format_bound(brackets[0][0])} "
            f"(bracket: {format_bound(brackets[0][0])} to {format_bound(brackets[0][1])})"
        )

    return tuple(upper_bound for _, upper_bound in brackets)

ABOVE_THRESHOLDS = bracket_thresholds(MAX_BRACKETS, "above")  # (26, 32, 38, 46)
BELOW_THRESHOLDS = bracket_thresholds(MIN_BRACKETS, "below")  # (-40, -27, -13, 0, 9)

def build_band_names(prefix: str, brackets) -> list[str]:
    """
    Build one band name per bracket, 
    e.g. 'days_daily_max_26_32'.
    """

    return [
        f"{prefix}_{format_bound(lower_bound)}_{format_bound(upper_bound)}"
        for lower_bound, upper_bound in brackets
    ]


MAX_BAND_NAMES = build_band_names("days_daily_max", MAX_BRACKETS)
MIN_BAND_NAMES = build_band_names("days_daily_min", MIN_BRACKETS)

# NetCDF variables that every yearly-statistics file must contain: 
# the yearly peaks plus one day-count variable per threshold
REQUIRED_NETCDF_VARIABLES = (
    [PEAK_MAX, PEAK_MIN]
    + [f"utci_days_above_{t}_daily_max" for t in ABOVE_THRESHOLDS]
    + [f"utci_days_below_{t}_daily_min" for t in BELOW_THRESHOLDS]
)




@dataclass(frozen=True)
class FileRecords:
    years: list[int]
    arrays: dict[str, list[np.ndarray]]  # variable -> one 2-D array per time step
    peak_units: dict[str, str]
    shape: tuple[int, int]
    transform: Affine


@dataclass(frozen=True)
class YearlyStats:
    years: np.ndarray  # (time,)
    cubes: dict[str, np.ndarray]  # variable -> (time, lat, lon), physical units
    peak_units: dict[str, str]
    shape: tuple[int, int]
    transform: Affine


# ---------------------------------------------------------------- loading
def subdataset_uris(nc_file: Path) -> dict[str, str]:
    """
    Map NetCDF variable name -> GDAL subdataset URI.

    GDAL exposes each variable of a NetCDF file as a subdataset URI, and the
    variable name is the text after the last colon, e.g.:

        'NETCDF:"utci_iceland_sample/utci_2015.nc":utci_yearly_max'
            -> {"utci_yearly_max": 'NETCDF:"utci_iceland_sample/utci_2015.nc":utci_yearly_max'}

        'NETCDF:"utci_iceland_sample/utci_2015.nc":utci_days_above_26_daily_max'
            -> {"utci_days_above_26_daily_max": 'NETCDF:"utci_iceland_sample/utci_2015.nc":utci_days_above_26_daily_max'}
    """

    with rasterio.open(nc_file) as parent:
        uris = parent.subdatasets

    return {uri.rsplit(":", 1)[-1].strip('"'): uri for uri in uris}


def year_of_time_coordinate(dataset_tags: dict, band_tags: dict) -> int:
    """
    Convert a NetCDF time step, stored as an offset from a reference date, into its calendar year.

    E.g. 8760 with units "hours since 2015-01-01" -> 2016.
    """

    # Date part of the units string, e.g. "2015-01-01" or "2015-1-1"
    DATE_PATTERN = r"(\d{4})-(\d{1,2})-(\d{1,2})"
    # Optional time part, e.g. " 00:00:00", "T06:30:00" or " 12:00:00.5"
    TIME_PATTERN = r"(?:[ T](\d{1,2}):(\d{2}):(\d{2})(?:\.\d+)?)"
    TIMEZONE_PATTERN = r"(?:UTC|Z)"

    TIME_UNITS_RE = re.compile(
        rf"^(seconds|hours|days) since {DATE_PATTERN}{TIME_PATTERN}?(?: ?{TIMEZONE_PATTERN})?$"
    )

    SECONDS_PER_UNIT = {"seconds": 1.0, "hours": 3600.0, "days": 86400.0}
    SUPPORTED_CALENDARS = {"standard", "gregorian", "proleptic_gregorian"}

    calendar_name = dataset_tags.get("time#calendar")
    if calendar_name not in SUPPORTED_CALENDARS:
        raise ValueError(
            f"Unsupported or missing time calendar (tag 'time#calendar'): {calendar_name!r}; "
            f"expected one of {sorted(SUPPORTED_CALENDARS)}"
        )

    units = dataset_tags.get("time#units")
    match = TIME_UNITS_RE.match(units) if isinstance(units, str) else None
    if not match:
        raise ValueError(
            f"Unsupported or missing time units (tag 'time#units'): {units!r}; "
            "expected e.g. 'hours since 2015-01-01 00:00:00'"
        )
    unit, year, month, day, hour, minute, second = match.groups()
    origin = datetime(
        int(year), int(month), int(day),
        int(hour or 0), int(minute or 0), int(second or 0),
        tzinfo=timezone.utc,
    )

    raw = band_tags.get("NETCDF_DIM_time")

    try:
        offset = float(raw)

    except (TypeError, ValueError):
        offset = math.nan

    if not math.isfinite(offset):
        raise ValueError(f"Invalid time coordinate (tag 'NETCDF_DIM_time'): {raw!r}")

    return (origin + timedelta(seconds=offset * SECONDS_PER_UNIT[unit])).year


def check_geographic(dataset_tags: dict, nc_file: Path, name: str) -> None:

    expected = {"lat#units": "degrees_north", "lon#units": "degrees_east"}

    for key, value in expected.items():

        found = dataset_tags.get(key)

        if found is not None and found != value:
            raise ValueError(f"{nc_file.name}:{name}: {key}={found!r}, expected {value!r}")


def transforms_match(a, b) -> bool:
    """
    Check that two rasters sit on the same grid, 
    tolerating tiny floating-point differences.
    """
    return np.allclose(tuple(a)[:6], tuple(b)[:6], rtol=0.0, atol=1e-9)


def read_physical(time_series_raster, band: int, name: str, nc_file: Path) -> np.ndarray:
    """
    Read one band, 
    mask missing values and 
    apply this variable's scale/offset.
    """

    scale = float(time_series_raster.scales[band - 1])
    offset = float(time_series_raster.offsets[band - 1])

    if not math.isfinite(scale) or scale <= 0:
        raise ValueError(f"{nc_file.name}:{name}: invalid scale_factor {scale!r}")
    if not math.isfinite(offset):
        raise ValueError(f"{nc_file.name}:{name}: invalid add_offset {offset!r}")

    raw = time_series_raster.read(band, masked=True).astype(np.float64)
    values = raw.filled(np.nan) * scale + offset
    values[~np.isfinite(values)] = np.nan

    return values


@dataclass(frozen=True)
class VariableRecords:
    years: list[int]
    arrays: list[np.ndarray]  # one 2-D array per time step
    shape: tuple[int, int]
    transform: Affine
    peak_unit: str | None  # only set for the yearly peak variables


def check_north_up_grid(src, nc_file: Path, name: str) -> None:
    """
    Reject rotated or south-up grids, 
    which the rest of the pipeline can't handle.
    """

    t = src.transform
    if t.a <= 0 or t.e >= 0 or abs(t.b) > 1e-12 or abs(t.d) > 1e-12:
        raise ValueError(f"{nc_file.name}:{name}: grid is not an unrotated north-up raster")


def read_peak_unit(src, tags: dict, name: str) -> str:
    """
    Find the units of a yearly peak variable, or '' 
    if the file doesn't declare any.
    """

    unit = src.units[0] or src.tags(1).get("units") or tags.get(f"{name}#units") or ""
    return str(unit)


def read_variable(uri: str, nc_file: Path, name: str) -> VariableRecords:
    """
    Open one variable, validate its grid and 
    time axis, and read all its time steps.
    """

    with rasterio.open(uri) as src:
        tags = src.tags()
        check_geographic(tags, nc_file, name)
        check_north_up_grid(src, nc_file, name)
        if not src.indexes:
            raise ValueError(f"{nc_file.name}:{name}: no time steps")

        return VariableRecords(
            years=[year_of_time_coordinate(tags, src.tags(b)) for b in src.indexes],
            arrays=[read_physical(src, b, name, nc_file) for b in src.indexes],
            shape=src.shape,
            transform=src.transform,
            peak_unit=read_peak_unit(src, tags, name) if name in (PEAK_MAX, PEAK_MIN) else None,
        )


def check_matches_reference(
    variable: VariableRecords, reference: VariableRecords,
    nc_file: Path, name: str, reference_name: str,
) -> None:
    """
    Require the same years and 
    grid as the reference variable.
    """

    if variable.years != reference.years:
        raise ValueError(f"{nc_file.name}:{name}: time axis differs from {reference_name}")
    if variable.shape != reference.shape or not transforms_match(variable.transform, reference.transform):
        raise ValueError(f"{nc_file.name}:{name}: grid differs from {reference_name}")


def read_yearly_file(nc_file: Path) -> FileRecords | None:
    """
    Read every required variable of one file, 
    or return None if it isn't a yearly-statistics file.
    """

    uris = subdataset_uris(nc_file)
    if PEAK_MAX not in uris or PEAK_MIN not in uris:
        return None

    missing = [v for v in REQUIRED_NETCDF_VARIABLES if v not in uris]
    if missing:
        raise KeyError(f"{nc_file.name} lacks variables: {missing}")

    reference_name = REQUIRED_NETCDF_VARIABLES[0]
    reference: VariableRecords | None = None
    arrays: dict[str, list[np.ndarray]] = {}
    peak_units: dict[str, str] = {}

    for name in REQUIRED_NETCDF_VARIABLES:
        variable = read_variable(uris[name], nc_file, name)

        if reference is None:
            reference = variable
        else:
            check_matches_reference(variable, reference, nc_file, name, reference_name)

        arrays[name] = variable.arrays
        if variable.peak_unit is not None:
            peak_units[name] = variable.peak_unit

    return FileRecords(reference.years, arrays, peak_units, reference.shape, reference.transform)


def load_yearly_statistics() -> YearlyStats:

    records: list[tuple[int, dict[str, np.ndarray]]] = []
    grid = None
    peak_units: dict[str, str] | None = None

    for nc_file in sorted(DATA_DIR.glob("*.nc")):

        loaded = read_yearly_file(nc_file)
        if loaded is None:
            continue

        if grid is None:
            grid = (loaded.shape, loaded.transform)
            peak_units = loaded.peak_units
        else:
            if loaded.shape != grid[0] or not transforms_match(loaded.transform, grid[1]):
                raise ValueError(f"{nc_file.name}: grid differs from the first file")
            if loaded.peak_units != peak_units:
                raise ValueError(f"{nc_file.name}: peak units {loaded.peak_units} differ from {peak_units}")

        for position, year in enumerate(loaded.years):
            records.append((year, {n: loaded.arrays[n][position] for n in REQUIRED_NETCDF_VARIABLES}))

    if not records:
        raise FileNotFoundError(f"No yearly-statistics files in {DATA_DIR.resolve()}")

    records = [r for r in records if START_YEAR <= r[0] <= END_YEAR]
    years = np.array([r[0] for r in records], dtype=int)
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

    records.sort(key=lambda r: r[0])
    cubes = {n: np.stack([r[1][n] for r in records]) for n in REQUIRED_NETCDF_VARIABLES}
    return YearlyStats(
        years=np.array([r[0] for r in records], dtype=int),
        cubes=cubes, peak_units=peak_units, shape=grid[0], transform=grid[1],
    )


def cube(annual: YearlyStats, name: str) -> np.ndarray:
    return annual.cubes[name]


# ------------------------------------------------------------ computation
def peaks_to_celsius(annual: YearlyStats):

    hot, cold = cube(annual, PEAK_MAX), cube(annual, PEAK_MIN)
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


def build_bands(annual: YearlyStats):

    years = annual.years
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

    cold_total = np.sum(min_parts, axis=0)  # shape: (time, lat, lon)
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


# ------------------------------------------------------------- rendering
def hex_to_rgb(color: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError(f"Invalid colour {color!r}; expected '#rrggbb'")
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def palette_rgb(colors: list[str]) -> np.ndarray:
    """RGB colour of every data index 0..MAX_INDEX, shape (MAX_INDEX + 1, 3)."""

    fraction = np.arange(MAX_INDEX + 1) / MAX_INDEX
    palette = np.array([hex_to_rgb(c) for c in colors], dtype=np.float64)

    if DISCRETE_COLORS:
        steps = np.minimum((fraction * len(colors)).astype(np.intp), len(colors) - 1)
        rgb = palette[steps]
    else:
        stops = np.linspace(0.0, 1.0, len(colors))
        rgb = np.stack([np.interp(fraction, stops, palette[:, c]) for c in range(3)], axis=-1)
    return np.rint(rgb).astype(np.uint8)


def to_indices(values: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    """Quantise values to palette indices; missing pixels get NODATA_INDEX."""

    valid = np.isfinite(values)
    fraction = np.where(valid, np.clip((values - vmin) / (vmax - vmin), 0.0, 1.0), 0.0)
    indices = np.rint(fraction * MAX_INDEX).astype(np.uint8)
    indices[~valid] = NODATA_INDEX
    return indices


def reproject_to_webmercator(values: np.ndarray, src_crs, src_transform, src_bounds):
    """Resample a geographic grid onto EPSG:3857 pixels (nearest-neighbour).

    Returns the reprojected array and its true (west, south, east, north) edges
    in WGS84 longitude/latitude.
    """

    height, width = values.shape
    dst_transform, dst_width, dst_height = calculate_default_transform(
        src_crs, WEBMERCATOR_CRS, width, height, *src_bounds
    )
    destination = np.full((dst_height, dst_width), np.nan, dtype=np.float32)
    reproject(
        source=values.astype(np.float32), destination=destination,
        src_transform=src_transform, src_crs=src_crs, src_nodata=np.nan,
        dst_transform=dst_transform, dst_crs=WEBMERCATOR_CRS, dst_nodata=np.nan,
        resampling=Resampling.nearest, init_dest_nodata=True,
    )
    mercator_bounds = array_bounds(dst_height, dst_width, dst_transform)
    lonlat_bounds = transform_bounds(WEBMERCATOR_CRS, WGS84_CRS, *mercator_bounds, densify_pts=21)
    return destination, lonlat_bounds


def write_map(
    values, lonlat_bounds, colors, png_path: Path, json_path: Path,
    column: str, units: str, vmin: float, vmax: float, raw_min: float, raw_max: float,
) -> None:
    """Write a palette-indexed PNG (index 255 = transparent nodata) and its MapLibre sidecar."""

    rgb = palette_rgb(colors)
    image = Image.fromarray(to_indices(values, vmin, vmax))

    palette = np.zeros((NODATA_INDEX + 1, 3), dtype=np.uint8)
    palette[: MAX_INDEX + 1] = rgb
    image.putpalette(palette.reshape(-1).tolist())

    if PNG_SCALE != 1:
        image = image.resize(
            (image.width * PNG_SCALE, image.height * PNG_SCALE), Image.Resampling.NEAREST
        )

    png_path.parent.mkdir(parents=True, exist_ok=True)
    alpha = bytes([255] * NODATA_INDEX + [0])
    image.save(png_path, transparency=alpha)

    west, south, east, north = (round(float(v), 6) for v in lonlat_bounds)
    entries = [*range(0, MAX_INDEX, COLOR_MAP_STEP), MAX_INDEX]
    sidecar = {
        "image": png_path.name,
        "crs": WEBMERCATOR_CRS.to_string(),
        "coordinates": [[west, north], [east, north], [east, south], [west, south]],
        "metric": {
            "column": column,
            "min": round(vmin, 6),
            "max": round(vmax, 6),
            "units": units,
            "raw_min": round(raw_min, 6),
            "raw_max": round(raw_max, 6),
        },
        "nodata": {"palette_index": NODATA_INDEX, "alpha": 0},
        "color_map": [
            {
                "index": i,
                "rgb": [int(c) for c in rgb[i]],
                "value": round(vmin + (vmax - vmin) * i / MAX_INDEX, 4),
            }
            for i in entries
        ],
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(sidecar, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def render_map(
    total, crs, transform, bounds, colors, png_path: Path, json_path: Path, column: str, units: str
) -> None:

    if not np.isfinite(total).any():
        raise ValueError(f"No valid pixels to plot for {png_path.name}")
    if PNG_SCALE < 1:
        raise ValueError("PNG_SCALE must be a positive integer")

    raw_min, raw_max = float(np.nanmin(total)), float(np.nanmax(total))
    print(f"{png_path.name}: min {raw_min:.1f} (lightest), max {raw_max:.1f} (darkest)")
    vmin, vmax = raw_min, raw_max

    if vmax == vmin:
        print(f"  All pixels equal ({vmin:.1f}); the whole map will be the lightest colour.")
        vmax = vmin + 1.0

    projected, lonlat_bounds = reproject_to_webmercator(total, crs, transform, bounds)
    if not np.isfinite(projected).any():
        raise ValueError(f"Reprojection left no valid pixels for {png_path.name}")

    write_map(
        projected, lonlat_bounds, colors, png_path, json_path,
        column, units, vmin, vmax, raw_min, raw_max,
    )


def render_pngs(tif_path: Path):

    with rasterio.open(tif_path) as src:

        index = {desc: i for i, desc in enumerate(src.descriptions, start=1)}
        missing = [n for n in MIN_BAND_NAMES + MAX_BAND_NAMES if n not in index]

        if missing:
            raise KeyError(f"Bands missing in {tif_path}: {missing}")

        missing = [n for n in (COLD_TOTAL_BAND, HEAT_TOTAL_BAND) if n not in index]
        if missing:
            raise KeyError(f"Bands missing in {tif_path}: {missing}")

        if src.crs is None:
            raise ValueError(f"{tif_path} has no CRS")

        cold_days = src.read(index[COLD_TOTAL_BAND]).astype(np.float64)
        heat_days = src.read(index[HEAT_TOTAL_BAND]).astype(np.float64)
        crs, transform, bounds = src.crs, src.transform, src.bounds

    render_map(cold_days, crs, transform, bounds, COLD_COLORS,
               COLD_PNG_PATH, COLD_JSON_PATH, COLD_TOTAL_BAND, "days")
    render_map(heat_days, crs, transform, bounds, HEAT_COLORS,
               HEAT_PNG_PATH, HEAT_JSON_PATH, HEAT_TOTAL_BAND, "days")


def main():
    
    annual = load_yearly_statistics()
    print(f"Years used ({annual.years.size}): {annual.years.tolist()}")
    print(f"Grid: {annual.shape[0]} x {annual.shape[1]} pixels")

    bands = build_bands(annual)
    write_geotiff(TIF_PATH, bands, annual.transform)
    print(f"Wrote {TIF_PATH} ({len(bands)} bands)")

    render_pngs(TIF_PATH)
    print(f"Wrote {COLD_PNG_PATH} + {COLD_JSON_PATH} and {HEAT_PNG_PATH} + {HEAT_JSON_PATH}")


if __name__ == "__main__":
    main()
