# UTCI map pipeline

Extract this archive into the project root. Run from that root:

    python -m utci_map

Default layout:

    project-root/
        utci_map/
        utci_iceland_sample/
        output/                 # created on execution

Edit:
`utci_map/config.py` to change 
paths, years, strictness and map styling.

Paths remain relative to the working directory.

Modules:
- __main__.py: pipeline entry point and progress messages
- config.py: runtime settings, paths and styling
- schema.py: variable names, thresholds, brackets and band naming
- models.py: immutable data containers
- netcdf_reader.py: per-file reading and validation
- combine_yearly_utci_statistics.py: cross-file assembly and period validation
- bands.py: summary calculations and unit conversion
- geotiff.py: GeoTIFF writer and band-description lookup
- palette.py: colour interpolation and quantisation
- png_maps.py: reprojection, PNG rendering and JSON sidecars
