"""
Build color palettes for UTCI cold- and heat-day maps.

Map day counts to palette indices for PNG rendering, with a reserved
index for transparent missing pixels.
"""

import re
from collections.abc import Sequence

import numpy as np

from utci_map.source.config import MAX_INDEX, NODATA_INDEX

HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")


def palette_rgb(colors: Sequence[str], discrete_colors: bool = False) -> np.ndarray:
    """
    Return an RGB color for each data palette index from 0 to MAX_INDEX.

    The result has shape (MAX_INDEX + 1, 3) and dtype uint8. Colors are blended
    evenly across the indices, or used as equal-width steps when discrete_colors
    is set. E.g. with MAX_INDEX = 254 and colors ["#000000", "#ffffff"], index 127
    is mid-gray (128, 128, 128); index NODATA_INDEX is left for missing pixels.
    """
    fraction = np.arange(MAX_INDEX + 1) / MAX_INDEX
    palette = np.array([_hex_to_rgb(color) for color in colors], dtype=np.float64)

    if discrete_colors:
        steps = np.minimum((fraction * len(colors)).astype(np.intp), len(colors) - 1)
        rgb = palette[steps]
    else:
        stops = np.linspace(0.0, 1.0, len(colors))
        rgb = np.stack(
            [np.interp(fraction, stops, palette[:, channel]) for channel in range(3)], axis=-1
        )
    return np.rint(rgb).astype(np.uint8)


def to_indices(values: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    """
    Quantize a (height, width) array to uint8 palette indices of the same shape.

    Values are clipped to vmin..vmax and spread over 0..MAX_INDEX; NaN becomes
    NODATA_INDEX. E.g. with vmin=0, vmax=100 and MAX_INDEX = 254, 50 -> 127.
    """
    valid = np.isfinite(values)
    fraction = np.where(valid, np.clip((values - vmin) / (vmax - vmin), 0.0, 1.0), 0.0)
    indices = np.rint(fraction * MAX_INDEX).astype(np.uint8)
    indices[~valid] = NODATA_INDEX
    return indices


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    """Convert '#rrggbb' to an (r, g, b) tuple of ints."""
    if not HEX_COLOR_RE.fullmatch(color):
        raise ValueError(f"Invalid color {color!r}; expected '#rrggbb'")
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
