import numpy as np
import pytest

pytest.importorskip("rasterio")
from rasterio.transform import from_origin
from utci_map.source.loading.netcdf_reader import read_yearly_file


def test_reads_years_fields_values_units_and_grid(netcdf_factory):
    """
    Check that a NetCDF file is read into the expected yearly records.

    Create a file for 2016–2017 and verify that the returned records contain
    all selected UTCI fields, their expected yearly values, and peak units
    in Celsius. Check the 4 x 4 grid shape and geographic transform, and
    confirm that missing pixels are represented as NaN.
    """

    path = netcdf_factory("yearly.nc")
    result = read_yearly_file(path)

    assert result is not None
    assert result.years == [2016, 2017]
    assert result.shape == (4, 4)
    np.testing.assert_allclose(tuple(result.transform), tuple(from_origin(-24, 67, 0.25, 0.25)))
    assert result.peak_units == {"utci_yearly_max": "degC", "utci_yearly_min": "degC"}

    expected = {"utci_yearly_max": 30, "utci_yearly_min": -20,
                "utci_days_above_26_daily_max": 10, "utci_days_above_32_daily_max": 6,
                "utci_days_above_38_daily_max": 3, "utci_days_above_46_daily_max": 1,
                "utci_days_below_-40_daily_min": 1, "utci_days_below_-27_daily_min": 3,
                "utci_days_below_-13_daily_min": 6, "utci_days_below_0_daily_min": 10,
                "utci_days_below_9_daily_min": 15}
    assert set(result.arrays) == set(expected)

    for name, base in expected.items():
        assert len(result.arrays[name]) == 2
        for index, values in enumerate(result.arrays[name]):
            wanted = np.full((4, 4), float(base + index))
            wanted[0, 0] = np.nan
            np.testing.assert_allclose(values, wanted, equal_nan=True)


def test_reads_yearly_extremes_in_physical_units(netcdf_factory):

    path = netcdf_factory("packed.nc", peak_scale=0.5, peak_offset=200, units="K")
    result = read_yearly_file(path)

    assert result.arrays["utci_yearly_max"][0][1, 1] == 215
    assert result.arrays["utci_yearly_min"][0][1, 1] == 190
    assert np.isnan(result.arrays["utci_yearly_max"][0][0, 0])


def test_file_without_yearly_extremes_fields_is_not_yearly_statistics(netcdf_factory):

    path = netcdf_factory("other.nc", missing=("utci_yearly_max", "utci_yearly_min"))
    assert read_yearly_file(path) is None


def test_missing_selected_field_raises_key_error(netcdf_factory):

    path = netcdf_factory("incomplete.nc", missing=("utci_days_above_26_daily_max",))
    with pytest.raises(KeyError):
        read_yearly_file(path)


@pytest.mark.parametrize("options", [{"calendar": "360_day"}, {"peak_scale": -1}])
def test_unsupported_input_raises_value_error(netcdf_factory, options):

    path = netcdf_factory("invalid.nc", **options)
    with pytest.raises(ValueError):
        read_yearly_file(path)
