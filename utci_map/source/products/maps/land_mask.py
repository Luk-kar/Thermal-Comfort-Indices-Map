"""Load GISCO land polygons and turn them into per-pixel land masks."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom

from utci_map.source.products.maps.models import WGS84_CRS, Geometry, RasterGrid

# GeoJSON positions are (longitude, latitude), optionally followed by a height.
Position = Annotated[list[float], Field(min_length=2)]
LinearRing = Annotated[list[Position], Field(min_length=4)]


class _GeoJsonModel(BaseModel):
    """Reject wrongly typed values instead of converting them; ignore unused members."""

    model_config = ConfigDict(strict=True, frozen=True)


class _Polygon(_GeoJsonModel):
    type: Literal["Polygon"]
    coordinates: list[LinearRing]


class _MultiPolygon(_GeoJsonModel):
    type: Literal["MultiPolygon"]
    coordinates: list[list[LinearRing]]


class _LandFeature(_GeoJsonModel):
    geometry: Annotated[_Polygon | _MultiPolygon, Field(discriminator="type")]


class _LandCollection(_GeoJsonModel):
    type: Literal["FeatureCollection"]
    features: Annotated[list[_LandFeature], Field(min_length=1)]


def load_land_geometries(path: Path) -> list[Geometry]:
    """
    Read land polygons in EPSG:4326 from a GeoJSON FeatureCollection.

    Raise ValueError naming the file unless it holds at least one feature and every
    feature has a Polygon or MultiPolygon geometry with numeric coordinates.
    """
    with path.open(encoding="utf-8") as source:
        collection = json.load(source)

    try:
        land = _LandCollection.model_validate(collection)
    except ValidationError as error:
        raise ValueError(f"{path}: invalid land coastline GeoJSON\n{error}") from error

    return [feature.geometry.model_dump() for feature in land.features]


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
