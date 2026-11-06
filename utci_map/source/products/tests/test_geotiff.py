"""Check that summary bands are written to a GeoTIFF with their grid, metadata and period."""

import numpy as np
import pytest

pytest.importorskip("rasterio")
import rasterio

from utci_map.source.products.geotiff import write_geotiff

COLD_DAYS = np.array([[1, np.nan], [2, 3]], dtype=float)
RECORD_YEAR = np.array([[2016, np.nan], [2017, 2018]], dtype=float)


@pytest.fixture
def summary_path(tmp_path, grid_transform):
    """Write a day-count band and a record-year band, each with a missing pixel."""
    path = tmp_path / "nested" / "summary.tif"
    bands = [("cold_days", COLD_DAYS, "days"), ("record_year", RECORD_YEAR, "year")]

    assert write_geotiff(path, bands, grid_transform, start_year=2016, end_year=2018) is None

    return path


def test_writes_grid_crs_and_float32_storage_with_nan_nodata(summary_path, grid_transform):
    with rasterio.open(summary_path) as result:
        assert (result.count, result.height, result.width) == (2, 2, 2)
        assert result.crs.to_epsg() == 4326
        assert result.transform == grid_transform
        assert result.dtypes == ("float32", "float32")
        assert np.isnan(result.nodata)


def test_writes_values_with_missing_pixels(summary_path):
    with rasterio.open(summary_path) as result:
        values = result.read()

    np.testing.assert_allclose(values, np.stack([COLD_DAYS, RECORD_YEAR]), equal_nan=True)


def test_writes_band_names_units_and_period_tags(summary_path):
    with rasterio.open(summary_path) as result:
        assert result.descriptions == ("cold_days", "record_year")
        assert result.tags(1)["units"] == "days"
        assert result.tags(2)["units"] == "year"
        assert result.tags()["start_year"] == "2016"
        assert result.tags()["end_year"] == "2018"


def test_replaces_existing_geotiff(tmp_path, grid_transform):
    path = tmp_path / "summary.tif"

    for value in (1, 2):
        bands = [("days", np.full((2, 2), value), "days")]
        write_geotiff(path, bands, grid_transform, start_year=2016, end_year=2018)

    with rasterio.open(path) as result:
        np.testing.assert_array_equal(result.read(1), np.full((2, 2), 2))
