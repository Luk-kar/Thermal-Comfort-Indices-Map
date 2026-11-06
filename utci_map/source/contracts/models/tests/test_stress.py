"""Check that StressSide accepts consistent sides and rejects inconsistent ones early."""

import dataclasses

import pytest

from utci_map.source.contracts.models import StressSide


def make_side(**overrides: object) -> StressSide:
    """Build a valid two-bracket heat side, replacing the given fields."""
    values: dict[str, object] = {
        "name": "heat",
        "statistic": "daily_max",
        "direction": "above",
        "brackets": ((26, 32), (32, float("inf"))),
        "fields": ("utci_days_above_26_daily_max", "utci_days_above_32_daily_max"),
        "band_names": ("days_daily_max_26_32", "days_daily_max_32_inf"),
        "total_band": "days_daily_max_above_26_total",
    }
    values.update(overrides)

    return StressSide(**values)  # type: ignore[arg-type]


def test_consistent_side_is_accepted() -> None:
    side = make_side()

    assert side.name == "heat"
    assert len(side.fields) == len(side.brackets) == len(side.band_names)


def test_unknown_direction_is_rejected() -> None:
    with pytest.raises(ValueError, match="direction must be 'above' or 'below'.*'sideways'"):
        make_side(direction="sideways")


@pytest.mark.parametrize("field_name", ["fields", "band_names"])
def test_mismatched_name_count_is_rejected_with_counts(field_name: str) -> None:
    with pytest.raises(ValueError, match="heat side needs one field and one band name"):
        make_side(**{field_name: ("only_one",)})


def test_side_is_hashable_and_usable_as_dictionary_key() -> None:
    side = make_side()

    lookup = {side: "heat counts"}

    assert lookup[make_side()] == "heat counts"


def test_side_is_immutable() -> None:
    side = make_side()

    with pytest.raises(dataclasses.FrozenInstanceError):
        side.name = "cold"  # type: ignore[misc]
