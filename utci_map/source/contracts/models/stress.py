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
        """Reject an unknown direction, mismatched names, or brackets the counts can't describe."""
        if self.direction not in ("above", "below"):
            raise ValueError(f"direction must be 'above' or 'below', got {self.direction!r}")

        if not len(self.brackets) == len(self.fields) == len(self.band_names):
            raise ValueError(
                f"{self.name} side needs one field and one band name per bracket, got "
                f"{len(self.brackets)} brackets, {len(self.fields)} fields "
                f"and {len(self.band_names)} band names"
            )

        self._check_contiguous()
        self._check_open_ended()

    def _check_contiguous(self) -> None:
        """Reject brackets with gaps or overlaps between neighbors."""
        for (_, upper), (lower, _) in zip(self.brackets, self.brackets[1:]):
            if upper != lower:
                raise ValueError(f"Brackets are not contiguous: {upper} != {lower}")

    def _check_open_ended(self) -> None:
        """Reject a closed outermost bracket, which cumulative day counts can't describe."""
        if self.direction == "above":
            outer = self.brackets[-1]
            is_open = outer[1] == float("inf")
            requirement = "The last 'above' bracket must be open-ended (upper bound inf)"
        else:
            outer = self.brackets[0]
            is_open = outer[0] == float("-inf")
            requirement = "The first 'below' bracket must be open-ended (lower bound -inf)"

        if not is_open:
            raise ValueError(f"{requirement}, but it is {outer[0]:g} to {outer[1]:g}")
