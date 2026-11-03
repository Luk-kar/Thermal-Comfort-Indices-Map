"""Check that rasters are reprojected to Web Mercator without changing values or the input array."""

import numpy as np
import pytest

pytest.importorskip("rasterio")

from utci_map.source.products.maps.reprojection import reproject_to_webmercator


def test_reprojection_preserves_values_and_input(layer):
    before = layer.values.copy()

    projected, bounds = reproject_to_webmercator(layer.values, layer.grid)

    assert projected.ndim == 2
    assert projected.dtype == np.float32
    assert np.isfinite(projected).any()
    np.testing.assert_array_equal(projected[np.isfinite(projected)], 12.0)
    np.testing.assert_array_equal(layer.values, before)
    west, south, east, north = bounds
    assert west < east and south < north


def test_land_geometries_mask_sea_on_the_projected_grid(layer):
    """Land covers the western half of the 0-4° E layer, so the last projected column is sea."""
    land = {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 4], [0, 4], [0, 0]]]}

    projected, _ = reproject_to_webmercator(layer.values, layer.grid, land_geometries=[land])

    assert np.isfinite(projected).any()
    assert np.isnan(projected[:, -1]).all()
    np.testing.assert_array_equal(layer.values, 12.0)
