"""Run from the project root with: python -m utci_map."""

from zipfile import ZipFile

from thermal_dataset_download import (
    OUTPUT_DIR as DOWNLOAD_DIR,
    EuropeBounds,
    build_target,
    get_download_regions,
)

from utci_map.source import config
from utci_map.source.computation.thermal_stress_summary import build_bands
from utci_map.source.loading.combine_yearly_utci_statistics import (
    load_yearly_statistics,
)
from utci_map.source.products.geotiff import write_geotiff
from utci_map.source.products.maps.png_maps import (
    MapOutput,
    RenderOptions,
    render_pngs,
)


def main():

    for region_name, _bounds in get_download_regions(EuropeBounds):
        
        region_dir = region_name.lower()
        data_dir = config.DATA_DIR / region_dir
        output_dir = config.OUTPUT_DIR / region_dir

        archive_path = build_target(
            DOWNLOAD_DIR,
            region_name,
            config.START_YEAR,
            config.END_YEAR,
        )

        print(f"Processing {region_name}: {archive_path} -> {output_dir}")

        extract_region(archive_path, data_dir)
        annual = load_data(data_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        tif_path = output_dir / config.TIF_PATH.name
        create_tif(annual, tif_path)
        create_pngs_with_sidecars(tif_path, output_dir)


def extract_region(archive_path, data_dir):

    if not archive_path.is_file():
        raise FileNotFoundError(f"Missing region archive: {archive_path}")

    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"Extracting {archive_path} -> {data_dir}")

    with ZipFile(archive_path) as archive:
        archive.extractall(data_dir)


def load_data(data_dir):
    annual = load_yearly_statistics(
        data_dir,
        config.START_YEAR,
        config.END_YEAR,
        config.REQUIRE_COMPLETE_PERIOD,
    )

    print(f"Years used ({annual.years.size}): {annual.years.tolist()}")
    print(f"Grid: {annual.shape[0]} x {annual.shape[1]} pixels")

    return annual


def create_tif(annual, tif_path):
    bands = build_bands(annual)

    write_geotiff(
        tif_path,
        bands,
        annual.transform,
        config.START_YEAR,
        config.END_YEAR,
    )

    print(f"Wrote {tif_path} ({len(bands)} bands)")


def create_pngs_with_sidecars(tif_path, output_dir):
    cold_png_path = output_dir / config.COLD_PNG_PATH.name
    cold_json_path = output_dir / config.COLD_JSON_PATH.name
    heat_png_path = output_dir / config.HEAT_PNG_PATH.name
    heat_json_path = output_dir / config.HEAT_JSON_PATH.name

    render_pngs(
        tif_path,
        cold=MapOutput(
            png_path=cold_png_path,
            json_path=cold_json_path,
            colors=tuple(config.COLD_COLORS),
        ),
        heat=MapOutput(
            png_path=heat_png_path,
            json_path=heat_json_path,
            colors=tuple(config.HEAT_COLORS),
        ),
        options=RenderOptions(
            png_scale=config.PNG_SCALE,
            discrete_colors=config.DISCRETE_COLORS,
        ),
    )

    print(
        f"Wrote {cold_png_path} + {cold_json_path} "
        f"and {heat_png_path} + {heat_json_path}"
    )


if __name__ == "__main__":
    main()