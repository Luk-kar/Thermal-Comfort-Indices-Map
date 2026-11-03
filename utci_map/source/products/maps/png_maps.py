"""Render the cold and heat total bands of a summary GeoTIFF as indexed PNGs with sidecars."""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

from utci_map.source.config import MAX_INDEX, NODATA_INDEX
from utci_map.source.products.geotiff import band_indices
from utci_map.source.products.maps.land_mask import land_mask, load_land_geometries
from utci_map.source.products.maps.models import (
    WEBMERCATOR_CRS,
    Geometry,
    ImagePlacement,
    MapLayer,
    MapOutput,
    MetricScale,
    RasterGrid,
    RenderOptions,
    ValueRange,
)
from utci_map.source.products.maps.palette import palette_rgb, to_indices
from utci_map.source.products.maps.reprojection import reproject_to_webmercator
from utci_map.source.products.maps.sidecar import write_sidecar
from utci_map.source.schema import COLD_TOTAL_BAND, HEAT_TOTAL_BAND, MAX_BAND_NAMES, MIN_BAND_NAMES

DAY_UNITS = "days"
REQUIRED_BANDS = [*MIN_BAND_NAMES, *MAX_BAND_NAMES, COLD_TOTAL_BAND, HEAT_TOTAL_BAND]


def render_pngs(
    tif_path: Path,
    cold: MapOutput,
    heat: MapOutput,
    options: RenderOptions | None = None,
    value_ranges: tuple[ValueRange, ValueRange] | None = None,
) -> None:
    """
    Render the cold and heat maps of one GeoTIFF as PNGs with JSON sidecars.

    value_ranges are the (cold, heat) ranges mapped onto each palette, as returned
    by global_value_ranges; without them each map is normalized to its own range.
    Raise KeyError if a summary band is missing, and ValueError if the GeoTIFF
    has no CRS, a map has no valid pixels, or options.png_scale is below 1.
    """
    options = options or RenderOptions()
    cold_range, heat_range = value_ranges or (None, None)
    cold_layer, heat_layer, land_geometries = _load_layers(tif_path, options)

    _render_map(cold_layer, cold, options, land_geometries, cold_range)
    _render_map(heat_layer, heat, options, land_geometries, heat_range)


def global_value_ranges(
    tif_paths: Sequence[Path], options: RenderOptions | None = None
) -> tuple[ValueRange, ValueRange]:
    """
    Return the (cold, heat) value ranges spanning every GeoTIFF.

    Rasters are read one at a time, with sea masked as for rendering. Raise
    ValueError if the cold or heat band has no valid pixel in any GeoTIFF.
    """
    options = options or RenderOptions()
    cold_ranges: list[ValueRange | None] = []
    heat_ranges: list[ValueRange | None] = []

    for tif_path in tif_paths:
        cold_layer, heat_layer, _ = _load_layers(tif_path, options)
        cold_ranges.append(_finite_range(cold_layer.values))
        heat_ranges.append(_finite_range(heat_layer.values))

    return _spanning_range(cold_ranges), _spanning_range(heat_ranges)


def _finite_range(values: np.ndarray) -> ValueRange | None:
    """Return the range of the finite values, or None if there are none."""
    if not np.isfinite(values).any():
        return None
    return ValueRange(float(np.nanmin(values)), float(np.nanmax(values)))


def _spanning_range(ranges: Sequence[ValueRange | None]) -> ValueRange:
    """Return the smallest range containing every non-empty range."""
    valid = [value_range for value_range in ranges if value_range is not None]
    if not valid:
        raise ValueError("No valid pixels to compute global value ranges")
    return ValueRange(min(r.vmin for r in valid), max(r.vmax for r in valid))


def _load_layers(
    tif_path: Path, options: RenderOptions
) -> tuple[MapLayer, MapLayer, list[Geometry] | None]:
    """Read the cold and heat total layers, masking sea pixels when a coastline is set."""
    cold_days, heat_days, grid = _read_total_bands(tif_path)

    land_geometries = None
    if options.coastline_path is not None:
        land_geometries = load_land_geometries(options.coastline_path)
        land = land_mask(land_geometries, cold_days.shape, grid)
        cold_days[~land] = np.nan
        heat_days[~land] = np.nan

    cold_layer = MapLayer(
        values=cold_days, grid=grid, metric_band_name=COLD_TOTAL_BAND, metric_units=DAY_UNITS
    )
    heat_layer = MapLayer(
        values=heat_days, grid=grid, metric_band_name=HEAT_TOTAL_BAND, metric_units=DAY_UNITS
    )
    return cold_layer, heat_layer, land_geometries


