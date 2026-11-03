"""Check the defaults, immutability and keyword-only construction of the map data contracts."""

from dataclasses import FrozenInstanceError

import pytest

pytest.importorskip("rasterio")

from utci_map.source.config import COASTLINE_PATH
from utci_map.source.products.maps.models import MapLayer, MapOutput, RenderOptions


def test_render_options_default_to_configured_settings():
    defaults = RenderOptions()

    assert defaults.png_scale == 1
    assert defaults.discrete_colors is False
    assert defaults.coastline_path == COASTLINE_PATH


def test_settings_and_outputs_cannot_be_reassigned(output):
    with pytest.raises(FrozenInstanceError):
        RenderOptions().png_scale = 2
    with pytest.raises(FrozenInstanceError):
        output.png_path = output.json_path


def test_settings_and_outputs_require_keyword_arguments(output):
    with pytest.raises(TypeError):
        RenderOptions(2)
    with pytest.raises(TypeError):
        MapOutput(output.png_path, output.json_path, ("#000000", "#ffffff"))


def test_layer_and_grid_fields_cannot_be_reassigned(layer):
    with pytest.raises(FrozenInstanceError):
        layer.grid.crs = None
    with pytest.raises(FrozenInstanceError):
        layer.metric_units = "hours"


def test_map_layer_shares_values_and_grid_without_array_equality(layer):
    """Layers compare by identity, and in-place value changes show through every sharer."""
    other = MapLayer(
        values=layer.values, grid=layer.grid, metric_band_name="other", metric_units="days"
    )

    assert other.values is layer.values
    assert other.grid is layer.grid
    assert other != layer
    other.values[0, 0] = 20.0
    assert layer.values[0, 0] == 20.0
