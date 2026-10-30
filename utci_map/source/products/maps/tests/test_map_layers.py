"""Tests for grouped raster metadata and layer rendering."""

from dataclasses import FrozenInstanceError
import json

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("rasterio")
from rasterio.transform import array_bounds, from_origin

from utci_map.source.products.maps.png_maps import (
    MapLayer, MapOutput, RasterGrid, RenderOptions, WGS84_CRS,
    _render_map, _reproject_to_webmercator,
)


@pytest.fixture
def layer():
    
    transform = from_origin(0, 4, 0.5, 0.5)
    return MapLayer(
        values=np.full((8, 8), 12., dtype=float),
        grid=RasterGrid(
            crs=WGS84_CRS,
            grid_transform=transform,
            bounds=array_bounds(8, 8, transform),
        ),
        metric_band_name="test_stress_days",
        metric_units="days",
    )


@pytest.fixture
def output(tmp_path):
    
    return MapOutput(
        png_path=tmp_path / "map.png",
        json_path=tmp_path / "map.json",
        colors=("#000000", "#ffffff"),
    )


def test_grouped_data_blocks_field_reassignment(layer):
    
    with pytest.raises(FrozenInstanceError):
        layer.grid.crs = None
    with pytest.raises(FrozenInstanceError):
        layer.metric_units = "hours"


def test_map_layer_shares_values_and_grid_without_array_equality(layer):
    
    other = MapLayer(
        values=layer.values, grid=layer.grid,
        metric_band_name="other", metric_units="days",
    )
    assert other.values is layer.values
    assert other.grid is layer.grid
    assert other != layer
    other.values[0, 0] = 20.
    assert layer.values[0, 0] == 20.


def test_reprojection_accepts_grouped_grid_and_preserves_input(layer):
    
    before = layer.values.copy()
    projected, bounds = _reproject_to_webmercator(layer.values, layer.grid)
    assert projected.ndim == 2
    assert projected.dtype == np.float32
    assert np.isfinite(projected).any()
    np.testing.assert_array_equal(projected[np.isfinite(projected)], 12.)
    np.testing.assert_array_equal(layer.values, before)
    west, south, east, north = bounds
    assert west < east and south < north


def test_projected_grid_is_used_for_land_mask(layer):
    
    land = {"type": "Polygon", "coordinates": [[
        [0, 0], [2, 0], [2, 4], [0, 4], [0, 0],
    ]]}
    projected, _ = _reproject_to_webmercator(
        layer.values, layer.grid, land_geometries=[land],
    )
    assert np.isfinite(projected).any()
    assert np.isnan(projected[:, -1]).all()
    np.testing.assert_array_equal(layer.values, 12.)


def test_render_map_uses_layer_metadata(layer, output):
    
    _render_map(layer, output, RenderOptions(coastline_path=None))
    metadata = json.loads(output.json_path.read_text())
    assert metadata["metric"]["column"] == layer.metric_band_name
    assert metadata["metric"]["units"] == layer.metric_units
    assert metadata["metric"]["raw_min"] == 12.
    assert metadata["metric"]["raw_max"] == 12.
    with Image.open(output.png_path) as image:
        assert image.mode == "P"
        assert np.any(np.array(image.convert("RGBA"))[:, :, 3] == 255)


@pytest.mark.parametrize("case", ["missing_values", "invalid_scale"])
def test_render_map_preserves_validation(layer, output, case):
    
    options = RenderOptions(coastline_path=None)
    if case == "missing_values":
        layer.values[:] = np.nan
        message = "No valid pixels"
    else:
        options = RenderOptions(png_scale=0, coastline_path=None)
        message = "png_scale must be a positive integer"
    with pytest.raises(ValueError, match=message):
        _render_map(layer, output, options)
