import test from "node:test";
import assert from "node:assert/strict";
import { createPngRepository } from "../data/png-files.js";
import { createSummaryReader, metadataValue, pointToPixel } from "../data/summary-reader.js";
import { createPngOverlay } from "../map/png-overlay.js";
import { formatBandValue, buildPointContent } from "../popup/content.js";
import { attachPointPopup } from "../popup/controller.js";
import { initializeSidebar } from "../ui/sidebar.js";
import { createRegionalRepository } from "../data/regional-files.js";

class Element {
  constructor(tag = "div") {
    this.tag = tag;
    this.children = [];
    this.listeners = {};
    this.value = "0.8";
    this.checked = true;
    this.textContent = "";
    const classes = new Set();
    this.classList = { add: name => classes.add(name), remove: name => classes.delete(name), contains: name => classes.has(name) };
  }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren() { this.children = []; }
  addEventListener(event, handler) { this.listeners[event] = handler; }
  querySelectorAll() { return this.children; }
  get firstElementChild() { return this.children[0]; }
  click() { return this.onclick?.(); }
  createTHead() { return this.appendChild(new Element("thead")); }
  createTBody() { return this.appendChild(new Element("tbody")); }
  insertRow() { return this.appendChild(new Element("tr")); }
  insertCell() { return this.appendChild(new Element("td")); }
}

function installDocument() {
  const elements = Object.fromEntries(["files", "opacity", "opacityVal", "fit", "status"].map(id => [id, new Element()]));
  globalThis.document = { getElementById: id => elements[id], createElement: tag => new Element(tag) };
  return elements;
}

class MockMap {
  constructor() { this.handlers = {}; this.sources = {}; this.layers = {}; this.paint = []; }
  on(event, handler) { (this.handlers[event] ||= []).push(handler); }
  off(event, handler) { this.handlers[event] = this.handlers[event].filter(item => item !== handler); }
  addControl() { }
  getLayer(id) { return this.layers[id]; }
  getSource(id) { return this.sources[id]; }
  removeLayer(id) { delete this.layers[id]; }
  removeSource(id) { delete this.sources[id]; }
  addSource(id, source) { this.sources[id] = source; }
  addLayer(layer) { this.layers[layer.id] = layer; }
  setPaintProperty(...args) { this.paint.push(args); }
  fitBounds(bounds) { this.fittedBounds = bounds; }
}

const popups = [];
class MockPopup {
  constructor() { popups.push(this); }
  setLngLat(point) { this.point = point; return this; }
  setText(text) { this.text = text; return this; }
  addTo() { this.open = true; return this; }
  isOpen() { return this.open; }
  remove() { this.open = false; }
  setDOMContent(content) { this.content = content; return this; }
}

function makeImage() {
  return {
    getGeoKeys: () => ({ GeographicTypeGeoKey: 4326, GTModelTypeGeoKey: 2, GTRasterTypeGeoKey: 1 }),
    getFileDirectory: () => ({}),
    getOrigin: () => [0, 4, 0], getResolution: () => [0.5, -0.5, 0],
    getWidth: () => 8, getHeight: () => 8, getSamplesPerPixel: () => 4,
    getGDALNoData: () => NaN,
    getGDALMetadata: sample => sample == null ? { start_year: "2016", end_year: "2025" } : [
      { DESCRIPTION: "days_daily_max_26_32", units: "days" },
      { DESCRIPTION: "days_daily_min_-40_-27", units: "days" },
      { DESCRIPTION: "record_max_utci_c", units: "degC" },
      { DESCRIPTION: "record_max_utci_year", units: "year" },
    ][sample],
    readRasters: async function (options) { this.lastRead = options; return new Float32Array([0, 71.5, 0, 2021]); },
  };
}

const repositoryConfig = {
  outputDir: "../output/", defaultBounds: [-25, 63, -13, 67.5], boundsByFile: {}, manualFiles: ["fallback.png"],
};

test("PNG sidecar supplies coordinates and keeps URLs relative to the page", async () => {
  const coordinates = [[0, 4], [4, 4], [4, 0], [0, 0]];
  const urls = [];
  const repository = createPngRepository(repositoryConfig, async url => {
    urls.push(url); return { ok: true, json: async () => ({ coordinates }) };
  });
  const placement = await repository.getPlacement("cold days.PNG");
  assert.equal(urls[0], "../output/cold%20days.json");
  assert.deepEqual(placement, { url: "../output/cold%20days.PNG", bounds: [0, 0, 4, 4], coordinates });
});

test("explicit PNG bounds avoid fetching a sidecar", async () => {
  const repository = createPngRepository({ ...repositoryConfig, boundsByFile: { "x.png": [0, 0, 1, 1] } }, () => assert.fail("Unexpected fetch"));
  assert.deepEqual((await repository.getPlacement("x.png")).coordinates, [[0, 1], [1, 1], [1, 0], [0, 0]]);
});

