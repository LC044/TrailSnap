import type { TicketStatistics } from "@/utils/ticketStatistics";
import type { MapFeature } from "@/api/ticketStatistics";

export type MapSelection =
  | { type: "city"; name: string }
  | { type: "route"; from: string; to: string; directional: boolean }
  | null;
export interface MapViewport {
  center: [number, number];
  zoom: number;
}
export const nationalViewport = (): MapViewport => ({
  center: [104, 32],
  zoom: 1,
});
export function fitMapViewport(
  points: [number, number][],
  aspect = 1.8,
): MapViewport {
  const valid = points.filter((point) => point.every(Number.isFinite));
  if (!valid.length) return nationalViewport();
  const xs = valid.map((point) => point[0]),
    ys = valid.map((point) => point[1]);
  const xmin = Math.min(...xs),
    xmax = Math.max(...xs),
    ymin = Math.min(...ys),
    ymax = Math.max(...ys);
  const mapAspect = (64 * 0.75) / 51;
  const longitudeScale = Math.max(1, aspect / mapAspect);
  const latitudeScale = Math.max(1, mapAspect / Math.max(0.3, aspect));
  return {
    center: [(xmin + xmax) / 2, (ymin + ymax) / 2],
    zoom: Math.min(
      6,
      Math.max(
        1,
        Math.min(
          (64 * longitudeScale) / Math.max(10, (xmax - xmin) * 1.3),
          (51 * latitudeScale) / Math.max(8, (ymax - ymin) * 1.3),
        ),
      ),
    ),
  };
}
export function featureCenter(feature: MapFeature): [number, number] | null {
  const properties = feature.properties || {};
  const center = properties.cp || properties.center || properties.centroid;
  if (center && center.length >= 2 && center.slice(0, 2).every(Number.isFinite))
    return [center[0], center[1]];
  const geometry = feature.geometry;
  const rings =
    geometry.type === "MultiPolygon"
      ? (geometry.coordinates as number[][][][]).map((polygon) => polygon[0])
      : geometry.type === "Polygon"
        ? [(geometry.coordinates as number[][][])[0]]
        : [];
  let largest = 0,
    result: [number, number] | null = null;
  for (const ring of rings) {
    if (!ring?.length) continue;
    const xs = ring.map((point) => point[0]),
      ys = ring.map((point) => point[1]);
    const xmin = Math.min(...xs),
      xmax = Math.max(...xs),
      ymin = Math.min(...ys),
      ymax = Math.max(...ys);
    const area = (xmax - xmin) * (ymax - ymin);
    if (area > largest) {
      largest = area;
      result = [(xmin + xmax) / 2, (ymin + ymax) / 2];
    }
  }
  return result;
}
type Entry = TicketStatistics["entries"][number];
export function matchesMapSelection(entry: Entry, selection: MapSelection) {
  if (!selection) return true;
  if (selection.type === "city")
    return entry.from === selection.name || entry.to === selection.name;
  const [from, to] =
    entry.from === entry.to
      ? [entry.ticket.from, entry.ticket.to]
      : [entry.from, entry.to];
  return (
    (from === selection.from && to === selection.to) ||
    (!selection.directional && from === selection.to && to === selection.from)
  );
}
export function mapSelectionDetail(
  summary: TicketStatistics,
  selection: MapSelection,
) {
  const journeys = summary.journeys.filter((row) =>
    matchesMapSelection(row, selection),
  );
  const entries = summary.entries
    .filter((row) => matchesMapSelection(row, selection))
    .sort((a, b) => b.parsed.time.localeCompare(a.parsed.time));
  return {
    count: journeys.length,
    distance: Math.round(journeys.reduce((sum, row) => sum + row.distance, 0)),
    duration: journeys.reduce((sum, row) => sum + row.duration, 0),
    amount: entries.reduce((sum, row) => sum + row.cents, 0) / 100,
    tickets: entries.map((row) => row.ticket),
    cities: [...new Set(journeys.flatMap((row) => [row.from, row.to]))],
  };
}
export function sameMapSelection(a: MapSelection, b: MapSelection) {
  if (!a || !b) return a === b;
  if (a.type === "city" && b.type === "city") return a.name === b.name;
  if (
    a.type !== "route" ||
    b.type !== "route" ||
    a.directional !== b.directional
  )
    return false;
  return (
    (a.from === b.from && a.to === b.to) ||
    (!a.directional && a.from === b.to && a.to === b.from)
  );
}

export function directionalMapRoutes(summary: TicketStatistics) {
  const routes = new Map<string, { from: string; to: string; count: number }>();
  for (const row of summary.journeys) {
    const [from, to] =
      row.from === row.to
        ? [row.ticket.from, row.ticket.to]
        : [row.from, row.to];
    const key = JSON.stringify([from, to]);
    const route = routes.get(key) || { from, to, count: 0 };
    route.count++;
    routes.set(key, route);
  }
  return [...routes.values()];
}
