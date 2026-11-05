"""Run from the project root with: python -m utci_map."""

import logging
import time
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

from thermal_dataset_download import OUTPUT_DIR as DOWNLOAD_DIR
from thermal_dataset_download import EuropeBounds, build_target, get_download_regions
from utci_map.source.computation import build_bands
from utci_map.source.contracts import (
    COLD_COLORS,
    COLD_JSON_PATH,
    COLD_PNG_PATH,
    DATA_DIR,
    DISCRETE_COLORS,
    END_YEAR,
    EXTRACTED_FILES_WARNING_COUNT,
    HEAT_COLORS,
    HEAT_JSON_PATH,
    HEAT_PNG_PATH,
    LOG_DIR,
    LOG_FILE_TIME_FORMAT,
    LOGGER_NAME,
    OUTPUT_DIR,
    PNG_SCALE,
    REQUIRE_COMPLETE_PERIOD,
    START_YEAR,
    TIF_PATH,
    YearlyStats,
)
from utci_map.source.loading import load_yearly_statistics
from utci_map.source.products import (
    MapOutput,
    RenderOptions,
    ValueRange,
    global_value_ranges,
    render_pngs,
    write_geotiff,
)
from utci_map.source.runlog import configure_logging, format_size, logged_file_io, warn_if_large

_LOGGER = logging.getLogger(LOGGER_NAME)


def main() -> None:
    """Build every region's GeoTIFF and maps, logging the run to a new file in LOG_DIR."""
    log_path = LOG_DIR / f"{datetime.now().strftime(LOG_FILE_TIME_FORMAT)}.log"
    configure_logging(log_path)
    _LOGGER.info("Started utci_map for %d-%d; logging to %s", START_YEAR, END_YEAR, log_path)
    start = time.perf_counter()

    try:
        _build_all_regions()
    except Exception:
        _LOGGER.exception("utci_map failed after %.1f s", time.perf_counter() - start)
        raise

    _LOGGER.info("Finished utci_map in %.1f s", time.perf_counter() - start)


def _build_all_regions() -> None:
    """Write each region's GeoTIFF, then render all PNGs on shared color scales."""
    tif_paths = []

    for region_name, _bounds in get_download_regions(EuropeBounds):
        region_dir = region_name.lower()
        data_dir = DATA_DIR / region_dir
        output_dir = OUTPUT_DIR / region_dir
        archive_path = build_target(DOWNLOAD_DIR, region_name, START_YEAR, END_YEAR)

        _LOGGER.info("Processing %s: %s -> %s", region_name, archive_path, output_dir)

        extract_region(archive_path, data_dir)
        annual = load_data(data_dir)

        output_dir.mkdir(parents=True, exist_ok=True)
        tif_path = output_dir / TIF_PATH.name
        create_tif(annual, tif_path)
        tif_paths.append(tif_path)

    options = RenderOptions(png_scale=PNG_SCALE, discrete_colors=DISCRETE_COLORS)
    cold_range, heat_range = global_value_ranges(tif_paths, options)

    _LOGGER.info("Global cold scale: %.1f to %.1f days", cold_range.vmin, cold_range.vmax)
    _LOGGER.info("Global heat scale: %.1f to %.1f days", heat_range.vmin, heat_range.vmax)

    for tif_path in tif_paths:
        create_pngs_with_sidecars(tif_path, tif_path.parent, (cold_range, heat_range), options)


def extract_region(archive_path: Path, data_dir: Path) -> None:
    """Unpack a region's ZIP archive into data_dir, logging how many files and bytes it held."""
    if not archive_path.is_file():
        raise FileNotFoundError(f"Missing region archive: {archive_path}")

    data_dir.mkdir(parents=True, exist_ok=True)

    with logged_file_io(_LOGGER, "Read", archive_path), ZipFile(archive_path) as archive:
        members = archive.infolist()
        archive.extractall(data_dir)

    extracted_bytes = sum(member.file_size for member in members)
    description = f"Extracted {archive_path} to {data_dir}"

    _LOGGER.info("%s: %d files, %s", description, len(members), format_size(extracted_bytes))
    warn_if_large(_LOGGER, description, extracted_bytes)

    if len(members) > EXTRACTED_FILES_WARNING_COUNT:
        _LOGGER.warning(
            "%s: %d files is over the %d limit",
            description,
            len(members),
            EXTRACTED_FILES_WARNING_COUNT,
        )


def load_data(data_dir: Path) -> YearlyStats:
    """Load the configured period from the extracted NetCDF files."""
    annual = load_yearly_statistics(
        data_dir,
        start_year=START_YEAR,
        end_year=END_YEAR,
        require_complete_period=REQUIRE_COMPLETE_PERIOD,
    )

    _LOGGER.info("Years used (%d): %s", annual.years.size, annual.years.tolist())
    _LOGGER.info("Grid: %d x %d pixels", annual.shape[0], annual.shape[1])

    return annual


def create_tif(annual: YearlyStats, tif_path: Path) -> None:
    """Compute the summary bands and write them to tif_path."""
    bands = build_bands(annual)

    _LOGGER.info("Built %d summary bands", len(bands))

    write_geotiff(
        tif_path,
        bands,
        annual.transform,
        start_year=START_YEAR,
        end_year=END_YEAR,
    )


def create_pngs_with_sidecars(
    tif_path: Path,
    output_dir: Path,
    value_ranges: tuple[ValueRange, ValueRange],
    options: RenderOptions,
) -> None:
    """Render the cold and heat PNGs and sidecars for one region on the shared scales."""
    render_pngs(
        tif_path,
        cold=MapOutput(
            png_path=output_dir / COLD_PNG_PATH.name,
            json_path=output_dir / COLD_JSON_PATH.name,
            colors=COLD_COLORS,
        ),
        heat=MapOutput(
            png_path=output_dir / HEAT_PNG_PATH.name,
            json_path=output_dir / HEAT_JSON_PATH.name,
            colors=HEAT_COLORS,
        ),
        options=options,
        value_ranges=value_ranges,
    )


if __name__ == "__main__":
    main()
