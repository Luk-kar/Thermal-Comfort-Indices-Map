const SOURCE_PREFIX = "output-png-";
const LAYER_PREFIX = "output-png-layer-";

export function createPngOverlay(map, pngRepository, onError = console.error) {
  const state = {
    selectionId: 0,
    opacity: 0.8,
    active: [],
  };

  function setOpacity(opacity) {
    state.opacity = opacity;

    for (const { layerId } of state.active) {
      if (map.getLayer(layerId)) {
        map.setPaintProperty(layerId, "raster-opacity", opacity);
      }
    }
  }

  function clearImages() {
    for (const { layerId, sourceId } of state.active) {
      if (map.getLayer(layerId)) map.removeLayer(layerId);
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    }

    state.active = [];
  }

  async function showImage(
    name,
    { opacity = state.opacity, fit = true } = {},
  ) {
    const selectionId = ++state.selectionId;
    setOpacity(opacity);

    let placements;

    try {
      placements = await pngRepository.getPlacements(name);
    } catch (error) {
      if (selectionId !== state.selectionId) return;
      throw error;
    }

    // Ignore a previous selection that finished loading too late.
    if (selectionId !== state.selectionId) return;

    if (!placements.length) {
      throw new Error(`No regional PNGs configured for ${name}`);
    }

    clearImages();

    try {
      placements.forEach((placement, index) => {
        const sourceId = `${SOURCE_PREFIX}${selectionId}-${index}`;
        const layerId = `${LAYER_PREFIX}${selectionId}-${index}`;

        map.addSource(sourceId, {
          type: "image",
          url: placement.url,
          coordinates: placement.coordinates,
        });

        // Track the source immediately so cleanup also handles addLayer errors.
        state.active.push({ sourceId, layerId });

        map.addLayer({
          id: layerId,
          type: "raster",
          source: sourceId,
          paint: {
            "raster-opacity": state.opacity,
            "raster-fade-duration": 0,
          },
        });
      });
    } catch (error) {
      clearImages();
      throw error;
    }

    if (fit) {
      const bounds = placements.reduce(
        (combined, placement) => {
          const [west, south, east, north] = placement.bounds;

          return [
            Math.min(combined[0], west),
            Math.min(combined[1], south),
            Math.max(combined[2], east),
            Math.max(combined[3], north),
          ];
        },
        [Infinity, Infinity, -Infinity, -Infinity],
      );

      const [west, south, east, north] = bounds;

      map.fitBounds(
        [[west, south], [east, north]],
        { padding: 40 },
      );
    }
  }

  map.on("error", event => {
    const isActiveSource = state.active.some(
      ({ sourceId }) => sourceId === event.sourceId,
    );

    if (isActiveSource) {
      onError(
        "Failed to load a regional PNG: " +
        (event.error?.message || "unknown error"),
      );
    }
  });

  return { showImage, setOpacity };
}