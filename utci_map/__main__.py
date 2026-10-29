"""Run from the project root with: python -m utci_map."""

from .source import config
from .source.computation.thermal_stress_summary import build_bands
from .source.products.geotiff import write_geotiff
from .source.products.maps.png_maps import render_pngs
from .source.loading.combine_yearly_utci_statistics import load_yearly_statistics


def main():
    yearly_statistics_maps = load_data()
    create_tif(yearly_statistics_maps)
    create_pngs_with_sidecars()

def load_data():
    annual = load_yearly_statistics(
        config.DATA_DIR,
        config.START_YEAR,
        config.END_YEAR,
        config.REQUIRE_COMPLETE_PERIOD,
    )

    print(f"Years used ({annual.years.size}): {annual.years.tolist()}")
    print(f"Grid: {annual.shape[0]} x {annual.shape[1]} pixels")

    return annual


def create_tif(annual):
    bands = build_bands(annual)

    write_geotiff(
        config.TIF_PATH,
        bands,
        annual.transform,
        config.START_YEAR,
        config.END_YEAR,
    )

    print(f"Wrote {config.TIF_PATH} ({len(bands)} bands)")


def create_pngs_with_sidecars():
    render_pngs(
        config.TIF_PATH,
        config.COLD_PNG_PATH,
        config.COLD_JSON_PATH,
        config.HEAT_PNG_PATH,
        config.HEAT_JSON_PATH,
        config.COLD_COLORS,
        config.HEAT_COLORS,
        config.PNG_SCALE,
        config.DISCRETE_COLORS,
    )

    print(
        f"Wrote {config.COLD_PNG_PATH} + {config.COLD_JSON_PATH} "
        f"and {config.HEAT_PNG_PATH} + {config.HEAT_JSON_PATH}"
    )


if __name__ == "__main__":
    main()