def _read_total_bands(tif_path: Path) -> tuple[np.ndarray, np.ndarray, RasterGrid]:
    """Read the cold and heat total bands as float64 (height, width) arrays and their grid."""
    with rasterio.open(tif_path) as src:
        index = band_indices(src, REQUIRED_BANDS)
        if src.crs is None:
            raise ValueError(f"{tif_path} has no CRS")

        cold_days = src.read(index[COLD_TOTAL_BAND]).astype(np.float64)
        heat_days = src.read(index[HEAT_TOTAL_BAND]).astype(np.float64)
        grid = RasterGrid(crs=src.crs, grid_transform=src.transform, bounds=tuple(src.bounds))
    return cold_days, heat_days, grid


def _render_map(
    layer: MapLayer,
    output: MapOutput,
    options: RenderOptions,
    land_geometries: list[Geometry] | None = None,
    value_range: ValueRange | None = None,
) -> None:
    """
    Reproject a layer, mask sea pixels when land is given, and write its PNG and sidecar.

    Colors follow value_range when given, otherwise the layer's own range.
    """
    if not np.isfinite(layer.values).any():
        raise ValueError(f"No valid pixels to plot for {output.png_path.name}")
    if options.png_scale < 1:
        raise ValueError("png_scale must be a positive integer")

    metric = _metric_scale(layer, value_range, output.png_path.name)
    projected, lonlat_bounds = reproject_to_webmercator(
        layer.values, layer.grid, land_geometries=land_geometries
    )
    if not np.isfinite(projected).any():
        raise ValueError(f"Reprojection left no valid pixels for {output.png_path.name}")

    rgb = palette_rgb(output.colors, options.discrete_colors)
    _write_png(projected, rgb=rgb, metric=metric, png_path=output.png_path, scale=options.png_scale)
    write_sidecar(
        output.json_path,
        output.png_path,
        placement=ImagePlacement(lonlat_bounds=lonlat_bounds, crs=WEBMERCATOR_CRS.to_string()),
        metric=metric,
        rgb=rgb,
    )


def _metric_scale(layer: MapLayer, value_range: ValueRange | None, image_name: str) -> MetricScale:
    """Choose the display range, widening an empty one so the map renders in the lightest color."""
    local = ValueRange(float(np.nanmin(layer.values)), float(np.nanmax(layer.values)))
    raw = value_range or local
    print(
        f"{image_name}: min {local.vmin:.1f}, max {local.vmax:.1f}; "
        f"color scale {raw.vmin:.1f} (lightest) to {raw.vmax:.1f} (darkest)"
    )

    vmax = raw.vmax
    if raw.vmax == raw.vmin:
        print(f"  All pixels equal ({raw.vmin:.1f}); the whole map will be the lightest color.")
        vmax = raw.vmin + 1.0

    return MetricScale(
        column=layer.metric_band_name,
        units=layer.metric_units,
        vmin=raw.vmin,
        vmax=vmax,
        raw_min=raw.vmin,
        raw_max=raw.vmax,
        local_min=local.vmin,
        local_max=local.vmax,
    )


def _write_png(
    values: np.ndarray, *, rgb: np.ndarray, metric: MetricScale, png_path: Path, scale: int
) -> None:
    """Write a palette-indexed PNG with NODATA_INDEX transparent, enlarged by an integer scale."""
    image = Image.fromarray(to_indices(values, metric.vmin, metric.vmax))

    palette = np.zeros((NODATA_INDEX + 1, 3), dtype=np.uint8)
    palette[: MAX_INDEX + 1] = rgb
    image.putpalette(palette.reshape(-1).tolist())

    if scale != 1:
        image = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)

    png_path.parent.mkdir(parents=True, exist_ok=True)
    alpha = bytes([255] * NODATA_INDEX + [0])
    image.save(png_path, transparency=alpha)
