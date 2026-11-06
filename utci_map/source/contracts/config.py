"""Run settings, paths and map styling; paths are relative to the working directory."""

from pathlib import Path

from utci_map.source.contracts.models import MapKind
from utci_map.source.contracts.schema import COLD_SIDE, HEAT_SIDE

DATA_DIR = Path("downloads")


# Inclusive period; must match the years in thermal_dataset_download.py.
START_YEAR = 2016
END_YEAR = 2025
REQUIRE_COMPLETE_PERIOD = True  # False = warn about missing years instead of failing


OUTPUT_DIR = Path("output") / "map"


TIF_PATH = OUTPUT_DIR / "utci_summary.tif"


COASTLINE_PATH = Path("gisco") / "COAS_RG_10M_2016_4326.geojson"

# Each run logs to its own file, e.g. logs/utci_map/2026-11-03_17-42-05.log.
LOGGER_NAME = "utci_map"
LOG_DIR = Path("logs") / "utci_map"
LOG_FILE_TIME_FORMAT = "%Y-%m-%d_%H-%M-%S"

# I/O beyond these limits is logged as a WARNING.
LARGE_IO_WARNING_BYTES = 500 * 1024**2  # one file, or everything extracted from one archive
EXTRACTED_FILES_WARNING_COUNT = 200  # files extracted from one region archive
SLOW_IO_WARNING_SECONDS = 60.0  # one read, write or extraction


COLD_COLORS = (
    "#daccc9",  # pale warm gray (light taupe) - fewest days; shared start color
    "#b8d4c8",  # pale sage green / light seafoam
    "#72b6b5",  # muted teal (soft aqua)
    "#4792b1",  # steel blue
    "#0f588f",  # deep azure blue
    "#042b48",  # very dark navy - most days
)

HEAT_COLORS = (
    "#daccc9",  # pale warm gray (light taupe) - fewest days; shared start color
    "#fdbe9d",  # light peach (pale apricot)
    "#ef8a82",  # salmon / coral pink
    "#c8596c",  # dusty rose (raspberry)
    "#993233",  # dark brick red (burgundy) - most days
)

# Rendered maps, in log and render order; file stems must match frontend/config.js.
COLD_MAP = MapKind(
    name="cold", total_band=COLD_SIDE.total_band, file_stem="utci_cold_days", colors=COLD_COLORS
)
HEAT_MAP = MapKind(
    name="heat", total_band=HEAT_SIDE.total_band, file_stem="utci_heat_days", colors=HEAT_COLORS
)
MAP_KINDS = (COLD_MAP, HEAT_MAP)

DISCRETE_COLORS = False  # True = use only the palette steps, no blending
PNG_SCALE = 1  # 1 = native size; >1 enlarges with nearest neighbor (coordinates are unaffected)

MAX_INDEX = 254  # palette indices 0..254 hold data
NODATA_INDEX = 255  # transparent palette index for missing pixels
COLOR_MAP_STEP = 17  # spacing of the entries listed in the sidecar's "color_map"
