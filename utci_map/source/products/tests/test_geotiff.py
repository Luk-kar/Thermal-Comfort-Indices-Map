"""Check that summary bands are written to a GeoTIFF with their grid, metadata and period."""

import numpy as np
import pytest

pytest.importorskip("rasterio")
import rasterio
from rasterio.transform import from_origin

from utci_map.source.products.geotiff import write_geotiff


def test_writes_values_grid_band_metadata_and_period(tmp_path):
    """
    Write a day-count band and a record-year band, each with a missing pixel, and
    check the grid, CRS, float32 storage, NaN nodata, band names, units and period tags.
    """
    path = tmp_path / "nested" / "summary.tif"
    transform = from_origin(-24, 67, 0.25, 0.25)
    first = np.array([[1, np.nan], [2, 3]], dtype=float)
    second = np.array([[2016, np.nan], [2017, 2018]], dtype=float)

    bands = [("cold_days", first, "days"), ("record_year", second, "year")]

    assert write_geotiff(path, bands, transform, start_year=2016, end_year=2018) is None

    with rasterio.open(path) as result:
        assert (result.count, result.height, result.width) == (2, 2, 2)
        assert result.crs.to_epsg() == 4326
        assert result.transform == transform
        assert result.dtypes == ("float32", "float32")
        assert np.isnan(result.nodata)
        assert result.descriptions == ("cold_days", "record_year")
        assert result.tags(1)["units"] == "days"
        assert result.tags(2)["units"] == "year"
        assert result.tags()["start_year"] == "2016"
        assert result.tags()["end_year"] == "2018"
        np.testing.assert_allclose(result.read(), np.stack([first, second]), equal_nan=True)


def test_replaces_existing_geotiff(tmp_path):
    path = tmp_path / "summary.tif"
    transform = from_origin(-24, 67, 0.25, 0.25)

    for value in (1, 2):
        bands = [("days", np.full((2, 2), value), "days")]
        write_geotiff(path, bands, transform, start_year=2016, end_year=2018)

    with rasterio.open(path) as result:
        np.testing.assert_array_equal(result.read(1), np.full((2, 2), 2))
