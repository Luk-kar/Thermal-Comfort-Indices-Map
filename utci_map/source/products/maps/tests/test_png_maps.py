from dataclasses import FrozenInstanceError, replace
import json

import numpy as np
import pytest
from PIL import Image

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin
from utci_map.source.config import MAX_INDEX
from utci_map.source.products.maps.png_maps import (
    COASTLINE_PATH, MapOutput, RenderOptions, ValueRange, global_value_ranges, render_pngs,
)


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
        cold=MapOutput(
            png_path=tmp_path / "images" / "cold.png",
            json_path=tmp_path / "metadata" / "cold.json",
            colors=("#000000", "#ffffff"),
        ),
        heat=MapOutput(
            png_path=tmp_path / "images" / "heat.png",
            json_path=tmp_path / "metadata" / "heat.json",
            colors=("#000000", "#ff0000"),
        ),
        options=RenderOptions(coastline_path=None),
    )


def test_configuration_defaults_and_immutability(render_options):
    defaults = RenderOptions()
    assert defaults.png_scale == 1
    assert defaults.discrete_colors is False
    assert defaults.coastline_path == COASTLINE_PATH
    assert render_options["options"].coastline_path is None
    assert isinstance(render_options["cold"].colors, tuple)
    with pytest.raises(FrozenInstanceError):
        defaults.png_scale = 2
    with pytest.raises(FrozenInstanceError):
        render_options["cold"].png_path = render_options["heat"].png_path


def test_configuration_and_maps_require_keyword_arguments(map_input, render_options):
    with pytest.raises(TypeError):
        RenderOptions(2)
    with pytest.raises(TypeError):
        MapOutput(
            render_options["cold"].png_path,
            render_options["cold"].json_path,
            ("#000000", "#ffffff"),
        )

@pytest.mark.parametrize("explicit_none", [False, True])
def test_default_render_options_use_configured_coastline(
    map_input, render_options, tmp_path, monkeypatch, explicit_none,
):
    # Rebase the relative default without accessing the project's GISCO file.
    if COASTLINE_PATH.is_absolute():
        pytest.skip("This default-coastline test requires a relative configured path")
    monkeypatch.chdir(tmp_path)
    COASTLINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COASTLINE_PATH.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": {
            "type": "Polygon", "coordinates": [[
                [-24, 65], [-23, 65], [-23, 67], [-24, 67], [-24, 65],
            ]],
        }}],
    }), encoding="utf-8")
    kwargs = {"cold": render_options["cold"], "heat": render_options["heat"]}
    if explicit_none:
        kwargs["options"] = None
    render_pngs(map_input(), **kwargs)
    for kind in ("cold", "heat"):
        with Image.open(render_options[kind].png_path) as image:
            alpha = np.array(image.convert("RGBA"))[:, :, 3]
            assert (alpha[:, -1] == 0).all()
            assert (alpha == 255).any()


def test_coastline_masks_sea_and_excludes_it_from_range(map_input, render_options, tmp_path):
    coastline = tmp_path / "land.geojson"
    coastline.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": {
            "type": "Polygon", "coordinates": [[
                [-24, 65], [-23, 65], [-23, 67], [-24, 67], [-24, 65],
            ]],
        }}],
    }), encoding="utf-8")
    values = np.full((8, 8), 999., dtype=float)
    values[:, :4] = 10.
    values[0, 0] = np.nan
    options = {
        **render_options,
        "options": replace(render_options["options"], coastline_path=coastline),
    }
    render_pngs(map_input(cold=values, heat=values), **options)

    for kind in ("cold", "heat"):
        metadata = json.loads(options[kind].json_path.read_text())
        assert metadata["metric"]["raw_min"] == 10.
        assert metadata["metric"]["raw_max"] == 10.
        with Image.open(options[kind].png_path) as image:
            pixels = np.array(image)
            alpha = np.array(image.convert("RGBA"))[:, :, 3]
            assert (alpha == 0).any()
            assert (alpha == 255).any()
            assert (alpha[:, -1] == 0).all()
            assert alpha[0, 0] == 0
            np.testing.assert_array_equal(pixels[alpha == 255], 0)


