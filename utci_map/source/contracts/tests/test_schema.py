"""Check the field and band names the schema derives for the heat and cold sides."""

from utci_map.source.contracts import COLD_SIDE, HEAT_SIDE, SELECTED_NETCDF_FIELDS


def test_heat_side_names_follow_lower_edges() -> None:
    assert HEAT_SIDE.direction == "above"
    assert HEAT_SIDE.fields == (
        "utci_days_above_26_daily_max",
        "utci_days_above_32_daily_max",
        "utci_days_above_38_daily_max",
        "utci_days_above_46_daily_max",
    )
    assert HEAT_SIDE.band_names[0] == "days_daily_max_26_32"
    assert HEAT_SIDE.band_names[-1] == "days_daily_max_46_inf"


def test_cold_side_names_follow_upper_edges() -> None:
    assert COLD_SIDE.direction == "below"
    assert COLD_SIDE.fields == (
        "utci_days_below_-40_daily_min",
        "utci_days_below_-27_daily_min",
        "utci_days_below_-13_daily_min",
        "utci_days_below_0_daily_min",
        "utci_days_below_9_daily_min",
    )
    assert COLD_SIDE.band_names[0] == "days_daily_min_-inf_-40"
    assert COLD_SIDE.band_names[-1] == "days_daily_min_0_9"


def test_total_band_uses_the_mildest_threshold() -> None:
    assert HEAT_SIDE.total_band == "days_daily_max_above_26_total"
    assert COLD_SIDE.total_band == "days_daily_min_below_9_total"


def test_selected_netcdf_fields_cover_peaks_and_both_sides() -> None:
    assert SELECTED_NETCDF_FIELDS[:2] == ("utci_yearly_max", "utci_yearly_min")
    assert set(HEAT_SIDE.fields + COLD_SIDE.fields) <= set(SELECTED_NETCDF_FIELDS)
    assert len(SELECTED_NETCDF_FIELDS) == 2 + len(HEAT_SIDE.fields) + len(COLD_SIDE.fields)
