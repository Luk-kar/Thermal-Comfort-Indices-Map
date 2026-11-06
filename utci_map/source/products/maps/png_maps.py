"""Render the cold and heat total bands of a summary GeoTIFF as indexed PNGs with sidecars."""

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.io import DatasetReader

from utci_map.source.contracts import (
    COLD_SIDE,
    HEAT_SIDE,
    MAP_KINDS,
    MAX_INDEX,
    NODATA_INDEX,
)
from utci_map.source.products.maps.encoding import palette_rgb, to_indices, write_sidecar
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
from utci_map.source.products.maps.reprojection import reproject_to_webmercator
from utci_map.source.runlog import logged_read, logged_write

_LOGGER = logging.getLogger(__name__)

DAY_UNITS = "days"
REQUIRED_BANDS = [
    *COLD_SIDE.band_names,
    *HEAT_SIDE.band_names,
    *(kind.total_band for kind in MAP_KINDS),
]


def render_pngs(
    tif_path: Path,
    outputs: Mapping[str, MapOutput],
    options: RenderOptions | None = None,
    value_ranges: Mapping[str, ValueRange] | None = None,
) -> None:
    """
    Render every map kind of one GeoTIFF as a PNG with a JSON sidecar.

    outputs and value_ranges are keyed by map kind name, e.g. {"cold": ..., "heat": ...}.
    value_ranges are mapped onto each palette, as returned by global_value_ranges;
    without them each map is normalized to its own range. Raise KeyError if a summary
    band is missing, ValueError if outputs don't name exactly the map kinds, the GeoTIFF
    has no CRS, a map has no valid pixels, or options.png_scale is below 1.
    """
    _check_kind_names(outputs, "outputs")
    if value_ranges is not None:
        _check_kind_names(value_ranges, "value_ranges")

    options = options or RenderOptions()
    layers, land_geometries = _load_layers(tif_path, options)

    for name, layer in layers.items():
        value_range = value_ranges[name] if value_ranges else None
        _render_map(layer, outputs[name], options, land_geometries, value_range)


def global_value_ranges(
    tif_paths: Sequence[Path], options: RenderOptions | None = None
) -> dict[str, ValueRange]:
    """
    Return the value range of each map kind spanning every GeoTIFF, keyed by kind name.

    Rasters are read one at a time, with sea masked as for rendering. Raise
    ValueError if a map kind's band has no valid pixel in any GeoTIFF.
    """
    options = options or RenderOptions()
    ranges: dict[str, list[ValueRange | None]] = {kind.name: [] for kind in MAP_KINDS}

    for tif_path in tif_paths:
        layers, _ = _load_layers(tif_path, options)
        for name, layer in layers.items():
            ranges[name].append(_finite_range(layer.values))

    return {name: _spanning_range(kind_ranges) for name, kind_ranges in ranges.items()}


def _check_kind_names(by_kind: Mapping[str, object], argument: str) -> None:
    """Reject a mapping whose keys are not exactly the configured map kind names."""
    expected = {kind.name for kind in MAP_KINDS}

    if set(by_kind) != expected:
        raise ValueError(f"{argument} must have keys {sorted(expected)}, got {sorted(by_kind)}")


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
) -> tuple[dict[str, MapLayer], list[Geometry] | None]:
    """Read each map kind's total layer, keyed by kind name, masking sea when a coastline is set."""
    days_by_kind, grid = _read_total_bands(tif_path)

    land_geometries = None
    if options.coastline_path is not None:
        land_geometries = load_land_geometries(options.coastline_path)
        land = land_mask(land_geometries, _grid_shape(days_by_kind), grid)
        for days in days_by_kind.values():
            days[~land] = np.nan

    layers = {
        kind.name: MapLayer(
            values=days_by_kind[kind.name],
            grid=grid,
            metric_band_name=kind.total_band,
            metric_units=DAY_UNITS,
        )
        for kind in MAP_KINDS
    }
    return layers, land_geometries


def _grid_shape(days_by_kind: Mapping[str, np.ndarray]) -> tuple[int, int]:
    """Return the shared (height, width) of the total bands."""
    height, width = next(iter(days_by_kind.values())).shape
    return height, width


def _read_total_bands(tif_path: Path) -> tuple[dict[str, np.ndarray], RasterGrid]:
    """Read each map kind's total band as a float64 (height, width) array, plus their grid."""
    with logged_read(_LOGGER, tif_path), rasterio.open(tif_path) as src:
        index = _band_indices(src, REQUIRED_BANDS)
        if src.crs is None:
            raise ValueError(f"{tif_path} has no CRS")

        days_by_kind = {
            kind.name: src.read(index[kind.total_band]).astype(np.float64) for kind in MAP_KINDS
        }
        grid = RasterGrid(crs=src.crs, grid_transform=src.transform, bounds=tuple(src.bounds))
    return days_by_kind, grid


def _band_indices(src: DatasetReader, required_names: Sequence[str]) -> dict[str, int]:
    """Map band descriptions to 1-based band indices, raising KeyError if any are missing."""
    index = {description: i for i, description in enumerate(src.descriptions, start=1)}
    missing = [name for name in required_names if name not in index]

    if missing:
        raise KeyError(f"Bands missing in {src.name}: {missing}")
    return index


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
    local = _finite_range(layer.values)
    if local is None:
        raise ValueError(f"No valid pixels to scale for {image_name}")

    raw = value_range or local
    _LOGGER.info(
        "%s: min %.1f, max %.1f; color scale %.1f (lightest) to %.1f (darkest)",
        image_name,
        local.vmin,
        local.vmax,
        raw.vmin,
        raw.vmax,
    )

    vmax = raw.vmax
    if raw.vmax == raw.vmin:
        _LOGGER.info(
            "%s: all pixels equal %.1f; the whole map will be the lightest color",
            image_name,
            raw.vmin,
        )
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

    alpha = bytes([255] * NODATA_INDEX + [0])

    with logged_write(_LOGGER, png_path):
        image.save(png_path, transparency=alpha)
