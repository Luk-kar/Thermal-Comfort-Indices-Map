"""
Check that summary GeoTIFFs become PNG maps with matching sidecars, and that shared
value ranges span every region. Cover coastline masking, transparency, scaling,
shared color scales and rejection of invalid input.
"""

import json
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("rasterio")

from utci_map.source.config import COASTLINE_PATH, MAX_INDEX, NODATA_INDEX
from utci_map.source.products.maps.models import MapOutput, RenderOptions, ValueRange
from utci_map.source.products.maps.png_maps import global_value_ranges, render_pngs

NO_COASTLINE = RenderOptions(coastline_path=None)


def _outputs(directory):
    """Black-to-white cold and black-to-red heat outputs, with PNGs and JSON in separate folders."""
    return {
        kind: MapOutput(
            png_path=directory / "images" / f"{kind}.png",
            json_path=directory / "metadata" / f"{kind}.json",
            colors=("#000000", top_color),
        )
        for kind, top_color in (("cold", "#ffffff"), ("heat", "#ff0000"))
    }


def _alpha(png_path):
    with Image.open(png_path) as image:
        return np.array(image.convert("RGBA"))[:, :, 3]


def _pixels(png_path):
    with Image.open(png_path) as image:
        return np.array(image)


def _metadata(output):
    return json.loads(output.json_path.read_text())


def _copy_tif(path, tmp_path, name):
    """Keep a map_input raster; the fixture rewrites one path on every call."""
    target = tmp_path / name
    target.write_bytes(path.read_bytes())
    return target


