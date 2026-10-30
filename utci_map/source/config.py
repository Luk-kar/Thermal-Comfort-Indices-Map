"""Run settings, paths and map styling; paths are relative to the working directory."""

from pathlib import Path

DATA_DIR = Path("utci_iceland_sample")


START_YEAR = 2016


END_YEAR = 2025


REQUIRE_COMPLETE_PERIOD = True


OUTPUT_DIR = Path("output")


TIF_PATH = OUTPUT_DIR / "utci_summary.tif"

COLD_DAYS = "utci_cold_days"
HEAT_DAYS = "utci_heat_days"


COLD_PNG_PATH = OUTPUT_DIR / f"{COLD_DAYS}.png"


HEAT_PNG_PATH = OUTPUT_DIR / f"{HEAT_DAYS}.png"


COLD_JSON_PATH = OUTPUT_DIR / f"{COLD_DAYS}.json"


HEAT_JSON_PATH = OUTPUT_DIR / f"{HEAT_DAYS}.json"


COASTLINE_PATH = Path("gisco") / "COAS_RG_10M_2016_4326.geojson"


COLD_COLORS = [
    "#daccc9",  # pale warm grey (light taupe) - fewest days; shared start colour
    "#b8d4c8",  # pale sage green / light seafoam
    "#72b6b5",  # muted teal (soft aqua)
    "#4792b1",  # steel blue
    "#0f588f",  # deep azure blue
    "#042b48",  # very dark navy - most days
]


HEAT_COLORS = [
    "#daccc9",  # pale warm grey (light taupe) - fewest days; shared start colour
    "#fdbe9d",  # light peach (pale apricot)
    "#ef8a82",  # salmon / coral pink
    "#c8596c",  # dusty rose (raspberry)
    "#993233",  # dark brick red (burgundy) - most days
]


DISCRETE_COLORS = False  # True = use only the palette steps, no blending


PNG_SCALE = 1  # 1 = native size; >1 enlarges with nearest-neighbour (coordinates are unaffected)


MAX_INDEX = 254  # palette indices 0..254 hold data; 255 is nodata


NODATA_INDEX = 255


COLOR_MAP_STEP = 17  # spacing of the entries listed in the sidecar's "color_map"
