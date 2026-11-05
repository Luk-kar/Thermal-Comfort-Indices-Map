"""Read and validate the variables and time steps of one NetCDF file."""

import logging
import math
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import rasterio
from rasterio.io import DatasetReader
from rasterio.transform import Affine

from utci_map.source.contracts import (
    PEAK_MAX,
    PEAK_MIN,
    SELECTED_NETCDF_FIELDS,
    FieldRecords,
    FileRecords,
)
from utci_map.source.runlog import logged_file_io

_LOGGER = logging.getLogger(__name__)

# Date part of the time units, e.g. "2015-01-01" or "2015-1-1".
_DATE_PATTERN = r"(\d{4})-(\d{1,2})-(\d{1,2})"
# Optional time part, e.g. " 00:00:00", "T06:30:00" or " 12:00:00.5".
_TIME_PATTERN = r"(?:[ T](\d{1,2}):(\d{2}):(\d{2})(?:\.\d+)?)"
_TIMEZONE_PATTERN = r"(?:UTC|Z)"
TIME_UNITS_RE = re.compile(
    rf"^(seconds|hours|days) since {_DATE_PATTERN}{_TIME_PATTERN}?(?: ?{_TIMEZONE_PATTERN})?$"
)
SECONDS_PER_UNIT = {"seconds": 1.0, "hours": 3600.0, "days": 86400.0}
SUPPORTED_CALENDARS = frozenset({"standard", "gregorian", "proleptic_gregorian"})
GEOGRAPHIC_UNITS = {"lat#units": "degrees_north", "lon#units": "degrees_east"}

# Tolerances for floating-point noise in grid transforms.
TRANSFORM_TOLERANCE = 1e-9
ROTATION_TOLERANCE = 1e-12


def read_yearly_file(nc_file: Path) -> FileRecords | None:
    """
    Read selected UTCI fields from one yearly-statistics NetCDF file.

    Return None if the file does not contain the yearly peak fields.
    Raise KeyError if it has the peak fields but lacks another selected field,
    and ValueError if a field has an unsupported grid, time axis or scaling.
    """
    with logged_file_io(_LOGGER, "Read", nc_file):
        records = _read_yearly_file(nc_file)

    if records is None:
        _LOGGER.info("Skipped %s: no yearly peak fields", nc_file.name)

    return records


def transforms_match(a: Affine, b: Affine) -> bool:
    """Check that two rasters share a grid, tolerating tiny floating-point differences."""
    return bool(np.allclose(tuple(a)[:6], tuple(b)[:6], rtol=0.0, atol=TRANSFORM_TOLERANCE))


def _read_yearly_file(nc_file: Path) -> FileRecords | None:
    """Read the selected fields, or return None for a file without yearly peaks."""
    uris = _field_uris(nc_file)

    if PEAK_MAX not in uris or PEAK_MIN not in uris:
        return None

    missing = [name for name in SELECTED_NETCDF_FIELDS if name not in uris]
    if missing:
        raise KeyError(f"{nc_file.name} lacks fields: {missing}")

    return _read_selected_fields(uris, nc_file)


def _field_uris(nc_file: Path) -> dict[str, str]:
    """
    Map each NetCDF variable name to its GDAL subdataset URI.

    GDAL exposes each variable as a subdataset URI ending in the variable name,
    e.g. 'NETCDF:"utci_2015.nc":utci_yearly_max'
    -> {"utci_yearly_max": 'NETCDF:"utci_2015.nc":utci_yearly_max'}.
    """
    with rasterio.open(nc_file) as parent:
        uris = parent.subdatasets

    return {uri.rsplit(":", 1)[-1].strip('"'): uri for uri in uris}


def _read_selected_fields(uris: dict[str, str], nc_file: Path) -> FileRecords:
    """Read selected fields and ensure they share the years and grid of the first one."""
    reference_name, *other_names = SELECTED_NETCDF_FIELDS
    reference = _read_field(uris[reference_name], nc_file, reference_name)
    fields = {reference_name: reference}

    for name in other_names:
        field = _read_field(uris[name], nc_file, name)
        if field.years != reference.years:
            raise ValueError(f"{nc_file.name}:{name}: time axis differs from {reference_name}")
        if field.shape != reference.shape or not transforms_match(
            field.transform, reference.transform
        ):
            raise ValueError(f"{nc_file.name}:{name}: grid differs from {reference_name}")
        fields[name] = field

    return FileRecords(
        years=reference.years,
        arrays={name: field.arrays for name, field in fields.items()},
        peak_units={
            name: field.peak_unit for name, field in fields.items() if field.peak_unit is not None
        },
        shape=reference.shape,
        transform=reference.transform,
    )


