"""Load GISCO land polygons and turn them into per-pixel land masks."""

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom

from utci_map.source.products.maps.models import WGS84_CRS, Geometry, RasterGrid

LAND_GEOMETRY_TYPES = frozenset({"Polygon", "MultiPolygon"})


def load_land_geometries(path: Path) -> list[Geometry]:
    """
    Read land polygons in EPSG:4326 from a GeoJSON FeatureCollection.

    Raise ValueError unless every feature has a Polygon or MultiPolygon geometry.
    """
    with path.open(encoding="utf-8") as source:
        collection = json.load(source)

    if collection.get("type") != "FeatureCollection":
        raise ValueError(f"{path}: expected a GeoJSON FeatureCollection")

    geometries = [feature.get("geometry") for feature in collection["features"]]
    if not geometries or any(
        geometry is None or geometry.get("type") not in LAND_GEOMETRY_TYPES
        for geometry in geometries
    ):
        raise ValueError(f"{path}: expected non-empty land Polygon/MultiPolygon features")
    return geometries


def land_mask(
    land_geometries: Sequence[Geometry], raster_shape: tuple[int, int], grid: RasterGrid
) -> np.ndarray:
    """
    Return a boolean (height, width) mask that is True for pixels touching land.

    A pixel counts as land if any polygon touches it, so narrow coastal features
    are kept even when they miss every pixel center. Polygon holes stay False.
    Geometries are reprojected from EPSG:4326 when the grid uses another CRS.
    """
    if grid.crs != WGS84_CRS:
        land_geometries = [
            transform_geom(WGS84_CRS, grid.crs, geometry) for geometry in land_geometries
        ]
    return geometry_mask(
        land_geometries,
        out_shape=raster_shape,
        transform=grid.grid_transform,
        invert=True,
        all_touched=True,
    )
