"""Reproject geographic rasters onto Web Mercator pixels for MapLibre image sources."""

from collections.abc import Sequence

import numpy as np
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds

from utci_map.source.products.maps.land_mask import land_mask
from utci_map.source.products.maps.models import (
    WEBMERCATOR_CRS,
    WGS84_CRS,
    Bounds,
    Geometry,
    RasterGrid,
)

# Points sampled along each edge, so the curved Mercator edges get exact WGS84 bounds.
EDGE_DENSIFY_POINTS = 21


def reproject_to_webmercator(
    values: np.ndarray,
    source_grid: RasterGrid,
    land_geometries: Sequence[Geometry] | None = None,
) -> tuple[np.ndarray, Bounds]:
    """
    Resample a (height, width) raster onto EPSG:3857 pixels using nearest neighbor.

    Return a new float32 array, with NaN for missing pixels and for sea pixels when
    land_geometries are given, and its (west, south, east, north) edges in WGS84.
    The input array is left unchanged.
    """
    height, width = values.shape
    dst_transform, dst_width, dst_height = calculate_default_transform(
        source_grid.crs, WEBMERCATOR_CRS, width, height, *source_grid.bounds
    )

    destination = np.full((dst_height, dst_width), np.nan, dtype=np.float32)
    reproject(
        source=values.astype(np.float32),
        destination=destination,
        src_transform=source_grid.grid_transform,
        src_crs=source_grid.crs,
        src_nodata=np.nan,
        dst_transform=dst_transform,
        dst_crs=WEBMERCATOR_CRS,
        dst_nodata=np.nan,
        resampling=Resampling.nearest,
        init_dest_nodata=True,
    )
    mercator_bounds = array_bounds(dst_height, dst_width, dst_transform)

    if land_geometries is not None:
        grid = RasterGrid(crs=WEBMERCATOR_CRS, grid_transform=dst_transform, bounds=mercator_bounds)
        destination[~land_mask(land_geometries, destination.shape, grid)] = np.nan

    lonlat_bounds = transform_bounds(
        WEBMERCATOR_CRS, WGS84_CRS, *mercator_bounds, densify_pts=EDGE_DENSIFY_POINTS
    )
    return destination, lonlat_bounds