def _read_field(uri: str, nc_file: Path, name: str) -> FieldRecords:
    """Open one variable, validate its grid and time axis, and read all its time steps."""
    with rasterio.open(uri) as src:
        tags = src.tags()
        _check_geographic(tags, nc_file, name)
        _check_north_up_grid(src.transform, nc_file, name)
        if not src.indexes:
            raise ValueError(f"{nc_file.name}:{name}: no time steps")

        return FieldRecords(
            years=[_year_of_time_step(tags, src.tags(band)) for band in src.indexes],
            arrays=[_read_physical(src, band, name, nc_file) for band in src.indexes],
            shape=src.shape,
            transform=src.transform,
            peak_unit=_read_peak_unit(src, tags, name) if name in (PEAK_MAX, PEAK_MIN) else None,
        )


def _check_geographic(dataset_tags: dict[str, str], nc_file: Path, name: str) -> None:
    """Reject coordinates whose declared units are not geographic degrees."""
    for key, expected in GEOGRAPHIC_UNITS.items():
        found = dataset_tags.get(key)
        if found is not None and found != expected:
            raise ValueError(f"{nc_file.name}:{name}: {key}={found!r}, expected {expected!r}")


def _check_north_up_grid(transform: Affine, nc_file: Path, name: str) -> None:
    """Reject rotated or south-up grids, which the rest of the pipeline can't handle."""
    if (
        transform.a <= 0
        or transform.e >= 0
        or abs(transform.b) > ROTATION_TOLERANCE
        or abs(transform.d) > ROTATION_TOLERANCE
    ):
        raise ValueError(f"{nc_file.name}:{name}: grid is not an unrotated north-up raster")


def _year_of_time_step(dataset_tags: dict[str, str], band_tags: dict[str, str]) -> int:
    """
    Convert a NetCDF time step, stored as an offset from a reference date, into its year.

    E.g. 8760 with units "hours since 2015-01-01" -> 2016.
    """
    _check_calendar(dataset_tags.get("time#calendar"))
    unit, origin = _parse_time_units(dataset_tags.get("time#units"))

    raw = band_tags.get("NETCDF_DIM_time")
    try:
        offset = float(raw) if raw is not None else math.nan
    except ValueError:
        offset = math.nan
    if not math.isfinite(offset):
        raise ValueError(f"Invalid time coordinate (tag 'NETCDF_DIM_time'): {raw!r}")

    return (origin + timedelta(seconds=offset * SECONDS_PER_UNIT[unit])).year


def _check_calendar(calendar_name: str | None) -> None:
    """Reject calendars whose dates don't follow the Gregorian calendar."""
    if calendar_name not in SUPPORTED_CALENDARS:
        raise ValueError(
            f"Unsupported or missing time calendar (tag 'time#calendar'): {calendar_name!r}; "
            f"expected one of {sorted(SUPPORTED_CALENDARS)}"
        )


def _parse_time_units(units: str | None) -> tuple[str, datetime]:
    """
    Split CF time units into the offset unit and the reference date.

    E.g. "hours since 2015-01-01 00:00:00" -> ("hours", datetime(2015, 1, 1, tzinfo=UTC)).
    """
    match = TIME_UNITS_RE.match(units) if units is not None else None
    if not match:
        raise ValueError(
            f"Unsupported or missing time units (tag 'time#units'): {units!r}; "
            "expected e.g. 'hours since 2015-01-01 00:00:00'"
        )

    unit, year, month, day, hour, minute, second = match.groups()
    origin = datetime(
        int(year),
        int(month),
        int(day),
        int(hour or 0),
        int(minute or 0),
        int(second or 0),
        tzinfo=UTC,
    )
    return unit, origin


def _read_physical(src: DatasetReader, band: int, name: str, nc_file: Path) -> np.ndarray:
    """Read one band as a (height, width) array, with NaN for missing values and scaling applied."""
    scale = float(src.scales[band - 1])
    offset = float(src.offsets[band - 1])

    if not math.isfinite(scale) or scale <= 0:
        raise ValueError(f"{nc_file.name}:{name}: invalid scale_factor {scale!r}")
    if not math.isfinite(offset):
        raise ValueError(f"{nc_file.name}:{name}: invalid add_offset {offset!r}")

    raw = src.read(band, masked=True).astype(np.float64)
    values = raw.filled(np.nan) * scale + offset
    values[~np.isfinite(values)] = np.nan
    return values


def _read_peak_unit(src: DatasetReader, dataset_tags: dict[str, str], name: str) -> str:
    """Find the units of a yearly peak variable, or '' if the file doesn't declare any."""
    unit = src.units[0] or src.tags(1).get("units") or dataset_tags.get(f"{name}#units") or ""
    return str(unit)
