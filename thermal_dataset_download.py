from pathlib import Path
from typing import Tuple

import cdsapi

Bounds = Tuple[float, float, float, float]  # (west, south, east, north), lon/lat WGS84

class EuropeBounds:
    """
    Europe-wide extents (lon/lat, WGS84) as (west, south, east, north).
    Pick the one you need by attribute: EuropeBounds.MAINLAND,
    EuropeBounds.CANARY, EuropeBounds.ENVELOPE, and so on.

    Europe is described as several boxes because a single rectangle that
    reaches the Canary Islands (~27.6 deg N) and Svalbard (~81 deg N) would
    also take in a large band of North Africa (Morocco, Algeria, Tunisia,
    Libya, Egypt) and a lot of empty Arctic and Atlantic ocean, none of
    which is in scope for this pipeline. Each box is sized to contain every
    EU/EEA/UK/candidate-country NUTS (or NUTS-equivalent) territory in its
    area, with a small margin:

      MAINLAND  (-11.0, 34.5, 46.0, 71.5)

        Continental Europe plus the peripheral territories that lie near it:

          west  (-11.0): west of Ireland (Blasket Islands, -10.7 deg W) plus margin
          south ( 34.5): south of Cyprus (Akrotiri, ~34.6 deg N), Crete
                         and Gavdos (~34.8 deg N), and the Spanish
                         exclaves Ceuta / Melilla (~35.3-35.9 deg N)
          east  ( 46.0): east of Turkey's easternmost NUTS-equivalent
                         province, Igdir (tripoint w/ Azerbaijan & Iran,
                         ~44.82 deg E) plus margin, and east of Cyprus /
                         the Balkans
          north ( 71.5): north of mainland Norway (Nordkapp, ~71.17 deg N)
                         and Jan Mayen (~71.0-71.16 deg N)

      ICELAND   (-26.0, 62.0, -12.0, 67.8)

        Iceland incl. Grimsey (~66.56 deg N) and the Vestmannaeyjar
        (~63.3 deg N).

          west  (-26.0): west of Bjargtangar (~-24.5 deg W) plus margin
          south ( 62.0): south of the Vestmannaeyjar plus margin
          east  (-12.0): east of Gerpir (~-13.5 deg W) plus margin; the
                         strip east of -13.0 is open sea and overlaps
                         MAINLAND's west edge (-11.0) by 1 deg of sea only
          north ( 67.8): north of Grimsey plus margin

      SVALBARD  (9.5, 73.9, 34.5, 81.0)

        Svalbard (~74-81 deg N). Jan Mayen and Svalbard share one combined
        NUTS region (NO0B), which cannot be split by nuts_id: Jan Mayen is
        covered by MAINLAND and Svalbard by this box, so NO0B is kept
        whole when clipping to the union of REGIONS.

          west  ( 9.5): west of Prins Karls Forland (~10.4 deg E)
          south (73.9): south of Bjornoya (~74.35-74.52 deg N)
          east  (34.5): east of Kvitoya (~33.5 deg E)
          north (81.0): north of Rossoya (~80.83 deg N)

      AZORES    (-32.6, 35.8, -23.9, 40.9)

        Corvo (~-31.3 deg W) to Santa Maria (~-25.0 deg W, ~36.9 deg N),
        Flores / Corvo (~39.7 deg N), each plus ~1 deg margin.

      MADEIRA   (-18.4, 29.0, -14.8, 34.3)

        Madeira and Porto Santo (~32.4-33.1 deg N, ~-17.3 to -16.3 deg W).
        The south edge also contains the Selvagens Islands (~30.0-30.2 deg N,
        ~-15.86 deg W), which belong to the same NUTS region; the east
        edge keeps them clear of the box boundary. The south margin overlaps
        CANARY's north edge (30.0) by 1 deg of open sea only.

      CANARY    (-19.5, 26.4, -12.0, 30.0)

        El Hierro (~27.6 deg N, ~-18.2 deg W) to Lanzarote / La Graciosa
        and the northern islets (~29.3-29.5 deg N, ~-13.3 deg W), plus margin.
        The widened south and east edges take in more of the Moroccan /
        Western Saharan coast (Cape Juby, ~-12.9 deg W); that land is out of
        scope and is only the unavoidable cost of a rectangular box.

      ENVELOPE  (-32.6, 26.4, 46.0, 81.0)

        The smallest single box containing all of the above.
          west  (-32.6): from AZORES
          south ( 26.4): from CANARY
          east  ( 46.0): from MAINLAND (see Igdir above)
          north ( 81.0): from SVALBARD (see Rossoya above)
    """

    MAINLAND: Bounds = (-11.0, 34.5, 46.0, 71.5)

    ICELAND: Bounds = (-26.0, 62.0, -12.0, 67.8)
    SVALBARD: Bounds = (9.5, 73.9, 34.5, 81.0)
    AZORES: Bounds = (-32.6, 35.8, -23.9, 40.9)

    # Madeira, Porto Santo and the Desertas (~32.4-33.1 deg N, ~-17.3 to -16.3 deg W)
    MADEIRA: Bounds = (-17.8, 31.9, -15.9, 33.6)

    # Selvagens Islands (~30.0-30.2 deg N, ~-16.0 to -15.9 deg W). Same NUTS region as
    # MADEIRA (PT30), but ~2.5 deg south of it; a separate box avoids downloading the
    # empty ocean in between.
    SELVAGENS: Bounds = (-16.6, 29.5, -15.2, 30.6)

    # El Hierro, La Palma, La Gomera, Tenerife, Gran Canaria (~-18.2 to -15.4 deg W)
    CANARY_WEST: Bounds = (-19.3, 26.8, -14.6, 29.7)

    # Fuerteventura, Lanzarote, La Graciosa (~-14.5 to -13.3 deg W). East edge -13.1
    # and south edge 27.8 stay clear of the Moroccan coast at Cape Juby / Tarfaya
    # (~-12.9 deg W, ~27.9 deg N).
    CANARY_EAST: Bounds = (-14.9, 27.8, -13.1, 30.0)

    REGIONS: Tuple[Bounds, ...] = (
        MAINLAND, ICELAND, SVALBARD, AZORES, MADEIRA, SELVAGENS, CANARY_WEST, CANARY_EAST,
    )

    ENVELOPE: Bounds = (
        min(b[0] for b in REGIONS),
        min(b[1] for b in REGIONS),
        max(b[2] for b in REGIONS),
        max(b[3] for b in REGIONS),
    )