class TestRenderPngs:
    @pytest.mark.parametrize(
        "kind, expected",
        [
            ("cold", ("days_daily_min_below_9_total", 0.0, 63.0)),
            ("heat", ("days_daily_max_above_26_total", 5.0, 5.0)),
        ],
    )
    def test_creates_png_and_matching_sidecar(self, map_input, tmp_path, kind, expected):
        """Expected is (band name, raw_min, raw_max) for the kind's sidecar."""
        metric, low, high = expected
        outputs = _outputs(tmp_path)

        assert render_pngs(map_input(), **outputs, options=NO_COASTLINE) is None

        metadata = _metadata(outputs[kind])
        assert metadata["image"] == outputs[kind].png_path.name
        assert metadata["crs"] == "EPSG:3857"
        assert metadata["metric"]["column"] == metric
        assert metadata["metric"]["units"] == "days"
        assert (metadata["metric"]["raw_min"], metadata["metric"]["raw_max"]) == (low, high)

        west, north = metadata["coordinates"][0]
        east, south = metadata["coordinates"][2]
        assert west < east and south < north
        assert west == pytest.approx(-24, abs=0.3)
        assert north == pytest.approx(67, abs=0.3)

        with Image.open(outputs[kind].png_path) as image:
            assert image.mode == "P"
            palette = image.getpalette()
        for entry in metadata["color_map"]:
            assert palette[3 * entry["index"] : 3 * entry["index"] + 3] == entry["rgb"]

    def test_constant_map_uses_the_lightest_color(self, map_input, tmp_path):
        outputs = _outputs(tmp_path)
        render_pngs(map_input(), **outputs, options=NO_COASTLINE)

        pixels = _pixels(outputs["heat"].png_path)
        np.testing.assert_array_equal(pixels[pixels != NODATA_INDEX], 0)

    @pytest.mark.parametrize("explicit_none", [False, True])
    def test_default_options_mask_sea_with_configured_coastline(
        self, map_input, west_half_coastline, tmp_path, monkeypatch, explicit_none
    ):
        """Rebase the relative default coastline into tmp_path, leaving the GISCO file alone."""
        if COASTLINE_PATH.is_absolute():
            pytest.skip("This default-coastline test requires a relative configured path")
        monkeypatch.chdir(tmp_path)
        COASTLINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        COASTLINE_PATH.write_text(west_half_coastline.read_text(), encoding="utf-8")
        outputs = _outputs(tmp_path)

        render_pngs(map_input(), **outputs, **({"options": None} if explicit_none else {}))

        for output in outputs.values():
            alpha = _alpha(output.png_path)
            assert (alpha[:, -1] == 0).all()
            assert (alpha == 255).any()

    def test_coastline_masks_sea_and_excludes_it_from_range(
        self, map_input, west_half_coastline, tmp_path
    ):
        """Sea pixels hold 999 and land pixels 10, so only 10 may set the range and colors."""
        values = np.full((8, 8), 999.0)
        values[:, :4] = 10.0
        values[0, 0] = np.nan
        outputs = _outputs(tmp_path)

        render_pngs(
            map_input(cold=values, heat=values),
            **outputs,
            options=RenderOptions(coastline_path=west_half_coastline),
        )

        for output in outputs.values():
            metadata = _metadata(output)
            assert (metadata["metric"]["raw_min"], metadata["metric"]["raw_max"]) == (10.0, 10.0)
            alpha = _alpha(output.png_path)
            assert (alpha == 255).any()
            assert (alpha[:, -1] == 0).all()
            assert alpha[0, 0] == 0
            np.testing.assert_array_equal(_pixels(output.png_path)[alpha == 255], 0)

    def test_missing_coastline_fails(self, map_input, tmp_path):
        options = RenderOptions(coastline_path=tmp_path / "missing.geojson")

        with pytest.raises(FileNotFoundError):
            render_pngs(map_input(), **_outputs(tmp_path), options=options)

    def test_scale_changes_image_size_not_geographic_placement(self, map_input, tmp_path):
        """Render at scale 1 and 2; the image doubles while the sidecar stays identical."""
        path, cold = map_input(), _outputs(tmp_path)["cold"]
        render_pngs(path, **_outputs(tmp_path), options=NO_COASTLINE)
        with Image.open(cold.png_path) as image:
            original_size = image.size
        original_metadata = _metadata(cold)

        render_pngs(path, **_outputs(tmp_path), options=replace(NO_COASTLINE, png_scale=2))

        with Image.open(cold.png_path) as image:
            assert image.size == tuple(2 * value for value in original_size)
        assert _metadata(cold) == original_metadata

    def test_missing_pixels_remain_transparent(self, map_input, tmp_path):
        values = np.full((8, 8), np.nan)
        values[2:6, 2:6] = 10
        outputs = _outputs(tmp_path)

        render_pngs(map_input(cold=values, heat=values), **outputs, options=NO_COASTLINE)

        alpha = _alpha(outputs["cold"].png_path)
        assert (alpha == 0).any()
        assert (alpha == 255).any()

    @pytest.mark.parametrize(
        "case, error",
        [
            ("missing_band", KeyError),
            ("missing_crs", ValueError),
            ("all_missing", ValueError),
            ("invalid_scale", ValueError),
        ],
    )
    def test_invalid_input_raises(self, map_input, tmp_path, case, error):
        inputs = {
            "missing_band": {"omit": ("days_daily_max_above_26_total",)},
            "missing_crs": {"crs": None},
            "all_missing": {"cold": np.full((8, 8), np.nan)},
            "invalid_scale": {},
        }
        options = replace(NO_COASTLINE, png_scale=0) if case == "invalid_scale" else NO_COASTLINE

        with pytest.raises(error):
            render_pngs(map_input(**inputs[case]), **_outputs(tmp_path), options=options)

    def test_shared_ranges_give_regions_the_same_scale(self, map_input, tmp_path):
        """
        Check that one day count has one color across regions.

        Both rasters hold a pixel with 50 days. Only the second reaches the top of
        the scale, so the first must not stretch its own maximum to the darkest
        color, while the sidecars keep each region's real range as local_min
        and local_max.
        """
        low = np.full((8, 8), 50.0)
        low[:, :4] = 25.0
        high = np.full((8, 8), 50.0)
        high[:, :4] = 100.0
        outputs = {"low": _outputs(tmp_path / "low"), "high": _outputs(tmp_path / "high")}

        for name, values in (("low", low), ("high", high)):
            render_pngs(
                map_input(cold=values, heat=values),
                **outputs[name],
                options=NO_COASTLINE,
                value_ranges=(ValueRange(0.0, 100.0), ValueRange(0.0, 200.0)),
            )

        cold = {name: _metadata(outputs[name]["cold"]) for name in outputs}
        for name in outputs:
            metric = cold[name]["metric"]
            assert (metric["min"], metric["max"]) == (0.0, 100.0)
            assert (metric["raw_min"], metric["raw_max"]) == (0.0, 100.0)
        assert cold["low"]["color_map"] == cold["high"]["color_map"]
        assert (cold["low"]["metric"]["local_min"], cold["low"]["metric"]["local_max"]) == (25, 50)
        assert (cold["high"]["metric"]["local_min"], cold["high"]["metric"]["local_max"]) == (
            50,
            100,
        )
        assert _metadata(outputs["low"]["heat"])["metric"]["max"] == 200.0

        fifty_days = round(0.5 * MAX_INDEX)
        low_pixels = _pixels(outputs["low"]["cold"].png_path)
        high_pixels = _pixels(outputs["high"]["cold"].png_path)
        assert low_pixels.max() == fifty_days
        assert fifty_days in high_pixels
        assert high_pixels.max() == MAX_INDEX

    def test_constant_region_uses_its_position_on_the_shared_scale(self, map_input, tmp_path):
        outputs = _outputs(tmp_path)

        render_pngs(
            map_input(cold=np.full((8, 8), 75.0)),
            **outputs,
            options=NO_COASTLINE,
            value_ranges=(ValueRange(0.0, 100.0), ValueRange(0.0, 100.0)),
        )

        pixels = _pixels(outputs["cold"].png_path)
        np.testing.assert_array_equal(pixels[pixels != NODATA_INDEX], round(0.75 * MAX_INDEX))

    def test_degenerate_shared_range_still_renders(self, map_input, tmp_path):
        """An empty shared range 5..5 is widened to 5..6 so the map can still be colored."""
        outputs = _outputs(tmp_path)

        render_pngs(
            map_input(cold=np.full((8, 8), 5.0)),
            **outputs,
            options=NO_COASTLINE,
            value_ranges=(ValueRange(5.0, 5.0), ValueRange(5.0, 5.0)),
        )

        metric = _metadata(outputs["cold"])["metric"]
        assert (metric["min"], metric["max"]) == (5.0, 6.0)


