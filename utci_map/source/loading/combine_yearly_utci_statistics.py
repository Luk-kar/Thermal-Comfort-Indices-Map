"""
Combine yearly UTCI statistics for the selected period into one dataset.

Ensure years are unique, required years are present, and all input files
describe the same spatial grid and use consistent units for UTCI extremes.
"""

from pathlib import Path

import numpy as np

from ..models import FileRecords, YearlyStats
from .netcdf_reader import read_yearly_file, transforms_match
from ..schema import SELECTED_NETCDF_FIELDS


YearRecord = tuple[int, dict[str, np.ndarray]]

def load_yearly_statistics(
    data_dir: Path,
    start_year: int,
    end_year: int,
    require_complete_period: bool,
) -> YearlyStats:
    """Load consistent yearly UTCI statistics for the selected period."""

    records, reference = _collect_yearly_records(data_dir)

    selected_records = _select_period_records(
        records,
        start_year,
        end_year,
    )

    _validate_period_years(
        selected_records,
        start_year,
        end_year,
        require_complete_period,
    )

    return _assemble_yearly_statistics(selected_records, reference)
    
def _check_file_consistency(
    loaded: FileRecords,
    reference: FileRecords,
    nc_file: Path,
) -> None:
    """Ensure the file uses the same spatial grid and peak units as the first file."""
    
    if (
        loaded.shape != reference.shape
        or not transforms_match(loaded.transform, reference.transform)
    ):
        raise ValueError(f"{nc_file.name}: grid differs from the first file")

    if loaded.peak_units != reference.peak_units:
        raise ValueError(
            f"{nc_file.name}: peak units {loaded.peak_units} "
            f"differ from {reference.peak_units}"
        )


def _collect_yearly_records(
    data_dir: Path,
) -> tuple[list[YearRecord], FileRecords]:
    """Read selected UTCI fields from compatible yearly-statistics files."""
    
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

        for position, year in enumerate(loaded.years):
            fields = {
                name: loaded.arrays[name][position]
                for name in SELECTED_NETCDF_FIELDS
            }
            records.append((year, fields))

    if not records or reference is None:
        raise FileNotFoundError(
            f"No yearly-statistics files in {data_dir.resolve()}"
        )

    return records, reference


def _select_period_records(
    records: list[YearRecord],
    start_year: int,
    end_year: int,
) -> list[YearRecord]:
    """Select records within the inclusive year range."""

    selected = [
        record
        for record in records
        if start_year <= record[0] <= end_year
    ]

    if not selected:
        raise ValueError(f"No records within {start_year}-{end_year}")

    return selected


def _validate_period_years(
    records: list[YearRecord],
    start_year: int,
    end_year: int,
    require_complete_period: bool,
) -> None:
    """Reject duplicate years and handle missing years according to period requirements."""

    years = np.array([year for year, _ in records], dtype=int)

    duplicates = sorted({
        int(year)
        for year in years
        if (years == year).sum() > 1
    })
    if duplicates:
        raise ValueError(f"Duplicate yearly records for: {duplicates}")

    missing_years = sorted(
        set(range(start_year, end_year + 1)) - set(years.tolist())
    )
    if missing_years and require_complete_period:
        raise ValueError(f"Missing years: {missing_years}")

    if missing_years:
        print(
            f"WARNING: missing years {missing_years}; "
            f"using {years.size} years"
        )


def _assemble_yearly_statistics(
    records: list[YearRecord],
    reference: FileRecords,
) -> YearlyStats:
    """Combine selected records into chronological yearly statistics."""

    ordered_records = sorted(records, key=lambda record: record[0])

    return YearlyStats(
        years=np.array(
            [year for year, _ in ordered_records],
            dtype=int,
        ),
        cubes={
            name: np.stack([
                fields[name]
                for _, fields in ordered_records
            ])
            for name in SELECTED_NETCDF_FIELDS
        },
        peak_units=reference.peak_units,
        shape=reference.shape,
        transform=reference.transform,
    )