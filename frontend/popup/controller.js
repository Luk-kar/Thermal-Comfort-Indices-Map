export function attachPointPopup(map, { summaryReader, buildContent, maplibre }) {
  const state = { activePopup: null };

  async function handleClick(event) {

    if (state.activePopup) state.activePopup.remove();

    const popup = new maplibre.Popup({ maxWidth: "min(520px, 90vw)" })
      .setLngLat(event.lngLat)
      .setText("Loading point data…")
      .addTo(map);
    state.activePopup = popup;

    const isCurrent = () => state.activePopup === popup && popup.isOpen();

    try {

      const point = await summaryReader.readPoint(event.lngLat.lng, event.lngLat.lat);
      if (!isCurrent()) return;
      if (!point) {
        popup.setText("This point is outside the summary GeoTIFF extent.");
        return;
      }

      popup.setDOMContent(buildContent(point));

    } catch (error) {
      console.error("Point query failed:", error);
      if (isCurrent()) popup.setText(`Could not read point data: ${error.message || String(error)}`);
    }
  }

  map.on("click", handleClick);

  return function detachPointPopup() {

    map.off("click", handleClick);
    if (state.activePopup) state.activePopup.remove();
    state.activePopup = null;
  };
}
