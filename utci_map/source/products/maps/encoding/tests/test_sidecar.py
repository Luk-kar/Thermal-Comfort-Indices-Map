"""Check that the JSON sidecar places the PNG and explains its colors in metric units."""

import json
from dataclasses import replace

import numpy as np
import pytest

from utci_map.source.products.maps.encoding.sidecar import write_sidecar
from utci_map.source.products.maps.models import ImagePlacement, MetricScale


@pytest.fixture
def sidecar_input(tmp_path):
    return dict(
        json_path=tmp_path / "metadata" / "cold.json",
        png_path=tmp_path / "images" / "cold.png",
        placement=ImagePlacement(
            lonlat_bounds=(-24.123456789, 63.25, -13.5, 67.75), crs="EPSG:3857"
        ),
        metric=MetricScale(
            column="cold_days",
            units="days",
            vmin=0.0,
            vmax=254.0,
            raw_min=1.123456789,
            raw_max=253.987654321,
            local_min=2.123456789,
            local_max=252.987654321,
        ),
        rgb=np.tile([12, 34, 56], (255, 1)),
    )


def test_writes_image_placement_metric_and_color_metadata(sidecar_input):
    """
    Check that the sidecar describes the PNG placement and metric colours.

    Verify the image filename and geographic corners in MapLibre image-source
    order: top-left, top-right, bottom-right, bottom-left, with each corner
    expressed as longitude and latitude. The application can use these values
    to position the PNG on the map.

    MapLibre image-source specification:
    https://www.maplibre.org/maplibre-style-spec/sources/#image

    Check the metric name, units, value ranges, missing-pixel metadata and
    color-map entries the application uses to explain the displayed values.
    These are application-specific metadata, not native MapLibre source options.

    This test validates the JSON contents, not rendering in MapLibre.
    """

    assert write_sidecar(**sidecar_input) is None

    result = json.loads(sidecar_input["json_path"].read_text())
    assert result["image"] == "cold.png"
    assert result["crs"] == "EPSG:3857"
    assert result["coordinates"] == [
        [-24.123457, 67.75],
        [-13.5, 67.75],
        [-13.5, 63.25],
        [-24.123457, 63.25],
    ]
    assert result["metric"] == dict(
        column="cold_days",
        min=0.0,
        max=254.0,
        units="days",
        raw_min=1.123457,
        raw_max=253.987654,
        local_min=2.123457,
        local_max=252.987654,
    )
    assert result["nodata"] == {"palette_index": 255, "alpha": 0}

    expected_indices = list(range(0, 254, 17)) + [254]
    assert result["color_map"] == [
        {"index": index, "rgb": [12, 34, 56], "value": float(index)} for index in expected_indices
    ]


def test_maps_palette_indices_to_metric_range(sidecar_input):
    """
    Check that palette indices map to values in the metric range.

    Verify that the sidecar associates palette indices with the corresponding
    metric values and colours, allowing the application to interpret the
    rendered image in the metric's units.
    """

    sidecar_input["metric"] = replace(sidecar_input["metric"], vmin=10.0, vmax=20.0)
    write_sidecar(**sidecar_input)
    entries = json.loads(sidecar_input["json_path"].read_text())["color_map"]

    assert entries[0]["value"] == 10.0
    assert entries[-1]["value"] == 20.0
    assert entries[1]["value"] == pytest.approx(10.6693)


def test_rejects_non_finite_json_values(sidecar_input):
    sidecar_input["metric"] = replace(sidecar_input["metric"], raw_min=float("nan"))
    with pytest.raises(ValueError):
        write_sidecar(**sidecar_input)