def test_land_mask_preserves_holes():
    from utci_map.source.products.maps.png_maps import _land_mask, RasterGrid, WGS84_CRS

    geometry = {"type": "Polygon", "coordinates": [
        [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]],
        [[1, 1], [1, 3], [3, 3], [3, 1], [1, 1]],
    ]}
    grid = RasterGrid(
        crs=WGS84_CRS,
        grid_transform=from_origin(0, 4, 1, 1),
        bounds=(0, 0, 4, 4),
    )
    mask = _land_mask([geometry], (4, 4), grid)
    expected = np.ones((4, 4), dtype=bool)
    expected[1:3, 1:3] = False
    np.testing.assert_array_equal(mask, expected)


def test_land_mask_reprojects_polygons():
    from rasterio.transform import from_bounds
    from rasterio.warp import transform_bounds
    from utci_map.source.products.maps.png_maps import (
        _land_mask, RasterGrid, WGS84_CRS, WEBMERCATOR_CRS,
    )

    geometry = {"type": "Polygon", "coordinates": [[
        [0, 0], [1, 0], [1, 2], [0, 2], [0, 0],
    ]]}
    bounds = transform_bounds(WGS84_CRS, WEBMERCATOR_CRS, 0, 0, 2, 2)
    grid = RasterGrid(
        crs=WEBMERCATOR_CRS,
        grid_transform=from_bounds(*bounds, 4, 4),
        bounds=bounds,
    )
    mask = _land_mask([geometry], (4, 4), grid)
    expected = np.zeros((4, 4), dtype=bool)
    expected[:, :2] = True
    np.testing.assert_array_equal(mask, expected)


def test_missing_coastline_fails(map_input, render_options, tmp_path):
    options = {
        **render_options,
        "options": replace(
            render_options["options"], coastline_path=tmp_path / "missing.geojson",
        ),
    }
    with pytest.raises(FileNotFoundError):
        render_pngs(map_input(), **options)


