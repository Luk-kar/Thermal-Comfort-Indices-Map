"""Reproject maps and write indexed PNGs with MapLibre JSON sidecars."""

from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds

from ...config import MAX_INDEX, NODATA_INDEX
from ..geotiff import band_indices
from .palette import palette_rgb, to_indices
from .sidecar import write_sidecar
from ...schema import COLD_TOTAL_BAND, HEAT_TOTAL_BAND, MIN_BAND_NAMES, MAX_BAND_NAMES

WEBMERCATOR_CRS: CRS = CRS.from_epsg(3857)


WGS84_CRS: CRS = CRS.from_epsg(4326)

def reproject_to_webmercator(values: np.ndarray, src_crs, src_transform, src_bounds):
    """Resample a geographic grid onto EPSG:3857 pixels (nearest-neighbour).

    Returns the reprojected array and its true (west, south, east, north) edges
    in WGS84 longitude/latitude.
    """

    height, width = values.shape
    dst_transform, dst_width, dst_height = calculate_default_transform(
        src_crs, WEBMERCATOR_CRS, width, height, *src_bounds
    )
    destination = np.full((dst_height, dst_width), np.nan, dtype=np.float32)
    reproject(
        source=values.astype(np.float32), destination=destination,
        src_transform=src_transform, src_crs=src_crs, src_nodata=np.nan,
        dst_transform=dst_transform, dst_crs=WEBMERCATOR_CRS, dst_nodata=np.nan,
        resampling=Resampling.nearest, init_dest_nodata=True,
    )
    mercator_bounds = array_bounds(dst_height, dst_width, dst_transform)
    lonlat_bounds = transform_bounds(WEBMERCATOR_CRS, WGS84_CRS, *mercator_bounds, densify_pts=21)
    return destination, lonlat_bounds


def write_map(
    values, lonlat_bounds, colors, png_path: Path, json_path: Path,
    column: str, units: str, vmin: float, vmax: float, raw_min: float, raw_max: float,
    png_scale: int = 1, discrete_colors: bool = False,
) -> None:
    """Write a palette-indexed PNG (index 255 = transparent nodata) and its MapLibre sidecar."""

    rgb = palette_rgb(colors, discrete_colors)
    image = Image.fromarray(to_indices(values, vmin, vmax))

    palette = np.zeros((NODATA_INDEX + 1, 3), dtype=np.uint8)
    palette[: MAX_INDEX + 1] = rgb
    image.putpalette(palette.reshape(-1).tolist())

    if png_scale != 1:
        image = image.resize(
            (image.width * png_scale, image.height * png_scale), Image.Resampling.NEAREST
        )

    png_path.parent.mkdir(parents=True, exist_ok=True)
    alpha = bytes([255] * NODATA_INDEX + [0])
    image.save(png_path, transparency=alpha)

    write_sidecar(
        json_path=json_path,
        png_path=png_path,
        lonlat_bounds=lonlat_bounds,
        crs=WEBMERCATOR_CRS.to_string(),
        rgb=rgb,
        column=column,
        units=units,
        vmin=vmin,
        vmax=vmax,
        raw_min=raw_min,
        raw_max=raw_max,
    )



def render_map(
    total, crs, transform, bounds, colors, png_path: Path, json_path: Path, column: str, units: str,
    png_scale: int = 1, discrete_colors: bool = False,
) -> None:

    if not np.isfinite(total).any():
        raise ValueError(f"No valid pixels to plot for {png_path.name}")
    if png_scale < 1:
        raise ValueError("png_scale must be a positive integer")

    raw_min, raw_max = float(np.nanmin(total)), float(np.nanmax(total))
    print(f"{png_path.name}: min {raw_min:.1f} (lightest), max {raw_max:.1f} (darkest)")
    vmin, vmax = raw_min, raw_max

    if vmax == vmin:
        print(f"  All pixels equal ({vmin:.1f}); the whole map will be the lightest colour.")
        vmax = vmin + 1.0

    projected, lonlat_bounds = reproject_to_webmercator(total, crs, transform, bounds)
    if not np.isfinite(projected).any():
        raise ValueError(f"Reprojection left no valid pixels for {png_path.name}")

    write_map(
        projected, lonlat_bounds, colors, png_path, json_path,
        column, units, vmin, vmax, raw_min, raw_max,
        png_scale=png_scale, discrete_colors=discrete_colors,
    )


def render_pngs(
    tif_path: Path,
    cold_png_path: Path, cold_json_path: Path,
    heat_png_path: Path, heat_json_path: Path,
    cold_colors: list[str], heat_colors: list[str],
    png_scale: int = 1, discrete_colors: bool = False,
):

    with rasterio.open(tif_path) as src:

        index = band_indices(
            src, MIN_BAND_NAMES + MAX_BAND_NAMES + [COLD_TOTAL_BAND, HEAT_TOTAL_BAND]
        )

        if src.crs is None:
            raise ValueError(f"{tif_path} has no CRS")

        cold_days = src.read(index[COLD_TOTAL_BAND]).astype(np.float64)
        heat_days = src.read(index[HEAT_TOTAL_BAND]).astype(np.float64)
        crs, transform, bounds = src.crs, src.transform, src.bounds

    render_map(cold_days, crs, transform, bounds, cold_colors,
               cold_png_path, cold_json_path, COLD_TOTAL_BAND, "days", png_scale, discrete_colors)
    render_map(heat_days, crs, transform, bounds, heat_colors,
               heat_png_path, heat_json_path, HEAT_TOTAL_BAND, "days", png_scale, discrete_colors)

