"""
Define colour palettes for UTCI cold- and heat-day maps.

Map day counts to palette indices for PNG rendering, with a reserved
index for transparent missing pixels.
"""
import re

import numpy as np

from ..config import MAX_INDEX, NODATA_INDEX

def hex_to_rgb(color: str) -> tuple[int, int, int]:

    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError(f"Invalid colour {color!r}; expected '#rrggbb'")
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def palette_rgb(colors: list[str], discrete_colors: bool = False) -> np.ndarray:
    """
    Return an RGB colour for each map palette index from 0 to MAX_INDEX.

    MAX_INDEX is the highest palette index used for data values; a separate
    index is reserved for transparent missing pixels. For example, with
    MAX_INDEX = 254, indices 0–254 represent data and index 255 marks
    missing pixels.

    The result has shape (MAX_INDEX + 1, 3), with one row per data index
    and columns for the red, green, and blue channels.
    """

    fraction = np.arange(MAX_INDEX + 1) / MAX_INDEX
    palette = np.array([hex_to_rgb(c) for c in colors], dtype=np.float64)

    if discrete_colors:
        steps = np.minimum((fraction * len(colors)).astype(np.intp), len(colors) - 1)
        rgb = palette[steps]
    else:
        stops = np.linspace(0.0, 1.0, len(colors))
        rgb = np.stack([np.interp(fraction, stops, palette[:, c]) for c in range(3)], axis=-1)
    return np.rint(rgb).astype(np.uint8)


def to_indices(values: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    """
    Quantise values to palette indices; 
    missing pixels get NODATA_INDEX.
    """

    valid = np.isfinite(values)
    fraction = np.where(valid, np.clip((values - vmin) / (vmax - vmin), 0.0, 1.0), 0.0)
    indices = np.rint(fraction * MAX_INDEX).astype(np.uint8)
    indices[~valid] = NODATA_INDEX
    return indices
