"""Describe the maps rendered from the summary GeoTIFF."""

from dataclasses import dataclass


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
