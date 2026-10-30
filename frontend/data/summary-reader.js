export function metadataValue(metadata, name) {
  const key = Object.keys(metadata || {}).find(
    key => key.toLowerCase() === name.toLowerCase(),
  );

  return key === undefined ? null : metadata[key];
}

export function pointToPixel(summary, longitude, latitude) {
  const normalizedLongitude = ((longitude + 180) % 360 + 360) % 360 - 180;

  const column = Math.floor(
    (normalizedLongitude - summary.origin[0]) / summary.resolution[0],
  );

  const row = Math.floor(
    (latitude - summary.origin[1]) / summary.resolution[1],
  );

  if (
    !Number.isFinite(column) ||
    !Number.isFinite(row) ||
    column < 0 ||
    column >= summary.width ||
    row < 0 ||
    row >= summary.height
  ) {
    return null;
  }

  return { column, row, longitude: normalizedLongitude };
}

export function createSummaryReader(tiffUrl, geotiff) {
  const state = { summaryPromise: null };

  async function loadSummary() {
    if (!state.summaryPromise) {
      state.summaryPromise = (async () => {
        if (!geotiff) {
          throw new Error("The GeoTIFF.js library could not be loaded.");
        }

        const tiff = await geotiff.fromUrl(tiffUrl, {
          allowFullFile: true,
        });

        const image = await tiff.getImage(0);
        const keys = image.getGeoKeys();

        if (
          Number(keys?.GeographicTypeGeoKey) !== 4326 ||
          (
            keys.GTModelTypeGeoKey != null &&
            Number(keys.GTModelTypeGeoKey) !== 2
          )
        ) {
          throw new Error(
            "Point queries require the EPSG:4326 GeoTIFF written by this pipeline.",
          );
        }

        if (Number(keys.GTRasterTypeGeoKey) === 2) {
          throw new Error("Point queries require a pixel-is-area raster.");
        }

        const matrix = image.getFileDirectory().ModelTransformation;

        if (
          matrix &&
          (
            matrix[1] !== 0 ||
            matrix[4] !== 0 ||
            matrix[2] !== 0 ||
            matrix[6] !== 0
          )
        ) {
          throw new Error(
            "Rotated or sheared GeoTIFF grids are not supported by this viewer.",
          );
        }

        const origin = image.getOrigin();
        const resolution = image.getResolution();

        if (
          ![
            origin[0],
            origin[1],
            resolution[0],
            resolution[1],
          ].every(Number.isFinite) ||
          resolution[0] <= 0 ||
          resolution[1] >= 0
        ) {
          throw new Error("Expected an unrotated north-up GeoTIFF grid.");
        }

        const bands = await Promise.all(
          Array.from(
            { length: image.getSamplesPerPixel() },
            async (_, sample) => {
              const metadata = await image.getGDALMetadata(sample) || {};

              return {
                sample,
                name: String(
                  metadataValue(metadata, "DESCRIPTION") ||
                  `band_${sample + 1}`,
                ),
                units: String(
                  metadataValue(metadata, "units") ||
                  metadataValue(metadata, "UNITTYPE") ||
                  "",
                ),
              };
            },
          ),
        );

        return {
          image,
          bands,
          origin,
          resolution,
          width: image.getWidth(),
          height: image.getHeight(),
          nodata: image.getGDALNoData(),
          metadata: await image.getGDALMetadata() || {},
        };
      })().catch(error => {
        state.summaryPromise = null;

        throw error;
      });
    }

    return state.summaryPromise;
  }

  async function readPoint(longitude, latitude) {
    const summary = await loadSummary();
    const pixel = pointToPixel(summary, longitude, latitude);

    if (!pixel) {
      return null;
    }

    const values = await summary.image.readRasters({
      window: [
        pixel.column,
        pixel.row,
        pixel.column + 1,
        pixel.row + 1,
      ],
      samples: summary.bands.map(band => band.sample),
      interleave: true,
    });

    return {
      longitude: pixel.longitude,
      latitude,
      pixel: {
        column: pixel.column,
        row: pixel.row,
      },
      pixelCenter: {
        longitude:
          summary.origin[0] +
          (pixel.column + 0.5) * summary.resolution[0],
        latitude:
          summary.origin[1] +
          (pixel.row + 0.5) * summary.resolution[1],
      },
      period: {
        startYear: metadataValue(summary.metadata, "start_year"),
        endYear: metadataValue(summary.metadata, "end_year"),
      },
      bands: summary.bands,
      values,
      nodata: summary.nodata,
    };
  }

  return { readPoint };
}