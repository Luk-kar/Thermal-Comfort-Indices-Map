"""Write the summary GeoTIFF and look up bands by description."""

from pathlib import Path

import numpy as np
import rasterio

def write_geotiff(path: Path, bands, transform, start_year: int, end_year: int):
    """
    Write summary bands to a multiband GeoTIFF.

    The output has shape (number_of_bands, height, width), with all bands
    sharing the same grid and geographic transform in EPSG:4326.

    Each input band is a (
        name,
        array,
        units
    )
    tuple, 
    where array has shape
    (
        height, 
        width
    ). 
    
    Values are stored as float32, with NaN marking missing
    pixels. 
    Band names and units are stored as descriptions and metadata;
    start_year and end_year describe the summarised period.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    height, width = bands[0][1].shape

    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width,
        count=len(bands), dtype="float32", crs="EPSG:4326",
        transform=transform, nodata=np.nan, compress="deflate", predictor=3,
    ) as dst:

        for index, (name, array, units) in enumerate(bands, start=1):
            dst.write(array.astype("float32"), index)
            dst.set_band_description(index, name)
            dst.update_tags(index, units=units)

        dst.update_tags(start_year=start_year, end_year=end_year)


def band_indices(src, required_names) -> dict[str, int]:
    """Return band indices and reject missing required descriptions."""

    index = {desc: i for i, desc in enumerate(src.descriptions, start=1)}
    missing = [name for name in required_names if name not in index]

    if missing:
        raise KeyError(f"Bands missing in {src.name}: {missing}")
    return index

