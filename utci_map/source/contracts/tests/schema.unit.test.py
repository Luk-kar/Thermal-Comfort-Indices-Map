"""
Pin the current behavior of the private schema helpers as a guard during refactors.

These tests reach into private internals and are not a behavior contract; the
public contract lives in test_schema.py. Rewrite them freely when the internals
change on purpose.
"""

import pytest

from utci_map.source.contracts.schema import INF, _side


def test_float_edges_give_the_same_field_names_as_integer_edges() -> None:
    side = _side("heat", "daily_max", ((26.0, 32.0), (32.0, INF)), "above")

    assert side.fields == ("utci_days_above_26_daily_max", "utci_days_above_32_daily_max")


def test_below_total_band_uses_the_last_upper_edge() -> None:
    side = _side("cold", "daily_min", ((-INF, -40), (-40, 9)), "below")

    assert side.total_band == "days_daily_min_below_9_total"


def test_invalid_brackets_are_rejected_when_the_side_is_built() -> None:
    with pytest.raises(ValueError, match="not contiguous"):
        _side("heat", "daily_max", ((26, 32), (34, INF)), "above")
