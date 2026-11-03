"""Synthetic GeoTIFFs, coastlines and map layers shared by the map-rendering tests."""

import json

import numpy as np
import pytest

pytest.importorskip("rasterio")
import rasterio
from rasterio.transform import array_bounds, from_origin

from utci_map.source.products.maps.models import WGS84_CRS, MapLayer, MapOutput, RasterGrid

SUMMARY_BAND_NAMES = [
    "days_daily_max_26_32",
    "days_daily_max_32_38",
    "days_daily_max_38_46",
    "days_daily_max_46_inf",
    "days_daily_min_-inf_-40",
    "days_daily_min_-40_-27",
    "days_daily_min_-27_-13",
    "days_daily_min_-13_0",
    "days_daily_min_0_9",
    "days_daily_min_below_9_total",
    "days_daily_max_above_26_total",
]


@pytest.fixture
def map_input(tmp_path):
    """
    Provide a factory writing an 8 x 8 summary GeoTIFF independently of the production writer.

    The grid starts at 24° W, 67° N with 0.25° pixels. The cold total defaults to
    0..63 and the heat total to 5 everywhere; other bands are zero. Every call
    rewrites the same path.
    """
    path = tmp_path / "input.tif"
    cold_band, heat_band = SUMMARY_BAND_NAMES[-2:]

    def create(cold=None, heat=None, omit=(), crs="EPSG:4326"):
        selected = [name for name in SUMMARY_BAND_NAMES if name not in omit]
        totals = {
            cold_band: np.arange(64, dtype=float).reshape(8, 8) if cold is None else cold,
            heat_band: np.full((8, 8), 5.0) if heat is None else heat,
        }
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=8,
            width=8,
            count=len(selected),
            dtype="float32",
            crs=crs,
            transform=from_origin(-24, 67, 0.25, 0.25),
            nodata=np.nan,
        ) as dst:
            for index, name in enumerate(selected, 1):
                dst.write(totals.get(name, np.zeros((8, 8))).astype("float32"), index)
                dst.set_band_description(index, name)
        return path

    return create


@pytest.fixture
def west_half_coastline(tmp_path):
    """Write a GeoJSON land polygon covering the western half of the map_input grid."""
    path = tmp_path / "land.geojson"
    polygon = [[[-24, 65], [-23, 65], [-23, 67], [-24, 67], [-24, 65]]]
    feature = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "Polygon", "coordinates": polygon},
    }
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8"
    )
    return path


@pytest.fixture
def layer():
    """Provide an 8 x 8 WGS84 layer of 12 days with 0.5° pixels, from 0° E, 4° N."""
    transform = from_origin(0, 4, 0.5, 0.5)
    return MapLayer(
        values=np.full((8, 8), 12.0, dtype=float),
        grid=RasterGrid(
            crs=WGS84_CRS, grid_transform=transform, bounds=array_bounds(8, 8, transform)
        ),
        metric_band_name="test_stress_days",
        metric_units="days",
    )


@pytest.fixture
def output(tmp_path):
    """Provide a black-to-white map output in tmp_path."""
    return MapOutput(
        png_path=tmp_path / "map.png",
        json_path=tmp_path / "map.json",
        colors=("#000000", "#ffffff"),
    )
