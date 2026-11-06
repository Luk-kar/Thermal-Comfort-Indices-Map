"""Describe thermal-stress brackets and the heat and cold sides built from them."""

from dataclasses import dataclass
from typing import Literal

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
