# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Rules

- Ask the user before writing or running code that uses a Python file I/O library (`os`, `io`, `shutil`, `pathlib`), and always before removing files with one. `.claude/hooks/ask_on_file_io.sh` enforces this for code visible in a tool call, but not for code that a script runs from an existing file.

## What this is

Downloads yearly UTCI (Universal Thermal Climate Index) statistics for European regions from the Copernicus CDS, turns them into summary GeoTIFFs and cold/heat PNG maps, and serves them through a static MapLibre frontend. There is no backend and no frontend build step.

## Commands

Run everything from the project root, because paths in `utci_map/source/config.py` are relative to the working directory.

```sh
uv sync                                        # install dependencies
uv run python thermal_dataset_download.py      # download one ZIP per region into downloads/ (needs CDS credentials)
uv run python -m utci_map                      # build output/map/<region>/ from those ZIPs
uv run python thermal_dataset_preview.py       # standalone previews in output/preview/
uv run python -m http.server 8000              # then open http://localhost:8000/frontend/

uv run pytest                                  # all Python tests
uv run pytest path/to/test_file.py::test_name  # one Python test
node --experimental-default-type=module --test frontend/tests/modules.test.mjs   # frontend tests
node --experimental-default-type=module --test --test-name-pattern="explicit PNG bounds" frontend/tests/modules.test.mjs   # frontend tests matching a name

uv run ruff check path/to/file.py              # lint
uv run ruff format path/to/file.py             # format
uv run mypy                                    # type check
```

The HTTP server must serve the repository root, not `frontend/`, because the frontend fetches `../output/map/`.

Run Ruff and mypy after changing Python code. Their settings in `pyproject.toml` enforce most of `.claude/rules/python/style.md`. The existing code does not pass yet, so check the files you changed, and don't run `ruff format` or `ruff check --fix` on the whole repository unless asked. Ruff cannot check the function and file line limits exactly, so follow those by hand; `PLR0915` only approximates the function limit by counting statements.

`thermal_dataset_download.py` calls `cdsapi.Client()` at import time, so CDS credentials are needed by anything that imports it: `utci_map`, the preview script and the downloader tests.

## Pipeline

`utci_map/__main__.py` orchestrates the stages under `utci_map/source/`:

1. **Extract:** unpack `downloads/utci_<region>_<start>_<end>.zip` into `downloads/<region>/`.
2. **Load (`loading/`):** read the NetCDF fields listed in `schema.SELECTED_NETCDF_FIELDS`, then validate grid, units and year coverage across files. NetCDF files without the yearly peak fields are skipped.
3. **Compute (`computation/`):** build the summary bands.
4. **GeoTIFF (`products/geotiff.py`):** write `utci_summary.tif` in EPSG:4326, with band names as descriptions.
5. **Maps (`products/maps/`):** render indexed PNGs in EPSG:3857 plus JSON sidecars.

Regions are processed in two passes. All GeoTIFFs are written first, then `global_value_ranges` finds the cold and heat ranges across every region, and only then are the PNGs rendered. This keeps colours comparable between regions. A sidecar's `raw_min`/`raw_max` span all regions, and `local_min`/`local_max` describe that region alone. Changing any region's data can therefore change every region's PNGs and sidecars.

### Data semantics

- CDS day counts are cumulative (days above or below a threshold). `thermal_stress_summary.py` subtracts them into disjoint brackets and raises an error if a result is negative.
- Day-count bands are medians across years. Total bands sum categories within each year before taking the median, so a total does not generally equal the sum of the category medians.
- Heat days use the daily maximum (above 26 °C) and cold days use the daily minimum (below 9 °C). The same day can count as both.
- A pixel missing in any year stays missing in the day-count bands.
- Record bands hold the extreme UTCI in °C and the first year it occurred.
- PNGs show only the two total bands and mask the sea using the GISCO coastline. GeoTIFFs keep all bands and the sea pixels, so popup values can exist where the map is transparent.

## Frontend

`frontend/app.js` wires the modules together. MapLibre and GeoTIFF.js are loaded from CDNs in `index.html` and accessed as globals.

- `data/regional-files.js` addresses files per region, for example `mainland/utci_cold_days.png`.
- `data/combined-files.js` groups them by filename, so choosing a layer shows it for all regions at once. A point query goes to the first region whose bounds contain it and that has data there.
- `data/summary-reader.js` reads single pixels directly from the region's GeoTIFF. This requires the EPSG:4326, north-up, pixel-is-area format the pipeline writes.
- The frontend uses only the placement fields from sidecars, not `metric` or `color_map`.
- `data/png-files.js` is not used by the app, only by the frontend tests.

## Keeping things in sync

Several values are duplicated with nothing enforcing that they match:

- **Regions:** defined by `EuropeBounds` in `thermal_dataset_download.py` and must also be added to `REGIONS` in `frontend/config.js`, using the lowercased attribute name. `get_download_regions` only picks up attributes whose bounds are also in `EuropeBounds.REGIONS`.
- **Years:** set in both `thermal_dataset_download.py` and `utci_map/source/config.py`. The years in `config.py` determine which archive filename `utci_map` looks for.
- **Stress brackets:** `schema.py` derives field and band names from the brackets, but `_yearly_days_by_stress_category` hard-codes the thresholds and `popup/content.js` hard-codes labels for each band name.
- **Preview script:** `thermal_dataset_preview.py` is a self-contained copy of the schema, palettes and processing logic, and shares only download helpers with `utci_map`. Changes to `utci_map` do not reach it.

## Repository notes

- Only the `.name` of the output paths in `config.py` is used; the real files live in `output/map/<region>/`. The five files directly in `output/` are not used by the pipeline or the frontend, and appear to predate the regional layout.
- `output/map/<region>/` is committed because the frontend reads it directly. Regenerate and commit it when pipeline changes affect the outputs. `downloads/` and `*.zip` are ignored, so a regeneration depends on local archives.
- Python tests sit next to the code in `tests/` directories, and downloader tests are in the root `tests/`. Fixtures in `utci_map/source/conftest.py` build synthetic data and real temporary NetCDF files, and NetCDF tests skip if GDAL lacks the netCDF driver.
- A `<module>.unit.test.py` file beside a `test_<module>.py` is a second, narrower tier: it pins the module's current internal behavior as a guard against unintended side effects from refactors, not a statement of required behavior. Its module docstring says this explicitly. Don't read it as a spec, and don't infer the module's public contract from what it happens to assert — that contract lives only in `test_<module>.py`.
