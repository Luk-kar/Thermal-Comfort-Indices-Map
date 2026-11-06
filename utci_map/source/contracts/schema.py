"""
Define UTCI fields, stress categories, thresholds and band naming rules.

These names are shared by the NetCDF loader, the summary GeoTIFF and the cold- and
heat-day PNG maps. Field and band names are derived from the brackets, so changing
a bracket renames them everywhere.
"""

from utci_map.source.contracts.models import Bracket, Direction, StressSide

INF = float("inf")

PEAK_MAX = "utci_yearly_max"
PEAK_MIN = "utci_yearly_min"

# Heat stress is counted from the daily maximum UTCI; the last bracket is open-ended.
MAX_BRACKETS: tuple[Bracket, ...] = ((26, 32), (32, 38), (38, 46), (46, INF))
# Cold stress is counted from the daily minimum UTCI; the first bracket is open-ended.
MIN_BRACKETS: tuple[Bracket, ...] = ((-INF, -40), (-40, -27), (-27, -13), (-13, 0), (0, 9))

_OPEN_LAST = "The last 'above' bracket must be open-ended (upper bound inf)"
_OPEN_FIRST = "The first 'below' bracket must be open-ended (lower bound -inf)"


def _side(
    name: str, statistic: str, brackets: tuple[Bracket, ...], direction: Direction
) -> StressSide:
    """
    Derive the field and band names of one stress side from its brackets.

    E.g. statistic "daily_max", direction "above" and bracket (26, 32) give the field
    "utci_days_above_26_daily_max", the band "days_daily_max_26_32" and the total band
    "days_daily_max_above_26_total". Thresholds keep their str() form, as in the CDS names.
    """
    thresholds = _thresholds(brackets, direction)
    prefix = f"days_{statistic}"
    # The total counts every day past the mildest threshold.
    mildest = thresholds[0] if direction == "above" else thresholds[-1]

    return StressSide(
        name=name,
        direction=direction,
        brackets=brackets,
        fields=tuple(f"utci_days_{direction}_{threshold}_{statistic}" for threshold in thresholds),
        band_names=_band_names(prefix, brackets),
        total_band=f"{prefix}_{direction}_{_format_bound(mildest)}_total",
    )


def _thresholds(brackets: tuple[Bracket, ...], direction: Direction) -> tuple[float, ...]:
    """
    Return the bracket edges that match the cumulative CDS day counts.

    'above' counts use the lower edge of every bracket and need an open-ended last
    bracket, e.g. ((26, 32), (32, inf)) -> (26, 32). 'below' counts use the upper edge
    and need an open-ended first bracket, e.g. ((-inf, -40), (-40, -27)) -> (-40, -27).
    """
    _check_contiguous(brackets)

    if direction == "above":
        _check_open_ended(brackets[-1], is_open=brackets[-1][1] == INF, rule=_OPEN_LAST)
        return tuple(lower for lower, _ in brackets)
    if direction == "below":
        _check_open_ended(brackets[0], is_open=brackets[0][0] == -INF, rule=_OPEN_FIRST)
        return tuple(upper for _, upper in brackets)
    raise ValueError(f"direction must be 'above' or 'below', got {direction!r}")


def _check_open_ended(bracket: Bracket, *, is_open: bool, rule: str) -> None:
    """Reject a closed outermost bracket, which the cumulative counts can't describe."""
    if not is_open:
        lower, upper = bracket
        raise ValueError(f"{rule}, but it is {_format_bound(lower)} to {_format_bound(upper)}")


def _format_bound(value: float) -> str:
    """Format a bracket bound for names and messages, e.g. 26.0 -> '26', -inf -> '-inf'."""
    if value == INF:
        return "inf"

    if value == -INF:
        return "-inf"

    return f"{value:g}"


def _check_contiguous(brackets: tuple[Bracket, ...]) -> None:
    """Reject brackets with gaps or overlaps between neighbors."""
    for (_, upper), (lower, _) in zip(brackets, brackets[1:]):
        if upper != lower:
            raise ValueError(f"Brackets are not contiguous: {upper} != {lower}")


def _band_names(prefix: str, brackets: tuple[Bracket, ...]) -> tuple[str, ...]:
    """
    Build one band name per bracket.

    E.g. prefix "days_daily_max" and bracket (26, 32) -> "days_daily_max_26_32".
    """
    return tuple(
        f"{prefix}_{_format_bound(lower)}_{_format_bound(upper)}" for lower, upper in brackets
    )


# E.g. HEAT_SIDE.band_names[0] == "days_daily_max_26_32" and
# COLD_SIDE.total_band == "days_daily_min_below_9_total".
HEAT_SIDE = _side("heat", "daily_max", MAX_BRACKETS, "above")
COLD_SIDE = _side("cold", "daily_min", MIN_BRACKETS, "below")

# The NetCDF variables to read: yearly peaks plus the cumulative day counts.
SELECTED_NETCDF_FIELDS = (PEAK_MAX, PEAK_MIN, *HEAT_SIDE.fields, *COLD_SIDE.fields)