class TestGlobalValueRanges:
    def test_ranges_span_all_regions_by_category(self, map_input, tmp_path):
        first = np.full((8, 8), 20.0)
        first[0, 0] = np.nan
        first[1, 1] = 300.0
        second = np.full((8, 8), 50.0)
        second[1, 1] = 70.0
        paths = [
            _copy_tif(map_input(cold=first, heat=np.full((8, 8), 4.0)), tmp_path, "first.tif"),
            _copy_tif(map_input(cold=second, heat=np.full((8, 8), 90.0)), tmp_path, "second.tif"),
        ]

        cold, heat = global_value_ranges(paths, NO_COASTLINE)

        assert cold == ValueRange(20.0, 300.0)
        assert heat == ValueRange(4.0, 90.0)

    def test_ranges_exclude_sea_pixels(self, map_input, west_half_coastline):
        values = np.full((8, 8), 999.0)
        values[:, :4] = 10.0

        cold, heat = global_value_ranges(
            [map_input(cold=values, heat=values)], RenderOptions(coastline_path=west_half_coastline)
        )

        assert cold == ValueRange(10.0, 10.0)
        assert heat == ValueRange(10.0, 10.0)

    def test_ranges_skip_a_region_without_valid_pixels(self, map_input, tmp_path):
        paths = [
            _copy_tif(map_input(cold=np.full((8, 8), np.nan)), tmp_path, "empty.tif"),
            _copy_tif(map_input(cold=np.full((8, 8), 7.0)), tmp_path, "valid.tif"),
        ]

        cold, _ = global_value_ranges(paths, NO_COASTLINE)

        assert cold == ValueRange(7.0, 7.0)

    @pytest.mark.parametrize("case", ["no_paths", "all_missing"])
    def test_input_without_valid_pixels_is_rejected(self, map_input, case):
        paths = [] if case == "no_paths" else [map_input(cold=np.full((8, 8), np.nan))]

        with pytest.raises(ValueError, match="No valid pixels"):
            global_value_ranges(paths, NO_COASTLINE)
