"""Define the data passed from the loading stage to the computation and output stages."""

from dataclasses import dataclass

import numpy as np
from rasterio.transform import Affine

Band = tuple[str, np.ndarray, str]  # (name, values with shape (height, width), units)


@dataclass(frozen=True)
class FileRecords:
    """
    Hold the selected UTCI fields read from a single input NetCDF file.

    Years come from the NetCDF time coordinates. Arrays hold one (height, width)
    array per year, with missing data masked as NaN and scale/offset applied.
    Peak units and grid information come from the fields' metadata.
    """

    years: list[int]  # e.g. [2015, 2016]
    # e.g. {"utci_yearly_max": [array_2015, array_2016]}
    arrays: dict[str, list[np.ndarray]]
    peak_units: dict[str, str]  # e.g. {"utci_yearly_max": "K", "utci_yearly_min": "K"}
    shape: tuple[int, int]  # (height, width), e.g. (180, 360)
    transform: Affine  # e.g. Affine(0.25, 0.0, -25.0, 0.0, -0.25, 67.0)


@dataclass(frozen=True)
class FieldRecords:
    """
    Hold yearly statistics read from one UTCI field in a NetCDF file.

    Years come from the field's time coordinates. Each array contains
    values for one year, with missing data masked as NaN and scale/offset
    applied. Grid information comes from the field's metadata.
    The unit is recorded only for yearly maximum and minimum UTCI fields.
    """

    years: list[int]  # e.g. [2015, 2016]
    arrays: list[np.ndarray]  # e.g. [array_2015, array_2016]; each array has shape (height, width)
    shape: tuple[int, int]  # (height, width), e.g. (180, 360)
    transform: Affine  # e.g. Affine(0.25, 0.0, -25.0, 0.0, -0.25, 67.0)
    # e.g. "K" (kelvin) for a yearly peak field, "" if undeclared, or None for a day-count field
    peak_unit: str | None


@dataclass(frozen=True)
class YearlyStats:
    """
    Hold selected UTCI fields combined across input NetCDF files.

    Records are filtered to the configured year range and sorted by year.
    For each field, yearly arrays are stacked in the same order as years,
    with missing values represented as NaN and scale/offset already applied.
    Peak units and grid information are checked for consistency across files.
    """

    years: np.ndarray  # e.g. np.array([2015, 2016]); shape (number_of_years,)
    # e.g. {"utci_yearly_max": values}; values have shape (number_of_years, height, width)
    cubes: dict[str, np.ndarray]
    peak_units: dict[str, str]  # e.g. {"utci_yearly_max": "K", "utci_yearly_min": "K"}
    shape: tuple[int, int]  # shared (height, width), e.g. (180, 360)
    transform: Affine  # shared grid transform, e.g. Affine(0.25, 0.0, -25.0, 0.0, -0.25, 67.0)
