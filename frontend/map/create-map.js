export function createMap(maplibre) {
  const map = new maplibre.Map({
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
  map.addControl(new maplibre.NavigationControl(), "top-right");
  map.addControl(new maplibre.ScaleControl());
  return map;
}
