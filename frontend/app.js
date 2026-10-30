import {
  OUTPUT_DIR,
  REGIONS,
  PNG_FILES,
  SUMMARY_TIF_NAME,
} from "./config.js";

import { createMap } from "./map/create-map.js";
import { createPngOverlay } from "./map/png-overlay.js";
import { createRegionalRepository } from "./data/regional-files.js";
import { buildPointContent } from "./popup/content.js";
import { attachPointPopup } from "./popup/controller.js";
import { initializeSidebar } from "./ui/sidebar.js";
import { createCombinedRepository } from "./data/combined-files.js";

function startApplication() {

  const maplibre = globalThis.maplibregl;

  if (!maplibre) {
    throw new Error("The MapLibre library could not be loaded.");
  }

  const map = createMap(maplibre);

  const regionalRepository = createRegionalRepository({
    outputDir: OUTPUT_DIR,
    regions: REGIONS,
    pngFiles: PNG_FILES,
    summaryTifName: SUMMARY_TIF_NAME,
    geoTIFF: globalThis.GeoTIFF,
  });

  const repository = createCombinedRepository(regionalRepository);

  const state = {
    selectionId: 0,
    activeReader: null,
  };

  let sidebar;

  const overlay = createPngOverlay(
    map,
    repository,
    message => sidebar.setStatus(message),
  );

  sidebar = initializeSidebar({
    onSelectImage: async (name, options) => {
      const selectionId = ++state.selectionId;

      // Do not query the previous region while a new image is loading.
      state.activeReader = null;

      await overlay.showImage(name, options);

      if (selectionId !== state.selectionId) return;

      state.activeReader = repository.getSummaryReader(name);
    },

    onOpacityChange: opacity => overlay.setOpacity(opacity),
  });

  // Keep the popup controller's existing readPoint() interface.
  const summaryReader = {
    async readPoint(longitude, latitude) {
      const reader = state.activeReader;
      const selectionId = state.selectionId;

      if (!reader) return null;

      const point = await reader.readPoint(longitude, latitude);

      if (selectionId !== state.selectionId) return null;

      return point;
    },
  };

  attachPointPopup(map, {
    summaryReader,
    buildContent: buildPointContent,
    maplibre,
  });

  map.on("load", async () => {
    try {
      sidebar.setFiles(await repository.listPngs());
    } catch (error) {
      sidebar.setStatus(
        `Failed to list PNGs: ${error.message || String(error)}`,
      );
    }
  });
}

try {
  startApplication();
} catch (error) {
  console.error("Application startup failed:", error);
  document.getElementById("status").textContent =
    error.message || String(error);
}