test("directory discovery deduplicates PNG names and ignores invalid links", async () => {
  globalThis.DOMParser = class {
    parseFromString() {
      return { querySelectorAll: () => [null, "b.png", "a.png?x=1", "b.png", "other.txt"].map(href => ({ getAttribute: () => href })) };
    }
  };
  const repository = createPngRepository(repositoryConfig, async () => ({ ok: true, text: async () => "listing" }));
  assert.deepEqual(await repository.listPngs(), ["a.png", "b.png"]);
});

test("unavailable directory listing uses a copy of the fallback list", async () => {
  const repository = createPngRepository(repositoryConfig, async () => { throw new Error("offline"); });
  const names = await repository.listPngs();
  assert.deepEqual(names, ["fallback.png"]);
  names.push("another.png");
  assert.deepEqual(repositoryConfig.manualFiles, ["fallback.png"]);
});

test("summary reader shares loading, reads all bands, and returns presentation data", async () => {
  let loads = 0;
  const image = makeImage();
  const reader = createSummaryReader("summary.tif", { fromUrl: async () => { loads++; return { getImage: async () => image }; } });
  const [point] = await Promise.all([reader.readPoint(1.25, 2.75), reader.readPoint(2, 3)]);
  assert.equal(loads, 1);
  assert.deepEqual(point.pixel, { column: 2, row: 2 });
  assert.deepEqual(point.pixelCenter, { longitude: 1.25, latitude: 2.75 });
  assert.deepEqual(point.period, { startYear: "2016", endYear: "2025" });
  assert.equal(point.bands.length, 4);
  assert.equal(point.image, undefined);
  assert.equal(image.lastRead.interleave, true);
  assert.deepEqual(image.lastRead.samples, [0, 1, 2, 3]);
  assert.equal(await reader.readPoint(5, 3), null);
});

test("failed summary loading can be retried", async () => {
  let attempts = 0;
  const reader = createSummaryReader("summary.tif", {
    fromUrl: async () => {
      if (++attempts === 1) throw new Error("offline");
      return { getImage: async () => makeImage() };
    },
  });
  await assert.rejects(reader.readPoint(1, 3), /offline/);
  assert.ok(await reader.readPoint(1, 3));
  assert.equal(attempts, 2);
});

test("reader rejects unsupported CRS", async () => {
  const image = makeImage();
  image.getGeoKeys = () => ({ ProjectedCSTypeGeoKey: 3857 });
  const reader = createSummaryReader("summary.tif", { fromUrl: async () => ({ getImage: async () => image }) });
  await assert.rejects(reader.readPoint(1, 3), /EPSG:4326/);
});

test("pixel lookup handles world wrapping and excludes east and south edges", () => {
  const summary = { origin: [0, 4], resolution: [0.5, -0.5], width: 8, height: 8 };
  assert.equal(pointToPixel(summary, 361.25, 2.75).column, 2);
  assert.equal(pointToPixel(summary, 4, 2), null);
  assert.equal(pointToPixel(summary, 2, 0), null);
  assert.equal(metadataValue({ DESCRIPTION: "test" }, "description"), "test");
});

test("formatting preserves current day labels, temperatures, years and nodata", () => {
  assert.equal(formatBandValue(71.5, "days", NaN), "71.5 days");
  assert.equal(formatBandValue(0, "degC", NaN), "0 °C");
  assert.equal(formatBandValue(2021, "year", NaN), "2021");
  assert.equal(formatBandValue(NaN, "days", NaN), "No data");
  assert.equal(formatBandValue(-9999, "days", -9999), "No data");
});

test("popup hides zero-day rows but retains zero-degree temperature records", async () => {
  installDocument();
  const reader = createSummaryReader("summary.tif", { fromUrl: async () => ({ getImage: async () => makeImage() }) });
  const content = buildPointContent(await reader.readPoint(1.25, 2.75));
  const table = content.children.find(child => child.tag === "table");
  const rows = table.children[1].children;
  assert.equal(rows.length, 3);
  assert.equal(rows[0].children[1].textContent, "71.5 days");
  assert.equal(rows[1].children[1].textContent, "0 °C");
});

test("overlay ignores stale image placement and uses the latest slider opacity", async () => {
  const pending = {};
  const map = new MockMap();

  const overlay = createPngOverlay(map, {
    getPlacements: name => new Promise(resolve => {
      pending[name] = resolve;
    }),
  });

  const first = overlay.showImage("first.png");
  const second = overlay.showImage("second.png", {
    opacity: 0.7,
    fit: false,
  });

  // A slider change during loading must apply to every new layer.
  overlay.setOpacity(0.3);

  const coordinates = [[0, 1], [1, 1], [1, 0], [0, 0]];
  const bounds = [0, 0, 1, 1];

  pending["second.png"]([
    {
      url: "azores/second.png",
      coordinates,
      bounds,
    },
    {
      url: "mainland/second.png",
      coordinates,
      bounds,
    },
  ]);
  await second;

  // The older selection finishes after the newer selection.
  pending["first.png"]([
    {
      url: "azores/first.png",
      coordinates,
      bounds,
    },
  ]);
  await first;

  const sources = Object.values(map.sources);
  const layers = Object.values(map.layers);

  assert.deepEqual(
    sources.map(source => source.url),
    ["azores/second.png", "mainland/second.png"],
  );

  assert.equal(layers.length, 2);

  for (const layer of layers) {
    assert.equal(layer.paint["raster-opacity"], 0.3);
    assert.ok(map.getSource(layer.source));
  }

  assert.equal(map.fittedBounds, undefined);
});

