"""Check that coastline files are validated and land polygons become the expected pixel masks."""

import json

import numpy as np
import pytest

pytest.importorskip("rasterio")
from rasterio.crs import CRS
from rasterio.transform import from_bounds, from_origin
from rasterio.warp import transform_bounds

from utci_map.source.products.maps.land_mask import land_mask, load_land_geometries
from utci_map.source.products.maps.models import WEBMERCATOR_CRS, WGS84_CRS, RasterGrid


def test_loads_polygon_features(west_half_coastline):
    geometries = load_land_geometries(west_half_coastline)

    assert [geometry["type"] for geometry in geometries] == ["Polygon"]


@pytest.mark.parametrize(
    "features",
    [
        [],
        [{"geometry": None}],
        [{"geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}],
    ],
)
def test_invalid_coastline_geometries_fail(tmp_path, features):
    path = tmp_path / "invalid.geojson"
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
    )

    with pytest.raises(ValueError):
        load_land_geometries(path)


def test_land_mask_preserves_holes():
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]],
            [[1, 1], [1, 3], [3, 3], [3, 1], [1, 1]],
        ],
    }
    grid = RasterGrid(crs=WGS84_CRS, grid_transform=from_origin(0, 4, 1, 1), bounds=(0, 0, 4, 4))

    mask = land_mask([geometry], (4, 4), grid)

    expected = np.ones((4, 4), dtype=bool)
    expected[1:3, 1:3] = False
    np.testing.assert_array_equal(mask, expected)


def test_land_mask_reprojects_polygons():
    """A WGS84 polygon over the western half of a Web Mercator grid masks its first two columns."""
    geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 2], [0, 2], [0, 0]]]}
    bounds = transform_bounds(WGS84_CRS, WEBMERCATOR_CRS, 0, 0, 2, 2)
    grid = RasterGrid(crs=WEBMERCATOR_CRS, grid_transform=from_bounds(*bounds, 4, 4), bounds=bounds)

    mask = land_mask([geometry], (4, 4), grid)

    expected = np.zeros((4, 4), dtype=bool)
    expected[:, :2] = True
    np.testing.assert_array_equal(mask, expected)


@pytest.mark.parametrize("epsg", [4326, 3857])
def test_land_mask_keeps_intersecting_pixels_without_land_at_centers(epsg):
    """
    Keep narrow land features on geographic and projected grids.

    The polygon intersects both pixels in the first column, but contains
    neither pixel center. Pixels in the second column remain sea.
    """
    geometry = {
        "type": "Polygon",
        "coordinates": [[[0.05, 0.1], [0.15, 0.1], [0.15, 1.9], [0.05, 1.9], [0.05, 0.1]]],
    }
    crs = CRS.from_epsg(epsg)
    bounds = (0.0, 0.0, 2.0, 2.0)
    if crs != WGS84_CRS:
        bounds = transform_bounds(WGS84_CRS, crs, *bounds)
    grid = RasterGrid(
        crs=crs, grid_transform=from_bounds(*bounds, width=2, height=2), bounds=bounds
    )

    mask = land_mask([geometry], (2, 2), grid)

    np.testing.assert_array_equal(mask, [[True, False], [True, False]])
