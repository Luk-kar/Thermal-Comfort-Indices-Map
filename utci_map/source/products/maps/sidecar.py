"""Write JSON metadata accompanying cold- and heat-day PNG maps."""

import json
from pathlib import Path

import numpy as np

from utci_map.source.config import MAX_INDEX, NODATA_INDEX, COLOR_MAP_STEP


def write_sidecar(
    json_path: Path,
    png_path: Path,
    lonlat_bounds,
    crs: str,
    rgb: np.ndarray,
    column: str,
    units: str,
    vmin: float,
    vmax: float,
    raw_min: float,
    raw_max: float,
    local_min: float,
    local_max: float,
) -> None:
    """Describe the PNG placement, metric range, colours and missing pixels.

    Use the same RGB palette and display range as the PNG so that the
    sidecar's colour-map entries describe the rendered image consistently.

    raw_min and raw_max span every region; local_min and local_max describe
    this region alone.
    """

    west, south, east, north = (round(float(v), 6) for v in lonlat_bounds)
    entries = [*range(0, MAX_INDEX, COLOR_MAP_STEP), MAX_INDEX]
    sidecar = {
        "image": png_path.name,
        "crs": crs,
        "coordinates": [[west, north], [east, north], [east, south], [west, south]],
        "metric": {
            "column": column,
            "min": round(vmin, 6),
            "max": round(vmax, 6),
            "units": units,
            "raw_min": round(raw_min, 6),
            "raw_max": round(raw_max, 6),
            "local_min": round(local_min, 6),
            "local_max": round(local_max, 6),
        },
        "nodata": {"palette_index": NODATA_INDEX, "alpha": 0},
        "color_map": [
            {
                "index": i,
                "rgb": [int(c) for c in rgb[i]],
                "value": round(vmin + (vmax - vmin) * i / MAX_INDEX, 4),
            }
            for i in entries
        ],
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(sidecar, indent=2, allow_nan=False) + "\n", encoding="utf-8")
