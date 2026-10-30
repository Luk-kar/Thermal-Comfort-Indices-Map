const SOURCE_ID = "output-png";
const LAYER_ID = "output-png-layer";

export function createPngOverlay(map, pngRepository, onError = console.error) {
  const state = { selectionId: 0, opacity: 0.8 };

  function setOpacity(opacity) {

    state.opacity = opacity;
    if (map.getLayer(LAYER_ID)) {
      map.setPaintProperty(LAYER_ID, "raster-opacity", opacity);
    }
  }

  async function showImage(name, { opacity = state.opacity, fit = true } = {}) {

    const selectionId = ++state.selectionId;
    setOpacity(opacity);
    const placement = await pngRepository.getPlacement(name);

    if (selectionId !== state.selectionId) return;

    if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID);
    if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);

    map.addSource(SOURCE_ID, {
      type: "image", url: placement.url, coordinates: placement.coordinates,
    });

    map.addLayer({
      id: LAYER_ID,
      type: "raster",
      source: SOURCE_ID,
      paint: { "raster-opacity": state.opacity, "raster-fade-duration": 0 },
    });

    if (fit) {
      const [west, south, east, north] = placement.bounds;
      map.fitBounds([[west, south], [east, north]], { padding: 40 });
    }
  }

  map.on("error", event => {
    if (event.sourceId === SOURCE_ID) {
      onError("Failed to load the PNG: " + (event.error?.message || "unknown error"));
    }
  });

  return { showImage, setOpacity };
}
