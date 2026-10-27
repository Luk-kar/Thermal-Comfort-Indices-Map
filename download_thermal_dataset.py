import cdsapi

NUMBER_OF_YEARS = 10
END_YEAR = 2025
START_YEAR = END_YEAR - NUMBER_OF_YEARS + 1

YEARS = [
    str(year)
    for year in range(START_YEAR, END_YEAR + 1)
]

print(f"Downloading for years: {YEARS}")

dataset = "derived-utci-historical"
request = {
    "variable": [
        "universal_thermal_climate_index_yearly_statistics"
    ],
    "version": "1_1",
    "product_type": "consolidated_dataset",
    "year": YEARS,
    "area": [67.5, -25.0, 63.0, -13.0],
}
target = "utci_iceland_sample.zip"

client = cdsapi.Client()
client.retrieve(dataset, request, target)
