"""
Define UTCI fields, stress categories, thresholds, and band naming rules
for the summary GeoTIFF and the cold- and heat-day PNG maps with MapLibre
JSON sidecars.
"""

COLD_TOTAL_BAND = "days_daily_min_below_9_total"


HEAT_TOTAL_BAND = "days_daily_max_above_26_total"


PEAK_MAX = "utci_yearly_max"


PEAK_MIN = "utci_yearly_min"


INF = float("inf")


def format_bound(value: float) -> str:
    """
    Format a bracket bound for 
    band/variable names and messages
    """

    if value == INF:
        return "inf"

    if value == -INF:
        return "-inf"

    return f"{value:g}"


MAX_BRACKETS = [(26, 32), (32, 38), (38, 46), (46, INF)]


MIN_BRACKETS = [(-INF, -40), (-40, -27), (-27, -13), (-13, 0), (0, 9)]


def bracket_thresholds(brackets, threshold_direction):
    """
    Cumulative-count thresholds that the brackets are built from.

    "above": the lower edge of every bracket (the last one must be open-ended).
    "below": the upper edge of every bracket (the first one must be open-ended).
    """

    THRESHOLD_STATISTIC = {"above": "daily_max", "below": "daily_min"}

    if threshold_direction not in THRESHOLD_STATISTIC:
        raise ValueError(
            f"threshold_direction must be 'above' or 'below', got {threshold_direction!r}"
        )

    for (_, upper_bound), (lower_bound, _) in zip(brackets, brackets[1:]):
        if upper_bound != lower_bound:
            raise ValueError(f"Brackets are not contiguous: {upper_bound} != {lower_bound}")

    if threshold_direction == "above":

        if brackets[-1][1] != INF:
            raise ValueError(
                "The last 'above' bracket must be open-ended (upper bound inf), "
                f"but its upper bound is {format_bound(brackets[-1][1])} "
                f"(bracket: {format_bound(brackets[-1][0])} to {format_bound(brackets[-1][1])})"
            )
        return tuple(lower_bound for lower_bound, _ in brackets)

    if brackets[0][0] != -INF:

        raise ValueError(
            "The first 'below' bracket must be open-ended (lower bound -inf), "
            f"but its lower bound is {format_bound(brackets[0][0])} "
            f"(bracket: {format_bound(brackets[0][0])} to {format_bound(brackets[0][1])})"
        )

    return tuple(upper_bound for _, upper_bound in brackets)


ABOVE_THRESHOLDS = bracket_thresholds(MAX_BRACKETS, "above")  # (26, 32, 38, 46)


BELOW_THRESHOLDS = bracket_thresholds(MIN_BRACKETS, "below")  # (-40, -27, -13, 0, 9)


def build_band_names(prefix: str, brackets) -> list[str]:
    """
    Build one band name per bracket, 
    e.g. 'days_daily_max_26_32'.
    """

    return [
        f"{prefix}_{format_bound(lower_bound)}_{format_bound(upper_bound)}"
        for lower_bound, upper_bound in brackets
    ]


MAX_BAND_NAMES = build_band_names("days_daily_max", MAX_BRACKETS)


MIN_BAND_NAMES = build_band_names("days_daily_min", MIN_BRACKETS)


SELECTED_NETCDF_FIELDS = (
    [PEAK_MAX, PEAK_MIN]
    + [f"utci_days_above_{t}_daily_max" for t in ABOVE_THRESHOLDS]
    + [f"utci_days_below_{t}_daily_min" for t in BELOW_THRESHOLDS]
)
