"""
Combine yearly UTCI statistics for the selected period into one dataset.

Ensure years are unique, required years are present, and all input files
describe the same spatial grid and use consistent units for UTCI extremes.
"""

import logging
from collections import Counter
from pathlib import Path

import numpy as np

from utci_map.source.contracts import SELECTED_NETCDF_FIELDS, FileRecords, YearlyStats
from utci_map.source.loading.netcdf_reader import read_yearly_file, same_grid

_LOGGER = logging.getLogger(__name__)

YearRecord = tuple[int, dict[str, np.ndarray]]  # (year, {field name: (height, width) array})


def load_yearly_statistics(
    data_dir: Path,
    start_year: int,
    end_year: int,
    require_complete_period: bool,
) -> YearlyStats:
    """
    Load consistent yearly UTCI statistics for the inclusive period start_year-end_year.

    Read every yearly-statistics NetCDF file in data_dir, skipping other NetCDF files.
    Raise FileNotFoundError if there are none, and ValueError if files disagree on grid
    or peak units, a year appears twice, or no year falls in the period. A year missing
    from the period raises ValueError if require_complete_period is set, and only
    logs a warning otherwise.
    """
    records, reference = _collect_yearly_records(data_dir)
    selected = [record for record in records if start_year <= record[0] <= end_year]
    if not selected:
        raise ValueError(f"No records within {start_year}-{end_year} in {data_dir}")

    _validate_period_years(
        [year for year, _ in selected],
        start_year=start_year,
        end_year=end_year,
        require_complete_period=require_complete_period,
    )
    return _assemble_yearly_statistics(selected, reference)


def _collect_yearly_records(data_dir: Path) -> tuple[list[YearRecord], FileRecords]:
    """Read yearly records from all compatible files, returning them with the first file."""
    records: list[YearRecord] = []
    reference: FileRecords | None = None

    for nc_file in sorted(data_dir.glob("*.nc")):
        loaded = read_yearly_file(nc_file)
        if loaded is None:
            continue
        if reference is None:
            reference = loaded
        else:
            _check_file_consistency(loaded, reference, nc_file)
        records.extend(_year_records(loaded))

    if reference is None:
        raise FileNotFoundError(f"No yearly-statistics files in {data_dir.resolve()}")
    return records, reference


def _check_file_consistency(loaded: FileRecords, reference: FileRecords, nc_file: Path) -> None:
    """Ensure the file uses the same spatial grid and peak units as the first file."""
    if not same_grid(loaded, reference):
        raise ValueError(f"{nc_file.name}: grid differs from the first file")

    if loaded.peak_units != reference.peak_units:
        raise ValueError(
            f"{nc_file.name}: peak units {loaded.peak_units} differ from {reference.peak_units}"
        )


def _year_records(loaded: FileRecords) -> list[YearRecord]:
    """Split one file's fields into one record per year."""
    return [
        (year, {name: loaded.arrays[name][position] for name in SELECTED_NETCDF_FIELDS})
        for position, year in enumerate(loaded.years)
    ]


def _validate_period_years(
    years: list[int], *, start_year: int, end_year: int, require_complete_period: bool
) -> None:
    """Reject duplicate years, and reject or warn about years missing from the period."""
    duplicates = sorted(year for year, count in Counter(years).items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate yearly records for: {duplicates}")

    missing_years = sorted(set(range(start_year, end_year + 1)) - set(years))
    if not missing_years:
        return
    if require_complete_period:
        raise ValueError(f"Missing years: {missing_years}")
    _LOGGER.warning("Missing years %s; using %d years", missing_years, len(years))


def _assemble_yearly_statistics(records: list[YearRecord], reference: FileRecords) -> YearlyStats:
    """Stack records chronologically into (years, height, width) cubes per field."""
    ordered = sorted(records, key=lambda record: record[0])

    return YearlyStats(
        years=np.array([year for year, _ in ordered], dtype=int),
        cubes={
            name: np.stack([fields[name] for _, fields in ordered])
            for name in SELECTED_NETCDF_FIELDS
        },
        peak_units=reference.peak_units,
        shape=reference.shape,
        transform=reference.transform,
    )
