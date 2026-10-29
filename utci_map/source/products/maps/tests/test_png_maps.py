import json

import numpy as np
import pytest
from PIL import Image

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin
from utci_map.source.products.maps.png_maps import render_pngs


@pytest.fixture
def map_input(tmp_path):
    """Create an input GeoTIFF independently of the production writer."""

    path = tmp_path / "input.tif"
    names = [
        "days_daily_max_26_32", "days_daily_max_32_38",
        "days_daily_max_38_46", "days_daily_max_46_inf",
        "days_daily_min_-inf_-40", "days_daily_min_-40_-27",
        "days_daily_min_-27_-13", "days_daily_min_-13_0", "days_daily_min_0_9",
        "days_daily_min_below_9_total", "days_daily_max_above_26_total",
    ]
    def create(cold=None, heat=None, omit=(), crs="EPSG:4326"):
        selected = [name for name in names if name not in omit]
        cold = np.arange(64, dtype=float).reshape(8, 8) if cold is None else cold
        heat = np.full((8, 8), 5.) if heat is None else heat
        with rasterio.open(path, "w", driver="GTiff", height=8, width=8,
                           count=len(selected), dtype="float32", crs=crs,
                           transform=from_origin(-24, 67, 0.25, 0.25), nodata=np.nan) as dst:
            for index, name in enumerate(selected, 1):
                values = cold if name == names[-2] else heat if name == names[-1] else np.zeros((8, 8))
                dst.write(values.astype("float32"), index)
                dst.set_band_description(index, name)
        return path
    return create


@pytest.fixture
def render_options(tmp_path):

    return dict(
        cold_png_path=tmp_path / "images" / "cold.png",
        cold_json_path=tmp_path / "metadata" / "cold.json",
        heat_png_path=tmp_path / "images" / "heat.png",
        heat_json_path=tmp_path / "metadata" / "heat.json",
        cold_colors=["#000000", "#ffffff"],
        heat_colors=["#000000", "#ff0000"],
    )


def test_creates_pngs_and_matching_sidecars(map_input, render_options):

    path = map_input()

    assert render_pngs(path, **render_options) is None

    for kind, metric, low, high in [
        ("cold", "days_daily_min_below_9_total", 0., 63.),
        ("heat", "days_daily_max_above_26_total", 5., 5.),
    ]:

        png_path = render_options[f"{kind}_png_path"]
        metadata = json.loads(render_options[f"{kind}_json_path"].read_text())
        assert metadata["image"] == png_path.name
        assert metadata["crs"] == "EPSG:3857"
        assert metadata["metric"]["column"] == metric
        assert metadata["metric"]["units"] == "days"
        assert metadata["metric"]["raw_min"] == low
        assert metadata["metric"]["raw_max"] == high

        west, north = metadata["coordinates"][0]
        east, south = metadata["coordinates"][2]
        assert west < east and south < north
        assert west == pytest.approx(-24, abs=0.3)
        assert north == pytest.approx(67, abs=0.3)

        with Image.open(png_path) as image:
            assert image.mode == "P"
            assert image.width > 0 and image.height > 0
            palette = image.getpalette()
            for entry in metadata["color_map"]:
                index = entry["index"]
                assert palette[3 * index:3 * index + 3] == entry["rgb"]
            if kind == "heat":
                pixels = np.array(image)
                np.testing.assert_array_equal(pixels[pixels != 255], 0)


def test_scale_changes_image_size_not_geographic_placement(map_input, render_options):
    """
    Check that enlarging a PNG preserves its geographic placement.

    Render the same input with scale factors of 1 and 2. Expect the second
    image to have twice the width and height, while its JSON sidecar remains
    unchanged, including the geographic corner coordinates and metric metadata.
    """

    path = map_input()
    render_pngs(path, **render_options, png_scale=1)

    with Image.open(render_options["cold_png_path"]) as image:
        original_size = image.size

    original_metadata = json.loads(render_options["cold_json_path"].read_text())
    render_pngs(path, **render_options, png_scale=2)

    with Image.open(render_options["cold_png_path"]) as image:
        assert image.size == tuple(2 * value for value in original_size)

    assert json.loads(render_options["cold_json_path"].read_text()) == original_metadata


def test_missing_pixels_remain_transparent(map_input, render_options):

    values = np.full((8, 8), np.nan)
    values[2:6, 2:6] = 10
    render_pngs(map_input(cold=values, heat=values), **render_options)

    with Image.open(render_options["cold_png_path"]) as image:
        alpha = np.array(image.convert("RGBA"))[:, :, 3]
        assert (alpha == 0).any()
        assert (alpha == 255).any()


@pytest.mark.parametrize("case", ["missing_band", "missing_crs", "all_missing", "invalid_scale"])
def test_invalid_input_raises(map_input, render_options, case):

    options = {}
    if case == "missing_band":
        path = map_input(omit=("days_daily_max_above_26_total",))
        error = KeyError

    elif case == "missing_crs":
        path = map_input(crs=None)
        error = ValueError

    elif case == "all_missing":
        path = map_input(cold=np.full((8, 8), np.nan))
        error = ValueError

    else:
        path = map_input()
        options["png_scale"] = 0
        error = ValueError

    with pytest.raises(error):
        render_pngs(path, **render_options, **options)
