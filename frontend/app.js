import {
  OUTPUT_DIR, SUMMARY_TIF_URL, DEFAULT_BOUNDS, BOUNDS_BY_FILE, MANUAL_FILES,
} from "./config.js";

import { createMap } from "./map/create-map.js";
import { createPngOverlay } from "./map/png-overlay.js";
import { createPngRepository } from "./data/png-files.js";
import { createSummaryReader } from "./data/summary-reader.js";
import { buildPointContent } from "./popup/content.js";
import { attachPointPopup } from "./popup/controller.js";
import { initializeSidebar } from "./ui/sidebar.js";

function startApplication() {

  const maplibre = globalThis.maplibregl;
  if (!maplibre) throw new Error("The MapLibre library could not be loaded.");

  const map = createMap(maplibre);
  const pngRepository = createPngRepository({
    outputDir: OUTPUT_DIR,
    defaultBounds: DEFAULT_BOUNDS,
    boundsByFile: BOUNDS_BY_FILE,
    manualFiles: MANUAL_FILES,
  });
  const summaryReader = createSummaryReader(SUMMARY_TIF_URL, globalThis.GeoTIFF);

  const overlay = createPngOverlay(map, pngRepository, message => sidebar.setStatus(message));
  const sidebar = initializeSidebar({
    onSelectImage: (name, options) => overlay.showImage(name, options),
    onOpacityChange: opacity => overlay.setOpacity(opacity),
  });

  attachPointPopup(map, { summaryReader, buildContent: buildPointContent, maplibre });

  map.on("load", async () => {
    try {
      sidebar.setFiles(await pngRepository.listPngs());
    } catch (error) {
      sidebar.setStatus(`Failed to list PNGs: ${error.message || String(error)}`);
    }
  });
}

try {
  startApplication();
} catch (error) {
  console.error("Application startup failed:", error);
  document.getElementById("status").textContent = error.message || String(error);
}
