"""Data contracts and coordinate reference systems shared by the map-rendering modules."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from rasterio.crs import CRS
from rasterio.transform import Affine

from utci_map.source.config import COASTLINE_PATH

WEBMERCATOR_CRS: CRS = CRS.from_epsg(3857)
WGS84_CRS: CRS = CRS.from_epsg(4326)

Bounds = tuple[float, float, float, float]  # (west, south, east, north)
Geometry = dict[str, Any]  # GeoJSON geometry, e.g. {"type": "Polygon", "coordinates": [...]}


@dataclass(frozen=True)
class RasterGrid:
    """
    Describe how a raster grid relates to its coordinate reference system.

    Attributes:
        crs: Coordinate reference system used by the transform and bounds.
        grid_transform: Affine transform mapping pixel coordinates (column, row)
            to spatial coordinates (x, y) in this CRS.
        bounds: Box enclosing the whole raster as (west, south, east, north)
            in this CRS, not necessarily in longitude and latitude.
    """

    crs: CRS
    grid_transform: Affine
    bounds: Bounds


@dataclass(frozen=True, eq=False)
class MapLayer:
    """
    Group a raster's values, spatial grid and metric metadata.

    Attributes:
        values: Array with shape (height, width) holding the metric for each pixel;
            NaN marks missing pixels, including sea pixels when coastline masking is on.
        grid: Grid describing the same extent and pixel layout as values.
        metric_band_name: Source GeoTIFF band, e.g. "days_daily_min_below_9_total";
            written to the sidecar's metric.column.
        metric_units: Units of the values, e.g. "days"; written to the sidecar's metric.units.

    Fields can't be reassigned, but the values array is neither copied nor made
    read-only, so in-place changes are visible to every object sharing it.
    """

    values: np.ndarray
    grid: RasterGrid
    metric_band_name: str
    metric_units: str


@dataclass(frozen=True, kw_only=True)
class MapOutput:
    """Output paths and palette for one map."""

    png_path: Path
    json_path: Path
    colors: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class RenderOptions:
    """Rendering settings shared by the cold and heat maps; coastline_path=None disables masking."""

    png_scale: int = 1
    discrete_colors: bool = False
    coastline_path: Path | None = COASTLINE_PATH


@dataclass(frozen=True)
class ValueRange:
    """Metric values mapped to the lightest and darkest palette colors."""

    vmin: float
    vmax: float


@dataclass(frozen=True, kw_only=True)
class MetricScale:
    """
    Describe a rendered metric and how its values map onto the palette.

    vmin and vmax map to the first and last palette index; vmax is widened by one
    when the range is empty. raw_min and raw_max are the requested range before
    widening, which spans every region when a shared range is used. local_min and
    local_max are the range of this map's own pixels.
    """

    column: str
    units: str
    vmin: float
    vmax: float
    raw_min: float
    raw_max: float
    local_min: float
    local_max: float


@dataclass(frozen=True, kw_only=True)
class ImagePlacement:
    """Where a PNG sits on the map: its WGS84 edges and the CRS of its pixels."""

    lonlat_bounds: Bounds
    crs: str