NUMBER_OF_YEARS = 10
END_YEAR = 2025
START_YEAR = END_YEAR - NUMBER_OF_YEARS + 1

YEARS = [str(year) for year in range(START_YEAR, END_YEAR + 1)]

DATASET = "derived-utci-historical"
OUTPUT_DIR = Path("downloads")

client = cdsapi.Client()

def get_download_regions(bounds_class):
    return [
        (name, bounds)
        for name, bounds in vars(bounds_class).items()
        if name not in {"REGIONS", "ENVELOPE"}
        and bounds in bounds_class.REGIONS
    ]


def build_request(bounds, years):
    west, south, east, north = bounds

    return {
        "variable": [
            "universal_thermal_climate_index_yearly_statistics"
        ],
        "version": "1_1",
        "product_type": "consolidated_dataset",
        "year": list(years),
        # Convert (west, south, east, north) to CDS area ordering.
        "area": [north, west, south, east],
    }


def build_target(output_dir, name, start_year, end_year):
    return Path(output_dir) / (
        f"utci_{name.lower()}_{start_year}_{end_year}.zip"
    )


def download_regions(
    client,
    dataset,
    regions,
    output_dir,
    start_year,
    end_year,
    log=print,
):
    regions = list(regions)
    years = [str(year) for year in range(start_year, end_year + 1)]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    targets = []

    for index, (name, bounds) in enumerate(regions, start=1):
        request = build_request(bounds, years)
        target = build_target(output_dir, name, start_year, end_year)

        log(
            f"Downloading {name} ({index}/{len(regions)}): "
            f"bounds={bounds} -> {target}",
            flush=True,
        )

        client.retrieve(dataset, request, str(target))

        log(f"Downloaded {name} -> {target}", flush=True)
        targets.append(target)

    return targets

if __name__ == "__main__":
    import cdsapi

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    download_regions(
        client=cdsapi.Client(),
        dataset=DATASET,
        regions=get_download_regions(EuropeBounds),
        output_dir=OUTPUT_DIR,
        start_year=START_YEAR,
        end_year=END_YEAR,
    )