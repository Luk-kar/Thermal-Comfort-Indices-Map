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

export function formatBandValue(value, units, nodata) {

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

export function buildPointContent(point) {
  const content = document.createElement("section");
  content.className = "point-data";

  appendText(content, "h3", "UTCI point data");

  appendText(
    content,
    "p",
    `${point.longitude.toFixed(5)}°, ${point.latitude.toFixed(5)}°`,
  );

  if (point.period.startYear != null && point.period.endYear != null) {
    appendText(
      content,
      "p",
      `Summary period: ${point.period.startYear}–${point.period.endYear}`,
    );
  }

  appendText(
    content,
    "p",
    `Source pixel: row ${point.pixel.row}, column ${point.pixel.column} (zero-based). ` +
    `Centre: ${point.pixelCenter.longitude.toFixed(5)}°, ${point.pixelCenter.latitude.toFixed(5)}°.`,
    "point-note",
  );

  const hasData = Array.from(point.values).some(
    value =>
      Number.isFinite(value) &&
      (point.nodata === null || value !== point.nodata),
  );

  if (!hasData) {
    appendText(content, "p", "No valid data at this source pixel.");
  }

  const table = document.createElement("table");
  const head = table.createTHead().insertRow();

  appendText(head, "th", "Metric");
  appendText(head, "th", "Value");

  const body = table.createTBody();

  point.bands.forEach((band, index) => {
    const value = point.values[index];

    const isDayCount =
      band.units === "days" ||
      band.name.startsWith("days_");

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
      point.nodata,
    );
  });

  content.appendChild(table);

  appendText(
    content,
    "p",
    "Day counts are median yearly counts. Record values and years cover the summary period. " +
    "Values come from the containing source pixel, without interpolation. " +
    "PNG coastline masking does not remove sea values from the original GeoTIFF.",
    "point-note",
  );

  return content;
}
