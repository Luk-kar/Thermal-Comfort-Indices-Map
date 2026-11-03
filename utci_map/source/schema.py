"""
Define UTCI fields, stress categories, thresholds and band naming rules.

These names are shared by the NetCDF loader, the summary GeoTIFF and the cold- and
heat-day PNG maps. Field and band names are derived from the brackets, so changing
a bracket renames them everywhere.
"""

INF = float("inf")

Bracket = tuple[float, float]  # (lower, upper) UTCI bound in °C

PEAK_MAX = "utci_yearly_max"
PEAK_MIN = "utci_yearly_min"

HEAT_BAND_PREFIX = "days_daily_max"
COLD_BAND_PREFIX = "days_daily_min"

# Heat stress is counted from the daily maximum UTCI; the last bracket is open-ended.
MAX_BRACKETS: tuple[Bracket, ...] = ((26, 32), (32, 38), (38, 46), (46, INF))
# Cold stress is counted from the daily minimum UTCI; the first bracket is open-ended.
MIN_BRACKETS: tuple[Bracket, ...] = ((-INF, -40), (-40, -27), (-27, -13), (-13, 0), (0, 9))


def _format_bound(value: float) -> str:
    """Format a bracket bound for names and messages, e.g. 26.0 -> '26', -inf -> '-inf'."""
    if value == INF:
        return "inf"

    if value == -INF:
        return "-inf"

    return f"{value:g}"


def _above_thresholds(brackets: tuple[Bracket, ...]) -> tuple[float, ...]:
    """
    Return the lower edge of every bracket, matching cumulative 'days above' counts.

    E.g. ((26, 32), (32, inf)) -> (26, 32). The last bracket must be open-ended.
    """
    _check_contiguous(brackets)

    lower, upper = brackets[-1]
    if upper != INF:
        raise ValueError(
            "The last 'above' bracket must be open-ended (upper bound inf), "
            f"but it is {_format_bound(lower)} to {_format_bound(upper)}"
        )

    return tuple(lower for lower, _ in brackets)


def _below_thresholds(brackets: tuple[Bracket, ...]) -> tuple[float, ...]:
    """
    Return the upper edge of every bracket, matching cumulative 'days below' counts.

    E.g. ((-inf, -40), (-40, -27)) -> (-40, -27). The first bracket must be open-ended.
    """
    _check_contiguous(brackets)

    lower, upper = brackets[0]
    if lower != -INF:
        raise ValueError(
            "The first 'below' bracket must be open-ended (lower bound -inf), "
            f"but it is {_format_bound(lower)} to {_format_bound(upper)}"
        )

    return tuple(upper for _, upper in brackets)


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


ABOVE_THRESHOLDS = _above_thresholds(MAX_BRACKETS)  # (26, 32, 38, 46)
BELOW_THRESHOLDS = _below_thresholds(MIN_BRACKETS)  # (-40, -27, -13, 0, 9)

MAX_BAND_NAMES = _band_names(HEAT_BAND_PREFIX, MAX_BRACKETS)  # e.g. "days_daily_max_26_32"
MIN_BAND_NAMES = _band_names(COLD_BAND_PREFIX, MIN_BRACKETS)  # e.g. "days_daily_min_0_9"

# Days in any heat or cold category, e.g. "days_daily_max_above_26_total".
HEAT_TOTAL_BAND = f"{HEAT_BAND_PREFIX}_above_{_format_bound(ABOVE_THRESHOLDS[0])}_total"
COLD_TOTAL_BAND = f"{COLD_BAND_PREFIX}_below_{_format_bound(BELOW_THRESHOLDS[-1])}_total"

# The NetCDF variables to read: yearly peaks plus one cumulative day count per threshold.
SELECTED_NETCDF_FIELDS = (
    PEAK_MAX,
    PEAK_MIN,
    *(f"utci_days_above_{t}_daily_max" for t in ABOVE_THRESHOLDS),
    *(f"utci_days_below_{t}_daily_min" for t in BELOW_THRESHOLDS),
)
