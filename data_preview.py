import xarray as xr

# Direct path to the extracted subset file
nc_path = (
    "utci_iceland_sample/ECMWF_utci_yearly_stats_2015_v1.1_con.area-subset.67.5.-13.0.63.0.-25.0.nc"
)

# Open the NetCDF raster
ds = xr.open_dataset(nc_path)
print(ds)