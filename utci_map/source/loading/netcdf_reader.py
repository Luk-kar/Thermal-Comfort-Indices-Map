"""Read and validate the variables and time steps of one NetCDF file."""

import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import rasterio

from utci_map.source.models import FileRecords, FieldRecords
from utci_map.source.schema import PEAK_MAX, PEAK_MIN, SELECTED_NETCDF_FIELDS

def read_yearly_file(nc_file: Path) -> FileRecords | None:
    """
    Read selected UTCI fields from one yearly-statistics NetCDF file.

    Return None if the file does not contain the yearly peak fields.
    """
    uris = get_netcdf_field_uris(nc_file)

    if not _is_yearly_statistics_file(uris):
        return None

    _validate_selected_fields(uris, nc_file)

    return _read_selected_fields(uris, nc_file)

def _is_yearly_statistics_file(uris: dict[str, str]) -> bool:
    """Identify files containing yearly maximum and minimum UTCI fields."""
    return PEAK_MAX in uris and PEAK_MIN in uris


def _validate_selected_fields(
    uris: dict[str, str],
    nc_file: Path,
) -> None:
    """Ensure all selected UTCI fields are available in the file."""
    missing = [name for name in SELECTED_NETCDF_FIELDS if name not in uris]

    if missing:
        raise KeyError(f"{nc_file.name} lacks fields: {missing}")


def _read_selected_fields(
    uris: dict[str, str],
    nc_file: Path,
) -> FileRecords:
    """Read selected fields and ensure they share the same years and grid."""
    reference_name = SELECTED_NETCDF_FIELDS[0]
    reference = read_variable(
        uris[reference_name],
        nc_file,
        reference_name,
    )

    arrays = {reference_name: reference.arrays}
    peak_units = {}

    if reference.peak_unit is not None:
        peak_units[reference_name] = reference.peak_unit

    for name in SELECTED_NETCDF_FIELDS[1:]:
        field = read_variable(uris[name], nc_file, name)

        check_matches_reference(
            field,
            reference,
            nc_file,
            name,
            reference_name,
        )

        arrays[name] = field.arrays
        if field.peak_unit is not None:
            peak_units[name] = field.peak_unit

    return FileRecords(
        years=reference.years,
        arrays=arrays,
        peak_units=peak_units,
        shape=reference.shape,
        transform=reference.transform,
    )

def get_netcdf_field_uris(nc_file: Path) -> dict[str, str]:
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


def read_variable(uri: str, nc_file: Path, name: str) -> FieldRecords:
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

        return FieldRecords(
            years=[year_of_time_coordinate(tags, src.tags(b)) for b in src.indexes],
            arrays=[read_physical(src, b, name, nc_file) for b in src.indexes],
            shape=src.shape,
            transform=src.transform,
            peak_unit=read_peak_unit(src, tags, name) if name in (PEAK_MAX, PEAK_MIN) else None,
        )


def check_matches_reference(
    variable: FieldRecords, reference: FieldRecords,
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