test("popup controller ignores stale clicks and supports cleanup", async () => {
  const pending = [];
  const map = new MockMap();
  const detach = attachPointPopup(map, {
    summaryReader: { readPoint: () => new Promise(resolve => pending.push(resolve)) },
    buildContent: point => point,
    maplibre: { Popup: MockPopup },
  });
  const click = map.handlers.click[0];
  const first = click({ lngLat: { lng: 1, lat: 2 } });
  const oldPopup = popups.at(-1);
  const second = click({ lngLat: { lng: 2, lat: 2 } });
  const currentPopup = popups.at(-1);
  pending[1]({ name: "latest" });
  await second;
  pending[0]({ name: "stale" });
  await first;
  assert.equal(oldPopup.content, undefined);
  assert.deepEqual(currentPopup.content, { name: "latest" });
  detach();
  assert.equal(map.handlers.click.length, 0);
  assert.equal(currentPopup.isOpen(), false);
});

test("sidebar wires selection, opacity, fit and empty-list status", async () => {
  const elements = installDocument();
  const selected = [];
  const opacities = [];
  const sidebar = initializeSidebar({ onSelectImage: (...args) => selected.push(args), onOpacityChange: value => opacities.push(value) });
  sidebar.setFiles(["cold.png", "heat.png"]);
  assert.equal(selected[0][0], "cold.png");
  await elements.files.children[1].click();
  assert.equal(selected[1][0], "heat.png");
  assert.equal(elements.files.children[0].classList.contains("active"), false);
  elements.opacity.value = "0.25";
  elements.opacity.listeners.input();
  assert.deepEqual(opacities, [0.25]);
  sidebar.setFiles([]);
  assert.match(elements.status.textContent, /No PNGs/);
});

test("thin entry starts the application and registers each handler once", async () => {
  const elements = installDocument();
  let createdMap;
  globalThis.maplibregl = {
    Map: class extends MockMap { constructor() { super(); createdMap = this; } },
    Popup: MockPopup, NavigationControl: class { }, ScaleControl: class { },
  };
  globalThis.GeoTIFF = { fromUrl: async () => ({ getImage: async () => makeImage() }) };
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({
      coordinates: [
        [0, 4],
        [4, 4],
        [4, 0],
        [0, 0],
      ],
    }),
  });
  await import("../index.js");
  assert.equal(createdMap.handlers.load.length, 1);
  assert.equal(createdMap.handlers.click.length, 1);
  assert.equal(createdMap.handlers.error.length, 1);
  await createdMap.handlers.load[0]();
  assert.equal(elements.files.children.length, 2);
  assert.deepEqual(
    elements.files.children.map(item => item.textContent),
    ["utci_cold_days.png", "utci_heat_days.png"],
  );

  // setFiles() starts selection asynchronously; explicitly await a selection
  // before testing the point popup.
  await elements.files.children[0].click();

  assert.equal(elements.status.textContent, "");
  await createdMap.handlers.click[0]({ lngLat: { lng: 1.25, lat: 2.75 } });
  assert.ok(popups.at(-1).content);
});

test("regional placement derives bounds from a coordinates-only sidecar", async () => {
  const urls = [];

  const repository = createRegionalRepository(
    {
      outputDir: "../output/map/",
      regions: ["azores"],
      pngFiles: ["utci_cold_days.png"],
      summaryTifName: "utci_summary.tif",
      geoTIFF: {},
    },
    async url => {
      urls.push(url);

      return {
        ok: true,
        json: async () => ({
          coordinates: [
            [0, 4],
            [4, 4],
            [4, 0],
            [0, 0],
          ],
        }),
      };
    },
  );

  assert.deepEqual(await repository.listPngs(), [
    "azores/utci_cold_days.png",
  ]);

  assert.deepEqual(
    await repository.getPlacement("azores/utci_cold_days.png"),
    {
      url: "../output/map/azores/utci_cold_days.png",
      bounds: [0, 0, 4, 4],
      coordinates: [
        [0, 4],
        [4, 4],
        [4, 0],
        [0, 0],
      ],
    },
  );

  assert.deepEqual(urls, [
    "../output/map/azores/utci_cold_days.json",
  ]);
});

test("regional placement rejects missing sidecar placement explicitly", async () => {
  const repository = createRegionalRepository(
    {
      outputDir: "../output/map/",
      regions: ["azores"],
      pngFiles: ["utci_cold_days.png"],
      summaryTifName: "utci_summary.tif",
      geoTIFF: {},
    },
    async () => ({
      ok: true,
      json: async () => ({}),
    }),
  );

  await assert.rejects(
    repository.getPlacement("azores/utci_cold_days.png"),
    /Missing or invalid placement.*azores\/utci_cold_days\.json/,
  );
});