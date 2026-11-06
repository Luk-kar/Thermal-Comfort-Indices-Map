"""Small deterministic inputs shared by public-entry-point tests."""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pytest

GRID_SIZE = 4
PIXEL_DEGREES = 0.25
NORTH = 67.0
WEST = -24.0
FILL_VALUE = -9999

# Value of each field in the first year; later years add 1, except as noted in yearly_statistics.
PEAK_BASE_VALUES = {"utci_yearly_max": 30, "utci_yearly_min": -20}
ABOVE_BASE_COUNTS = {26: 10, 32: 6, 38: 3, 46: 1}
BELOW_BASE_COUNTS = {-40: 1, -27: 3, -13: 6, 0: 10, 9: 15}
BASE_VALUES = {
    **PEAK_BASE_VALUES,
    **{f"utci_days_above_{t}_daily_max": count for t, count in ABOVE_BASE_COUNTS.items()},
    **{f"utci_days_below_{t}_daily_min": count for t, count in BELOW_BASE_COUNTS.items()},
}


@pytest.fixture
def grid_transform():
    """Provide the synthetic grid's transform: 0.25° pixels from 24° W, 67° N."""
    from rasterio.transform import from_origin

    return from_origin(WEST, NORTH, PIXEL_DEGREES, PIXEL_DEGREES)


@pytest.fixture
def yearly_statistics(grid_transform):
    """
    Provide three years of synthetic UTCI statistics on a 4 x 4 grid.

    The fixture covers 2016–2018. Yearly maximum and minimum values are
    in degrees Celsius, and each threshold field contains increasing
    yearly day counts. The top-left pixel is missing (NaN) in every field
    and year, so tests can check missing-value handling.
    """
    from utci_map.source.contracts import YearlyStats

    years = np.array([2016, 2017, 2018])
    shape = (years.size, GRID_SIZE, GRID_SIZE)

    cubes = {}
    for name, base in BASE_VALUES.items():
        # The yearly minimum falls each year, so the last year holds both UTCI records.
        step = -1.0 if name == "utci_yearly_min" else 1.0
        yearly = base + step * np.arange(years.size, dtype=float)
        cubes[name] = np.broadcast_to(yearly[:, None, None], shape).copy()
        cubes[name][:, 0, 0] = np.nan

    return YearlyStats(
        years=years,
        cubes=cubes,
        peak_units={name: "degC" for name in PEAK_BASE_VALUES},
        shape=(GRID_SIZE, GRID_SIZE),
        transform=grid_transform,
    )


@pytest.fixture
def netcdf_factory(tmp_path):
    """
    Provide a factory for creating temporary NetCDF files with UTCI statistics.

    Each file contains yearly maximum and minimum UTCI fields and cumulative
    day counts for heat- and cold-stress thresholds on a 4 x 4 geographic grid.
    Values increase with each time step, and the top-left pixel is marked
    as missing in every field and year.

    Tests can customize the years, omitted fields, peak units, grid location,
    peak scale/offset, and calendar through the keyword arguments of
    _NetcdfOptions. The factory returns the created file's path so tests can
    pass it directly to the loader without mocking its functions.
    """
    import rasterio

    with rasterio.Env() as env:
        if "netCDF" not in env.drivers():
            pytest.skip("Rasterio/GDAL requires the netCDF driver for these tests")

    def create(name, **options):
        path = tmp_path / name
        _write_netcdf(path, _NetcdfOptions(**options))

        return path

    return create


@dataclass(frozen=True, kw_only=True)
class _NetcdfOptions:
    """Settings a test can change in a generated NetCDF file."""

    years: tuple[int, ...] = (2016, 2017)
    missing: tuple[str, ...] = ()
    units: str = "degC"
    west: float = WEST
    peak_scale: float = 1.0
    peak_offset: float = 0.0
    calendar: str = "standard"


def _write_netcdf(path, options):
    """Write CF coordinates and every UTCI field not listed in options.missing."""
    from scipy.io import netcdf_file

    fields = {name: base for name, base in BASE_VALUES.items() if name not in options.missing}

    with netcdf_file(path, "w") as nc:
        nc.Conventions = "CF-1.8"
        _write_coordinates(nc, options)

        for field, base in fields.items():
            _write_field(nc, field, base, options)


def _write_coordinates(nc, options):
    """Write the time axis (days since 2010) and the 0.25° lat/lon cell centers."""
    for dim, length in [("time", len(options.years)), ("lat", GRID_SIZE), ("lon", GRID_SIZE)]:
        nc.createDimension(dim, length)

    time = nc.createVariable("time", "f8", ("time",))
    time.units = "days since 2010-01-01 00:00:00"
    time.calendar = options.calendar
    time.standard_name = "time"
    time[:] = [(datetime(year, 1, 1) - datetime(2010, 1, 1)).days for year in options.years]

    centers = PIXEL_DEGREES / 2 + np.arange(GRID_SIZE) * PIXEL_DEGREES
    _write_axis(nc, "lat", units="degrees_north", axis="Y", values=NORTH - centers)
    _write_axis(nc, "lon", units="degrees_east", axis="X", values=options.west + centers)


def _write_axis(nc, name, *, units, axis, values):
    """Write one CF coordinate variable."""
    variable = nc.createVariable(name, "f8", (name,))
    variable.units = units
    variable.standard_name = {"lat": "latitude", "lon": "longitude"}[name]
    variable.axis = axis
    variable[:] = values


def _write_field(nc, field, base, options):
    """Write one int16 field counting up from base per year, with the top-left pixel missing."""
    is_peak = field in PEAK_BASE_VALUES
    variable = nc.createVariable(field, "i2", ("time", "lat", "lon"))
    variable._FillValue = np.int16(FILL_VALUE)
    variable.units = options.units if is_peak else "days"

    if is_peak:
        variable.scale_factor = np.float64(options.peak_scale)
        variable.add_offset = np.float64(options.peak_offset)

    shape = (len(options.years), GRID_SIZE, GRID_SIZE)
    data = np.broadcast_to((base + np.arange(len(options.years)))[:, None, None], shape)
    data = data.astype("i2")
    data[:, 0, 0] = FILL_VALUE
    variable[:] = data
