"""Check that load_yearly_statistics combines NetCDF files into one consistent dataset.

Cover year filtering and ordering, missing and duplicate years, and rejection of files
with mismatched grids or peak units.
"""

import numpy as np
import pytest

pytest.importorskip("rasterio")
from utci_map.source.loading.combine_yearly_utci_statistics import load_yearly_statistics


def test_combines_sorts_and_filters_records(netcdf_factory, tmp_path):
    """
    Check that records from multiple files form one chronological dataset.

    Create one file for 2018 and another for 2015–2017, with filenames
    placing the later year first. Request 2016–2018 and verify that 2015
    is excluded, years are sorted, and field values follow the same order.

    Check the combined array shapes, peak units, and missing pixels.
    """
    netcdf_factory("a.nc", years=(2018,))
    netcdf_factory("b.nc", years=(2015, 2016, 2017))
    result = load_yearly_statistics(
        tmp_path, start_year=2016, end_year=2018, require_complete_period=True
    )

    np.testing.assert_array_equal(result.years, [2016, 2017, 2018])

    assert result.shape == (4, 4)
    assert result.peak_units == {"utci_yearly_max": "degC", "utci_yearly_min": "degC"}

    np.testing.assert_allclose(result.cubes["utci_yearly_max"][:, 1, 1], [31, 32, 30])

    assert all(values.shape == (3, 4, 4) for values in result.cubes.values())
    assert all(np.isnan(values[:, 0, 0]).all() for values in result.cubes.values())


def test_empty_directory_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_yearly_statistics(
            tmp_path, start_year=2016, end_year=2017, require_complete_period=True
        )


def test_no_records_in_period_raises_value_error(netcdf_factory, tmp_path):
    netcdf_factory("old.nc", years=(2015,))
    with pytest.raises(ValueError):
        load_yearly_statistics(
            tmp_path, start_year=2016, end_year=2017, require_complete_period=True
        )


def test_duplicate_years_raised_error(netcdf_factory, tmp_path):
    netcdf_factory("a.nc", years=(2016,))
    netcdf_factory("b.nc", years=(2016,))

    with pytest.raises(ValueError):
        load_yearly_statistics(
            tmp_path, start_year=2016, end_year=2016, require_complete_period=True
        )


@pytest.mark.parametrize("complete", [True, False])
def test_missing_year_policy(netcdf_factory, tmp_path, complete):
    """
    Check how the loader handles a missing year in the selected period.

    Provide records for 2016 and 2018, leaving 2017 missing. Expect a
    ValueError when a complete period is required; otherwise, expect
    a dataset containing only the available years, 2016 and 2018.
    """
    netcdf_factory("partial.nc", years=(2016, 2018))

    if complete:
        with pytest.raises(ValueError):
            load_yearly_statistics(
                tmp_path, start_year=2016, end_year=2018, require_complete_period=complete
            )

    else:
        result = load_yearly_statistics(
            tmp_path, start_year=2016, end_year=2018, require_complete_period=complete
        )
        np.testing.assert_array_equal(result.years, [2016, 2018])


@pytest.mark.parametrize("options", [{"west": -23}, {"units": "K"}])
def test_inconsistent_files_are_rejected(netcdf_factory, tmp_path, options):
    """
    Check that files with incompatible grids or peak units are rejected.

    Create a reference file for 2016 and a second file for 2017 with either
    a shifted western grid boundary or Kelvin peak units instead of Celsius.
    Expect a ValueError rather than combining inconsistent yearly records.
    """
    netcdf_factory("a.nc", years=(2016,))
    netcdf_factory("b.nc", years=(2017,), **options)

    with pytest.raises(ValueError):
        load_yearly_statistics(
            tmp_path, start_year=2016, end_year=2017, require_complete_period=True
        )
