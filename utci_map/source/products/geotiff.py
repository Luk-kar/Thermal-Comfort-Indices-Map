"""Write the summary GeoTIFF."""

import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine

from utci_map.source.contracts import Band
from utci_map.source.runlog import logged_write

_LOGGER = logging.getLogger(__name__)


def write_geotiff(
    path: Path, bands: Sequence[Band], transform: Affine, start_year: int, end_year: int
) -> None:
    """
    Write summary bands to a multiband GeoTIFF in EPSG:4326, replacing any existing file.

    Each band is a (name, values, units) tuple whose values have shape (height, width);
    the file has shape (number_of_bands, height, width). Values are stored as float32
    with NaN marking missing pixels. Band names become band descriptions, units become
    band tags, and start_year and end_year are stored as dataset tags.
    """
    height, width = bands[0][1].shape

    with (
        logged_write(_LOGGER, path),
        rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=len(bands),
            dtype="float32",
            crs="EPSG:4326",
            transform=transform,
            nodata=np.nan,
            compress="deflate",
            predictor=3,
        ) as dst,
    ):
        for index, (name, values, units) in enumerate(bands, start=1):
            dst.write(values.astype("float32"), index)
            dst.set_band_description(index, name)
            dst.update_tags(index, units=units)

        dst.update_tags(start_year=start_year, end_year=end_year)
