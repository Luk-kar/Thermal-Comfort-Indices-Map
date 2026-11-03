"""Write JSON metadata accompanying cold- and heat-day PNG maps."""

import json
from pathlib import Path
from typing import Any

import numpy as np

from utci_map.source.config import COLOR_MAP_STEP, MAX_INDEX, NODATA_INDEX
from utci_map.source.products.maps.models import Bounds, ImagePlacement, MetricScale

COORDINATE_DECIMALS = 6
METRIC_DECIMALS = 6
COLOR_MAP_VALUE_DECIMALS = 4


def write_sidecar(
    json_path: Path,
    png_path: Path,
    *,
    placement: ImagePlacement,
    metric: MetricScale,
    rgb: np.ndarray,
) -> None:
    """
    Describe the PNG placement, metric range, colors and missing pixels.

    rgb is the (MAX_INDEX + 1, 3) palette used for the PNG, and metric.vmin and
    metric.vmax its display range, so the sidecar's color-map entries describe the
    rendered image. Raise ValueError if any value is NaN or infinite.
    """
    sidecar = {
        "image": png_path.name,
        "crs": placement.crs,
        "coordinates": _corner_coordinates(placement.lonlat_bounds),
        "metric": _metric_entry(metric),
        "nodata": {"palette_index": NODATA_INDEX, "alpha": 0},
        "color_map": _color_map(rgb, metric.vmin, metric.vmax),
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(sidecar, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _corner_coordinates(lonlat_bounds: Bounds) -> list[list[float]]:
    """
    List image corners in MapLibre image-source order.

    E.g. (west, south, east, north) -> [[west, north], [east, north], [east, south], [west, south]].
    """
    west, south, east, north = (round(float(v), COORDINATE_DECIMALS) for v in lonlat_bounds)
    return [[west, north], [east, north], [east, south], [west, south]]


def _metric_entry(metric: MetricScale) -> dict[str, Any]:
    """Describe the metric and its value ranges, rounded for JSON."""
    return {
        "column": metric.column,
        "min": round(metric.vmin, METRIC_DECIMALS),
        "max": round(metric.vmax, METRIC_DECIMALS),
        "units": metric.units,
        "raw_min": round(metric.raw_min, METRIC_DECIMALS),
        "raw_max": round(metric.raw_max, METRIC_DECIMALS),
        "local_min": round(metric.local_min, METRIC_DECIMALS),
        "local_max": round(metric.local_max, METRIC_DECIMALS),
    }


def _color_map(rgb: np.ndarray, vmin: float, vmax: float) -> list[dict[str, Any]]:
    """Sample every COLOR_MAP_STEP-th palette index, plus the last, with its color and value."""
    entries = [*range(0, MAX_INDEX, COLOR_MAP_STEP), MAX_INDEX]
    return [
        {
            "index": i,
            "rgb": [int(channel) for channel in rgb[i]],
            "value": round(vmin + (vmax - vmin) * i / MAX_INDEX, COLOR_MAP_VALUE_DECIMALS),
        }
        for i in entries
    ]
