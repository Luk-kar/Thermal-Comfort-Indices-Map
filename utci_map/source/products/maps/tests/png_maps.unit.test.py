"""
Pin the current behavior of png_maps._render_map as a guard during refactors.

These tests reach into private internals and are not a behavior contract; the
public contract lives in test_png_maps.py. Rewrite them freely when the internals
change on purpose.
"""

import json

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("rasterio")

from utci_map.source.products.maps.models import RenderOptions
from utci_map.source.products.maps.png_maps import _render_map


def test_render_map_uses_layer_metadata(layer, output):
    _render_map(layer, output, RenderOptions(coastline_path=None))

    metadata = json.loads(output.json_path.read_text())
    assert metadata["metric"]["column"] == layer.metric_band_name
    assert metadata["metric"]["units"] == layer.metric_units
    assert metadata["metric"]["raw_min"] == 12.0
    assert metadata["metric"]["raw_max"] == 12.0
    with Image.open(output.png_path) as image:
        assert image.mode == "P"
        assert np.any(np.array(image.convert("RGBA"))[:, :, 3] == 255)


@pytest.mark.parametrize(
    "case, message",
    [
        ("missing_values", "No valid pixels"),
        ("invalid_scale", "png_scale must be a positive integer"),
    ],
)
def test_render_map_preserves_validation(layer, output, case, message):
    options = RenderOptions(coastline_path=None)
    if case == "missing_values":
        layer.values[:] = np.nan
    else:
        options = RenderOptions(png_scale=0, coastline_path=None)

    with pytest.raises(ValueError, match=message):
        _render_map(layer, output, options)
