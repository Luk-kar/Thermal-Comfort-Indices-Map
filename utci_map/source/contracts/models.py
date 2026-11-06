"""Data contracts between the loading, computation and output stages."""

from dataclasses import dataclass
from typing import Literal

import numpy as np
from rasterio.transform import Affine

Band = tuple[str, np.ndarray, str]  # (name, values with shape (height, width), units)
Bracket = tuple[float, float]  # (lower, upper) UTCI (Universal Thermal Climate Index) bound in °C
# How the day counts from the CDS (Copernicus Climate Data Store) accumulate.
Direction = Literal["above", "below"]


@dataclass(frozen=True, kw_only=True)
class StressSide:
    """
    Describe the heat or cold side of the thermal-stress categories.

    The fields are the cumulative CDS day counts, one per threshold in threshold order,
    and band_names hold one summary band per bracket. E.g. the heat side has direction
    "above", fields ("utci_days_above_26_daily_max", ...), band_names
    ("days_daily_max_26_32", ...) and total_band "days_daily_max_above_26_total".
    The CDS variables are documented at
    https://cds.climate.copernicus.eu/datasets/derived-utci-historical
    """

    name: str  # "heat" or "cold"
    statistic: str  # CDS daily statistic, "daily_max" or "daily_min"
    direction: Direction
    brackets: tuple[Bracket, ...]
    fields: tuple[str, ...]
    band_names: tuple[str, ...]
    total_band: str

    def __post_init__(self) -> None:
        """Reject a side whose direction is unknown or whose names don't match its brackets."""
        if self.direction not in ("above", "below"):
            raise ValueError(f"direction must be 'above' or 'below', got {self.direction!r}")

        if not len(self.brackets) == len(self.fields) == len(self.band_names):
            raise ValueError(
                f"{self.name} side needs one field and one band name per bracket, got "
                f"{len(self.brackets)} brackets, {len(self.fields)} fields "
                f"and {len(self.band_names)} band names"
            )


@dataclass(frozen=True, kw_only=True)
class MapKind:
    """
    Describe one rendered map: which GeoTIFF band it shows, its file names and palette.

    E.g. name "cold", total_band "days_daily_min_below_9_total" and file_stem
    "utci_cold_days" give utci_cold_days.png and utci_cold_days.json.
    """

    name: str
    total_band: str
    file_stem: str
    colors: tuple[str, ...]


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
