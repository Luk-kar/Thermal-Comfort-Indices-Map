import { createSummaryReader } from "./summary-reader.js";

function isBounds(value) {
    return (
        Array.isArray(value) &&
        value.length === 4 &&
        value.every(Number.isFinite) &&
        value[0] < value[2] &&
        value[1] < value[3]
    );
}

function isCoordinates(value) {
    return (
        Array.isArray(value) &&
        value.length === 4 &&
        value.every(
            point =>
                Array.isArray(point) &&
                point.length === 2 &&
                point.every(Number.isFinite),
        )
    );
}

function parsePlacement(metadata, sidecarUrl) {
    if (!metadata || typeof metadata !== "object") {
        throw new Error(`Invalid placement metadata in ${sidecarUrl}`);
    }

    if (metadata.coordinates != null) {
        const coordinates = metadata.coordinates;

        if (!isCoordinates(coordinates)) {
            throw new Error(
                `Invalid coordinates in ${sidecarUrl}: expected four [longitude, latitude] pairs`,
            );
        }

        const longitudes = coordinates.map(point => point[0]);
        const latitudes = coordinates.map(point => point[1]);

        const bounds = [
            Math.min(...longitudes),
            Math.min(...latitudes),
            Math.max(...longitudes),
            Math.max(...latitudes),
        ];

        if (!isBounds(bounds)) {
            throw new Error(`Degenerate image extent in ${sidecarUrl}`);
        }

        return { coordinates, bounds };
    }

    if (isBounds(metadata.bounds)) {
        const bounds = [...metadata.bounds];
        const [west, south, east, north] = bounds;

        return {
            bounds,
            coordinates: [
                [west, north],
                [east, north],
                [east, south],
                [west, south],
            ],
        };
    }

    throw new Error(
        `Missing or invalid placement in ${sidecarUrl}: expected coordinates ` +
        `or bounds [west, south, east, north]`,
    );
}

/**
 * Creates a repository for region-specific PNG overlays and summary GeoTIFFs.
 *
 * Each region is a subdirectory of outputDir containing the configured PNGs,
 * matching JSON placement sidecars, and a summary GeoTIFF. Images are addressed
 * by region-qualified names such as "mainland/utci_cold_days.png".
 *
 * Placement comes exclusively from sidecars; no shared geographic fallback is
 * used. Summary readers are created on demand and cached per region.
 *
 * @param {Object} options - Regional output configuration.
 * @param {string} options.outputDir - Root output URL relative to the HTML page.
 * @param {string[]} options.regions - Region subdirectory names.
 * @param {string[]} options.pngFiles - PNG filenames expected in each region.
 * @param {string} options.summaryTifName - Summary GeoTIFF filename.
 * @param {Object} options.geoTIFF - GeoTIFF library used by summary readers.
 * @param {Function} [fetchImpl] - Optional fetch implementation for testing.
 * @returns {Object} Regional image listing, placement, and summary-reader API.
 */
export function createRegionalRepository(
    {
        outputDir,
        regions,
        pngFiles,
        summaryTifName,
        geoTIFF,
    },
    fetchImpl = (...args) => globalThis.fetch(...args),
) {
    const root = outputDir.endsWith("/") ? outputDir : `${outputDir}/`;
    const entries = new Map();
    const summaryReaders = new Map();

    for (const region of regions) {
        const regionDir = `${root}${encodeURIComponent(region)}/`;

        for (const filename of pngFiles) {
            entries.set(`${region}/${filename}`, {
                region,
                regionDir,
                filename,
            });
        }
    }

    function getEntry(name) {
        const entry = entries.get(name);

        if (!entry) {
            throw new Error(`Unknown regional PNG: ${name}`);
        }

        return entry;
    }

    async function listPngs() {
        return [...entries.keys()];
    }

    async function getPlacement(name) {
        const { regionDir, filename } = getEntry(name);
        const url = `${regionDir}${encodeURIComponent(filename)}`;

        const sidecarName = filename.replace(/\.png$/i, ".json");
        const sidecarUrl = `${regionDir}${encodeURIComponent(sidecarName)}`;

        const response = await fetchImpl(sidecarUrl);

        if (!response.ok) {
            throw new Error(
                `Could not load ${sidecarUrl} (HTTP ${response.status})`,
            );
        }

        const metadata = await response.json();
        const { coordinates, bounds } = parsePlacement(metadata, sidecarUrl);

        return { url, coordinates, bounds };
    }

    function getSummaryReader(name) {
        const { region, regionDir } = getEntry(name);

        if (!summaryReaders.has(region)) {
            summaryReaders.set(
                region,
                createSummaryReader(
                    `${regionDir}${encodeURIComponent(summaryTifName)}`,
                    geoTIFF,
                ),
            );
        }

        return summaryReaders.get(region);
    }

    return {
        listPngs,
        getPlacement,
        getSummaryReader,
    };
}