@pytest.mark.parametrize("features", [[], [{"geometry": None}], [
    {"geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}},
]])
def test_invalid_coastline_geometries_fail(tmp_path, features):
    from utci_map.source.products.maps.png_maps import _load_land_geometries

    path = tmp_path / "invalid.geojson"
    path.write_text(json.dumps({
        "type": "FeatureCollection", "features": features,
    }), encoding="utf-8")
    with pytest.raises(ValueError):
        _load_land_geometries(path)


def test_creates_pngs_and_matching_sidecars(map_input, render_options):

    path = map_input()

    assert render_pngs(path, **render_options) is None

    for kind, metric, low, high in [
        ("cold", "days_daily_min_below_9_total", 0., 63.),
        ("heat", "days_daily_max_above_26_total", 5., 5.),
    ]:

        png_path = render_options[kind].png_path
        metadata = json.loads(render_options[kind].json_path.read_text())
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
    render_pngs(path, **render_options)

    with Image.open(render_options["cold"].png_path) as image:
        original_size = image.size

    original_metadata = json.loads(render_options["cold"].json_path.read_text())
    render_pngs(path, **{
        **render_options,
        "options": replace(render_options["options"], png_scale=2),
    })

    with Image.open(render_options["cold"].png_path) as image:
        assert image.size == tuple(2 * value for value in original_size)

    assert json.loads(render_options["cold"].json_path.read_text()) == original_metadata


def test_missing_pixels_remain_transparent(map_input, render_options):

    values = np.full((8, 8), np.nan)
    values[2:6, 2:6] = 10
    render_pngs(map_input(cold=values, heat=values), **render_options)

    with Image.open(render_options["cold"].png_path) as image:
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
        render_options = {
            **render_options,
            "options": replace(render_options["options"], png_scale=0),
        }
        error = ValueError

    with pytest.raises(error):
        render_pngs(path, **render_options, **options)

def _copy_tif(path, tmp_path, name):
    """Keep a map_input raster; the fixture rewrites one path on every call."""

    target = tmp_path / name
    target.write_bytes(path.read_bytes())
    return target


def _outputs(tmp_path, name):

    return dict(
        cold=MapOutput(
            png_path=tmp_path / name / "cold.png",
            json_path=tmp_path / name / "cold.json",
            colors=("#000000", "#ffffff"),
        ),
        heat=MapOutput(
            png_path=tmp_path / name / "heat.png",
            json_path=tmp_path / name / "heat.json",
            colors=("#000000", "#ff0000"),
        ),
    )


def test_global_value_ranges_span_all_regions_by_category(map_input, tmp_path):

    first = np.full((8, 8), 20.)
    first[0, 0] = np.nan
    first[1, 1] = 300.
    second = np.full((8, 8), 50.)
    second[1, 1] = 70.
    first_heat = np.full((8, 8), 4.)
    second_heat = np.full((8, 8), 90.)

    paths = [
        _copy_tif(map_input(cold=first, heat=first_heat), tmp_path, "first.tif"),
        _copy_tif(map_input(cold=second, heat=second_heat), tmp_path, "second.tif"),
    ]

    cold, heat = global_value_ranges(paths, RenderOptions(coastline_path=None))

    assert cold == ValueRange(20., 300.)
    assert heat == ValueRange(4., 90.)


def test_global_value_ranges_exclude_sea_pixels(map_input, tmp_path):

    coastline = tmp_path / "land.geojson"
    coastline.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": {
            "type": "Polygon", "coordinates": [[
                [-24, 65], [-23, 65], [-23, 67], [-24, 67], [-24, 65],
            ]],
        }}],
    }), encoding="utf-8")
    values = np.full((8, 8), 999., dtype=float)
    values[:, :4] = 10.

    cold, heat = global_value_ranges(
        [map_input(cold=values, heat=values)], RenderOptions(coastline_path=coastline),
    )

    assert cold == ValueRange(10., 10.)
    assert heat == ValueRange(10., 10.)


def test_global_value_ranges_skip_a_region_without_valid_pixels(map_input, tmp_path):

    paths = [
        _copy_tif(map_input(cold=np.full((8, 8), np.nan)), tmp_path, "empty.tif"),
        _copy_tif(map_input(cold=np.full((8, 8), 7.)), tmp_path, "valid.tif"),
    ]

    cold, _ = global_value_ranges(paths, RenderOptions(coastline_path=None))

    assert cold == ValueRange(7., 7.)


@pytest.mark.parametrize("case", ["no_paths", "all_missing"])
def test_global_value_ranges_reject_input_without_valid_pixels(map_input, case):

    paths = [] if case == "no_paths" else [map_input(cold=np.full((8, 8), np.nan))]

    with pytest.raises(ValueError, match="No valid pixels"):
        global_value_ranges(paths, RenderOptions(coastline_path=None))


