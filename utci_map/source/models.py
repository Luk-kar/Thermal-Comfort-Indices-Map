"""Data contracts between loading and computation stages."""

from dataclasses import dataclass

import numpy as np
from rasterio.transform import Affine

@dataclass(frozen=True)
class FileRecords:
    """
    Hold yearly statistics read from a single input NetCDF file.

    Populated by the selected UTCI fields.
    Years come from the NetCDF time coordinates; 
    arrays contain values with missing data masked as 
    NaN and scale/offset applied. 
    Peak units
    and grid information come from the fields' metadata.
    """

    years: list[int]  # e.g. [2015, 2016]
    arrays: dict[str, list[np.ndarray]]  # e.g. {"utci_yearly_max": [array_2015, array_2016]}; each array is 2-D
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
    peak_unit: str | None  # e.g. "K" (kelvin) for a yearly peak field, "" if undeclared, or None for a day-count field


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
    cubes: dict[str, np.ndarray]  # e.g. {"utci_yearly_max": values}; values have shape (number_of_years, height, width)
    peak_units: dict[str, str]  # e.g. {"utci_yearly_max": "K", "utci_yearly_min": "K"}
    shape: tuple[int, int]  # shared (height, width), e.g. (180, 360)
    transform: Affine  # shared grid transform, e.g. Affine(0.25, 0.0, -25.0, 0.0, -0.25, 67.0)
