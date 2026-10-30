const boundsToCoords = ([west, south, east, north]) => [
  [west, north], [east, north], [east, south], [west, south],
];

function validateCoordinates(coordinates) {

  return Array.isArray(coordinates) && coordinates.length === 4 &&
    coordinates.every(point => Array.isArray(point) && point.length === 2 &&
      point.every(Number.isFinite));
}

export function createPngRepository({

  outputDir, defaultBounds, boundsByFile, manualFiles,
}, fetchResource = globalThis.fetch) {

  async function listPngs() {
    try {
      const response = await fetchResource(outputDir);
      if (!response.ok) throw new Error(response.status);
      const document = new DOMParser().parseFromString(await response.text(), "text/html");
      const names = [...document.querySelectorAll("a")]
        .map(link => link.getAttribute("href"))
        .filter(Boolean)
        .map(href => decodeURIComponent(href.split(/[?#]/)[0]))
        .filter(href => href.toLowerCase().endsWith(".png"))
        .map(href => href.split("/").pop());
      if (names.length) return [...new Set(names)].sort();
    } catch (error) {
      // Servers without directory listings use the configured fallback.
    }
    return [...manualFiles];
  }

  async function getPlacement(name) {

    let bounds = boundsByFile[name] || defaultBounds;
    let coordinates = boundsToCoords(bounds);

    if (!boundsByFile[name]) {

      try {

        const response = await fetchResource(
          outputDir + encodeURIComponent(name.replace(/\.png$/i, ".json")),
        );

        if (!response.ok) throw new Error(response.status);

        const sidecar = await response.json();

        if (!validateCoordinates(sidecar.coordinates)) {
          throw new Error("Invalid sidecar coordinates");
        }

        coordinates = sidecar.coordinates;
        const longitudes = coordinates.map(point => point[0]);
        const latitudes = coordinates.map(point => point[1]);

        bounds = [Math.min(...longitudes), Math.min(...latitudes),
        Math.max(...longitudes), Math.max(...latitudes)];

      } catch (error) {
        console.warn(`Using fallback PNG bounds for ${name}:`, error);
      }
    }
    return { url: outputDir + encodeURIComponent(name), bounds, coordinates };
  }

  return { listPngs, getPlacement };
}