def test_shared_ranges_give_regions_the_same_scale(map_input, tmp_path):
    """
    Check that one day count has one colour across regions.

    Both rasters hold a pixel with 50 days. Only the second reaches the top of
    the scale, so the first must not stretch its own maximum to the darkest
    colour, while the sidecars keep each region's real range as local_min
    and local_max.
    """

    low = np.full((8, 8), 50.)
    low[:, :4] = 25.
    high = np.full((8, 8), 50.)
    high[:, :4] = 100.
    cold_range, heat_range = ValueRange(0., 100.), ValueRange(0., 200.)
    options = RenderOptions(coastline_path=None)

    for name, values in (("low", low), ("high", high)):
        render_pngs(
            map_input(cold=values, heat=values), **_outputs(tmp_path, name),
            options=options, cold_range=cold_range, heat_range=heat_range,
        )

    metadata = {
        name: json.loads((tmp_path / name / "cold.json").read_text())
        for name in ("low", "high")
    }
    for name in ("low", "high"):
        assert metadata[name]["metric"]["min"] == 0.
        assert metadata[name]["metric"]["max"] == 100.
        assert metadata[name]["metric"]["raw_min"] == 0.
        assert metadata[name]["metric"]["raw_max"] == 100.
    assert metadata["low"]["color_map"] == metadata["high"]["color_map"]
    assert metadata["low"]["metric"]["local_min"] == 25.
    assert metadata["low"]["metric"]["local_max"] == 50.
    assert metadata["high"]["metric"]["local_min"] == 50.
    assert metadata["high"]["metric"]["local_max"] == 100.

    heat_metadata = json.loads((tmp_path / "low" / "heat.json").read_text())
    assert heat_metadata["metric"]["max"] == 200.

    with Image.open(tmp_path / "low" / "cold.png") as image:
        low_pixels = np.array(image)
    with Image.open(tmp_path / "high" / "cold.png") as image:
        high_pixels = np.array(image)

    fifty_days = round(0.5 * MAX_INDEX)
    assert low_pixels.max() == fifty_days
    assert fifty_days in high_pixels
    assert high_pixels.max() == MAX_INDEX


def test_constant_region_uses_its_position_on_the_shared_scale(map_input, tmp_path):

    outputs = _outputs(tmp_path, "constant")
    render_pngs(
        map_input(cold=np.full((8, 8), 75.)), **outputs,
        options=RenderOptions(coastline_path=None),
        cold_range=ValueRange(0., 100.), heat_range=ValueRange(0., 100.),
    )

    with Image.open(outputs["cold"].png_path) as image:
        pixels = np.array(image)
    np.testing.assert_array_equal(pixels[pixels != 255], round(0.75 * MAX_INDEX))


def test_degenerate_shared_range_still_renders(map_input, tmp_path):

    outputs = _outputs(tmp_path, "degenerate")
    render_pngs(
        map_input(cold=np.full((8, 8), 5.)), **outputs,
        options=RenderOptions(coastline_path=None),
        cold_range=ValueRange(5., 5.), heat_range=ValueRange(5., 5.),
    )

    metadata = json.loads(outputs["cold"].json_path.read_text())
    assert metadata["metric"]["min"] == 5.
    assert metadata["metric"]["max"] == 6.


@pytest.mark.parametrize("epsg", [4326, 3857])
def test_land_mask_keeps_intersecting_pixels_without_land_at_centres(epsg):
    """
    Keep narrow land features on geographic and projected grids.

    The polygon intersects both pixels in the first column, but contains
    neither pixel centre. Pixels in the second column remain sea.
    """
    from rasterio.crs import CRS
    from rasterio.transform import from_bounds
    from rasterio.warp import transform_bounds

    from utci_map.source.products.maps.png_maps import (
        RasterGrid,
        WGS84_CRS,
        _land_mask,
    )

    geometry = {
        "type": "Polygon",
        "coordinates": [[
            [0.05, 0.1],
            [0.15, 0.1],
            [0.15, 1.9],
            [0.05, 1.9],
            [0.05, 0.1],
        ]],
    }

    crs = CRS.from_epsg(epsg)
    bounds = (0.0, 0.0, 2.0, 2.0)

    if crs != WGS84_CRS:
        bounds = transform_bounds(WGS84_CRS, crs, *bounds)

    grid = RasterGrid(
        crs=crs,
        grid_transform=from_bounds(*bounds, width=2, height=2),
        bounds=bounds,
    )

    mask = _land_mask([geometry], (2, 2), grid)

    np.testing.assert_array_equal(
        mask,
        np.array([
            [True, False],
            [True, False],
        ]),
    )