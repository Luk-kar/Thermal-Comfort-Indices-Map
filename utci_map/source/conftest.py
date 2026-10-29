"""Small deterministic inputs shared by public-entry-point tests."""

from datetime import datetime

import numpy as np
import pytest


@pytest.fixture
def yearly_statistics():
    """Provide three years of synthetic UTCI statistics on a 4 x 4 grid.

    The fixture covers 2016–2018. Yearly maximum and minimum values are
    in degrees Celsius, and each threshold field contains increasing
    yearly day counts. The top-left pixel is missing (NaN) in every field
    and year, so tests can check missing-value handling.
    """

    from rasterio.transform import from_origin
    from utci_map.source.models import YearlyStats

    shape = (3, 4, 4)
    def values(sequence):
        result = np.broadcast_to(np.array(sequence, dtype=float)[:, None, None], shape).copy()
        result[:, 0, 0] = np.nan
        return result

    cubes = {
        "utci_yearly_max": values([30, 31, 32]),
        "utci_yearly_min": values([-20, -21, -22]),
    }

    for threshold, count in [(26, 10), (32, 6), (38, 3), (46, 1)]:
        cubes[f"utci_days_above_{threshold}_daily_max"] = values([count, count + 1, count + 2])

    for threshold, count in [(-40, 1), (-27, 3), (-13, 6), (0, 10), (9, 15)]:
        cubes[f"utci_days_below_{threshold}_daily_min"] = values([count, count + 1, count + 2])

    return YearlyStats(
        years=np.array([2016, 2017, 2018]), cubes=cubes,
        peak_units={"utci_yearly_max": "degC", "utci_yearly_min": "degC"},
        shape=(4, 4), transform=from_origin(-24, 67, 0.25, 0.25),
    )


@pytest.fixture
def netcdf_factory(tmp_path):
    """
    Provide a factory for creating temporary NetCDF files with UTCI statistics.

    Each file contains yearly maximum and minimum UTCI fields and cumulative
    day counts for heat- and cold-stress thresholds on a 4 x 4 geographic grid.
    Values increase with each time step, and the top-left pixel is marked
    as missing in every field and year.

    Tests can customise the years, omitted fields, peak units, grid location,
    peak scale/offset, and calendar to exercise valid and invalid inputs.
    The factory returns the created file's path so tests can pass it directly
    to the loader without mocking its functions.
    """

    import rasterio
    from scipy.io import netcdf_file

    with rasterio.Env() as env:
        if "netCDF" not in env.drivers():
            pytest.skip("Rasterio/GDAL requires the netCDF driver for these tests")

    def create(name, years=(2016, 2017), missing=(), units="degC", west=-24.0,
               peak_scale=1.0, peak_offset=0.0, calendar="standard"):

        path = tmp_path / name
        values = {"utci_yearly_max": 30, "utci_yearly_min": -20}
        values.update({f"utci_days_above_{t}_daily_max": c for t, c in [(26, 10), (32, 6), (38, 3), (46, 1)]})
        values.update({f"utci_days_below_{t}_daily_min": c for t, c in [(-40, 1), (-27, 3), (-13, 6), (0, 10), (9, 15)]})

        # Write time and geographic coordinates, UTCI fields, and metadata
        # to a real NetCDF file that the production loader can read.
        with netcdf_file(path, "w") as nc:

            nc.Conventions = "CF-1.8"
            for dim, length in [("time", len(years)), ("lat", 4), ("lon", 4)]:
                nc.createDimension(dim, length)
            time = nc.createVariable("time", "f8", ("time",))
            time.units = "days since 2010-01-01 00:00:00"
            time.calendar = calendar
            time.standard_name = "time"
            time[:] = [(datetime(y, 1, 1) - datetime(2010, 1, 1)).days for y in years]
            lat = nc.createVariable("lat", "f8", ("lat",))
            lat.units = "degrees_north"
            lat.standard_name = "latitude"
            lat.axis = "Y"
            lat[:] = 67 - 0.125 - np.arange(4) * 0.25
            lon = nc.createVariable("lon", "f8", ("lon",))
            lon.units = "degrees_east"
            lon.standard_name = "longitude"
            lon.axis = "X"
            lon[:] = west + 0.125 + np.arange(4) * 0.25
            for field, base in values.items():
                if field in missing:
                    continue
                var = nc.createVariable(field, "i2", ("time", "lat", "lon"))
                var._FillValue = np.int16(-9999)
                var.units = units if field.startswith("utci_yearly_") else "days"
                data = np.broadcast_to(np.arange(len(years))[:, None, None] + base, (len(years), 4, 4)).astype("i2").copy()
                data[:, 0, 0] = -9999
                if field.startswith("utci_yearly_"):
                    var.scale_factor = np.float64(peak_scale)
                    var.add_offset = np.float64(peak_offset)
                var[:] = data
        return path
    return create
