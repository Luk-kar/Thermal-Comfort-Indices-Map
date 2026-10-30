  // ---- CONFIG ---------------------------------------------------------
  // Path relative to this HTML file (frontend/ -> ../output/).
  const OUTPUT_DIR = "../output/";
  const SUMMARY_TIF_URL = OUTPUT_DIR + "utci_summary.tif";

  // Bounds of the PNGs in lon/lat (EPSG:4326): [west, south, east, north].
  // Taken from the NetCDF subset name: N=67.5, E=-13.0, S=63.0, W=-25.0.
  const DEFAULT_BOUNDS = [-25.0, 63.0, -13.0, 67.5];

  // Optional per-file bounds overrides, e.g. { "utci_mean.png": [w, s, e, n] }.
  const BOUNDS_BY_FILE = {};

  // Fallback list, used when the server gives no directory listing.
  const MANUAL_FILES = [
    // "utci_mean_2016.png",
  ];
  // ---------------------------------------------------------------------

  const SOURCE_ID = "output-png";
  const LAYER_ID = "output-png-layer";

  const map = new maplibregl.Map({
    container: "map",
    center: [-19, 65.25],
    zoom: 5,
    style: {
      version: 8,
      sources: {
        osm: {
          type: "raster",
          tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
          tileSize: 256,
          maxzoom: 19,
          attribution: "© OpenStreetMap contributors",
        },
      },
      layers: [{ id: "osm", type: "raster", source: "osm" }],
    },
  });
  map.addControl(new maplibregl.NavigationControl(), "top-right");
  map.addControl(new maplibregl.ScaleControl());

  const $files = document.getElementById("files");
  const $opacity = document.getElementById("opacity");
  const $opacityVal = document.getElementById("opacityVal");
  const $fit = document.getElementById("fit");
  const $status = document.getElementById("status");

  const boundsToCoords = ([w, s, e, n]) => [[w, n], [e, n], [e, s], [w, s]];

  async function listPngs() {
    try {
      const res = await fetch(OUTPUT_DIR);
      if (!res.ok) throw new Error(res.status);
      const doc = new DOMParser().parseFromString(await res.text(), "text/html");
      const names = [...doc.querySelectorAll("a")]
        .map(a => decodeURIComponent(a.getAttribute("href").split("?")[0]))
        .filter(h => h.toLowerCase().endsWith(".png"))
        .map(h => h.split("/").pop());
      if (names.length) return [...new Set(names)].sort();
    } catch (e) { /* fall through */ }
    return MANUAL_FILES;
  }

  let imageSelectionId = 0;

  async function showImage(name) {
    const selectionId = ++imageSelectionId;
    let bounds = BOUNDS_BY_FILE[name] || DEFAULT_BOUNDS;
    let coordinates = boundsToCoords(bounds);
    if (!BOUNDS_BY_FILE[name]) {
      try {
        const response = await fetch(OUTPUT_DIR + encodeURIComponent(name.replace(/\.png$/i, ".json")));
        if (!response.ok) throw new Error(response.status);
        const sidecar = await response.json();
        if (!Array.isArray(sidecar.coordinates) || sidecar.coordinates.length !== 4 ||
            !sidecar.coordinates.every(point => Array.isArray(point) && point.length === 2 && point.every(Number.isFinite))) {
          throw new Error("Invalid sidecar coordinates");
        }
        coordinates = sidecar.coordinates;
        const longitudes = coordinates.map(point => point[0]);
        const latitudes = coordinates.map(point => point[1]);
        bounds = [Math.min(...longitudes), Math.min(...latitudes), Math.max(...longitudes), Math.max(...latitudes)];
      } catch (error) {
        console.warn(`Using fallback PNG bounds for ${name}:`, error);
      }
    }
    if (selectionId !== imageSelectionId) return;
    const url = OUTPUT_DIR + encodeURIComponent(name);
    $status.textContent = "";

    if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID);
    if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);

    map.addSource(SOURCE_ID, { type: "image", url, coordinates });
    map.addLayer({
      id: LAYER_ID,
      type: "raster",
      source: SOURCE_ID,
      paint: { "raster-opacity": parseFloat($opacity.value), "raster-fade-duration": 0 },
    });

    if ($fit.checked) {
      map.fitBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]], { padding: 40 });
    }
  }


  // Read original data, independently of the selected PNG's palette/opacity.
  let summaryPromise = null;
  let activePointPopup = null;

  const BAND_LABELS = {
    "days_daily_max_26_32": "Daily maximum UTCI: 26 to 32 °C",
    "days_daily_max_32_38": "Daily maximum UTCI: 32 to 38 °C",
    "days_daily_max_38_46": "Daily maximum UTCI: 38 to 46 °C",
    "days_daily_max_46_inf": "Daily maximum UTCI: above 46 °C",
    "days_daily_min_-inf_-40": "Daily minimum UTCI: below −40 °C",
    "days_daily_min_-40_-27": "Daily minimum UTCI: −40 to −27 °C",
    "days_daily_min_-27_-13": "Daily minimum UTCI: −27 to −13 °C",
    "days_daily_min_-13_0": "Daily minimum UTCI: −13 to 0 °C",
    "days_daily_min_0_9": "Daily minimum UTCI: 0 to 9 °C",
    "days_daily_min_below_9_total": "Total cold-stress days (daily minimum below 9 °C)",
    "days_daily_max_above_26_total": "Total heat-stress days (daily maximum above 26 °C)",
    "record_max_utci_c": "Record maximum UTCI",
    "record_max_utci_year": "Record maximum UTCI year",
    "record_min_utci_c": "Record minimum UTCI",
    "record_min_utci_year": "Record minimum UTCI year",
  };

  function metadataValue(metadata, name) {
    const key = Object.keys(metadata || {}).find(key => key.toLowerCase() === name.toLowerCase());
    return key === undefined ? null : metadata[key];
  }

  async function loadSummary() {
    if (!summaryPromise) {
      summaryPromise = (async () => {
        if (typeof GeoTIFF === "undefined") {
          throw new Error("The GeoTIFF.js library could not be loaded.");
        }
        // Also support simple HTTP servers that return the entire TIFF instead of ranges.
        const tiff = await GeoTIFF.fromUrl(SUMMARY_TIF_URL, { allowFullFile: true });
        const image = await tiff.getImage(0);
        const keys = image.getGeoKeys();
        if (Number(keys?.GeographicTypeGeoKey) !== 4326 ||
            (keys.GTModelTypeGeoKey != null && Number(keys.GTModelTypeGeoKey) !== 2)) {
          throw new Error("Point queries require the EPSG:4326 GeoTIFF written by this pipeline.");
        }
        if (Number(keys.GTRasterTypeGeoKey) === 2) {
          throw new Error("Point queries require a pixel-is-area raster.");
        }
        const matrix = image.getFileDirectory().ModelTransformation;
        if (matrix && (matrix[1] !== 0 || matrix[4] !== 0 || matrix[2] !== 0 || matrix[6] !== 0)) {
          throw new Error("Rotated or sheared GeoTIFF grids are not supported by this viewer.");
        }
        const origin = image.getOrigin();
        const resolution = image.getResolution();
        if (![origin[0], origin[1], resolution[0], resolution[1]].every(Number.isFinite) ||
            resolution[0] <= 0 || resolution[1] >= 0) {
          throw new Error("Expected an unrotated north-up GeoTIFF grid.");
        }
        const bands = await Promise.all(
          Array.from({ length: image.getSamplesPerPixel() }, async (_, sample) => {
            const metadata = await image.getGDALMetadata(sample) || {};
            return {
              sample,
              name: String(metadataValue(metadata, "DESCRIPTION") || `band_${sample + 1}`),
              units: String(metadataValue(metadata, "units") || metadataValue(metadata, "UNITTYPE") || ""),
            };
          })
        );
        return {
          image, bands, origin, resolution,
          width: image.getWidth(), height: image.getHeight(),
          nodata: image.getGDALNoData(),
          metadata: await image.getGDALMetadata() || {},
        };
      })().catch(error => {
        summaryPromise = null; // A later click can retry a failed request.
        throw error;
      });
    }
    return summaryPromise;
  }

  function pointToPixel(summary, longitude, latitude) {
    // MapLibre may report longitudes outside [-180, 180] on wrapped world copies.
    const normalizedLongitude = ((longitude + 180) % 360 + 360) % 360 - 180;
    const column = Math.floor((normalizedLongitude - summary.origin[0]) / summary.resolution[0]);
    const row = Math.floor((latitude - summary.origin[1]) / summary.resolution[1]);
    if (!Number.isFinite(column) || !Number.isFinite(row) ||
        column < 0 || column >= summary.width || row < 0 || row >= summary.height) {
      return null;
    }
    return { column, row, longitude: normalizedLongitude };
  }

  function formatBandValue(value, units, nodata) {
    if (!Number.isFinite(value) || (nodata !== null && value === nodata)) return "No data";
    const unitLabel = units === "degC" ? "°C" : units;
    const text = units === "year"
      ? String(Math.round(value))
      : new Intl.NumberFormat("en", { maximumFractionDigits: 2 }).format(value);
    return units === "year" || !unitLabel ? text : `${text} ${unitLabel}`;
  }

  function appendText(parent, tag, text, className) {
    const element = document.createElement(tag);
    element.textContent = text;
    if (className) element.className = className;
    parent.appendChild(element);
    return element;
  }

  function buildPointContent(summary, pixel, latitude, values) {
    const content = document.createElement("section");
    content.className = "point-data";
    appendText(content, "h3", "UTCI point data");
    appendText(content, "p", `${pixel.longitude.toFixed(5)}°, ${latitude.toFixed(5)}°`);
    const startYear = metadataValue(summary.metadata, "start_year");
    const endYear = metadataValue(summary.metadata, "end_year");
    if (startYear != null && endYear != null) {
      appendText(content, "p", `Summary period: ${startYear}–${endYear}`);
    }
    const centerLongitude = summary.origin[0] + (pixel.column + 0.5) * summary.resolution[0];
    const centerLatitude = summary.origin[1] + (pixel.row + 0.5) * summary.resolution[1];
    appendText(content, "p",
      `Source pixel: row ${pixel.row}, column ${pixel.column} (zero-based). ` +
      `Centre: ${centerLongitude.toFixed(5)}°, ${centerLatitude.toFixed(5)}°.`, "point-note");
    const hasData = Array.from(values).some(value =>
      Number.isFinite(value) && (summary.nodata === null || value !== summary.nodata));
    if (!hasData) appendText(content, "p", "No valid data at this source pixel.");
    const table = document.createElement("table");
    const head = table.createTHead().insertRow();
    appendText(head, "th", "Metric");
    appendText(head, "th", "Value");
    const body = table.createTBody();
    summary.bands.forEach((band, index) => {
      const value = values[index];
      const isDayCount =
        band.units === "days" || band.name.startsWith("days_");

      if (isDayCount && value === 0) {
        return;
      }

      const row = body.insertRow();
      const label = row.insertCell();

      appendText(label, "span", BAND_LABELS[band.name] || band.name);
      appendText(label, "code", band.name, "band-name");

      row.insertCell().textContent = formatBandValue(
        value,
        band.units,
        summary.nodata,
      );
    });
    content.appendChild(table);
    appendText(content, "p",
      "Day counts are median yearly counts. Record values and years cover the summary period. " +
      "Values come from the containing source pixel, without interpolation. " +
      "PNG coastline masking does not remove sea values from the original GeoTIFF.", "point-note");
    return content;
  }

  map.on("click", async event => {
    if (activePointPopup) activePointPopup.remove();
    const popup = new maplibregl.Popup({ maxWidth: "min(520px, 90vw)" })
      .setLngLat(event.lngLat)
      .setText("Loading point data…")
      .addTo(map);
    activePointPopup = popup;
    const isCurrent = () => activePointPopup === popup && popup.isOpen();
    try {
      const summary = await loadSummary();
      if (!isCurrent()) return;
      const pixel = pointToPixel(summary, event.lngLat.lng, event.lngLat.lat);
      if (!pixel) {
        popup.setText("This point is outside the summary GeoTIFF extent.");
        return;
      }
      const values = await summary.image.readRasters({
        window: [pixel.column, pixel.row, pixel.column + 1, pixel.row + 1],
        samples: summary.bands.map(band => band.sample),
        interleave: true,
      });
      if (!isCurrent()) return;
      popup.setDOMContent(buildPointContent(summary, pixel, event.lngLat.lat, values));
    } catch (error) {
      console.error("Point query failed:", error);
      if (isCurrent()) popup.setText(`Could not read point data: ${error.message || String(error)}`);
    }
  });

  map.on("error", e => {
    if (e.sourceId === SOURCE_ID) $status.textContent = "Failed to load the PNG: " + (e.error?.message || "unknown error");
  });

  $opacity.addEventListener("input", () => {
    $opacityVal.textContent = $opacity.value;
    if (map.getLayer(LAYER_ID)) map.setPaintProperty(LAYER_ID, "raster-opacity", parseFloat($opacity.value));
  });

  map.on("load", async () => {
    const files = await listPngs();
    if (!files.length) {
      $status.textContent = "No PNGs found. Serve the project root over HTTP or fill MANUAL_FILES.";
      return;
    }
    files.forEach(name => {
      const li = document.createElement("li");
      li.textContent = name;
      li.onclick = () => {
        document.querySelectorAll("#files li").forEach(x => x.classList.remove("active"));
        li.classList.add("active");
        showImage(name);
      };
      $files.appendChild(li);
    });
    $files.firstChild.click();
  });
