/** Geographic math shared by the globe and its worker. All coordinates are WGS84. */
export type GeoPosition = [number, number]
export type ArcPosition = [number, number, number]

export function validPosition(position: number[]): boolean {
  return Number.isFinite(position[0]) && Number.isFinite(position[1]) && Math.abs(position[0]) <= 180 && Math.abs(position[1]) <= 90
}

/** Great-circle interpolation follows the short path across the date line. */
export function arcCoordinates(from: GeoPosition, to: GeoPosition, raised = true): ArcPosition[] {
  if (!validPosition(from) || !validPosition(to)) return []
  const rad = Math.PI / 180
  const vector = ([lng, lat]: GeoPosition) => [Math.cos(lat * rad) * Math.cos(lng * rad), Math.cos(lat * rad) * Math.sin(lng * rad), Math.sin(lat * rad)]
  const a = vector(from)
  const b = vector(to)
  const angle = Math.acos(Math.max(-1, Math.min(1, a.reduce((sum, value, i) => sum + value * b[i], 0))))
  if (angle < 0.000001) return [[...from, 2000], [...to, 2000]]
  // Select a stable tangent even for antipodal cities, where ordinary slerp divides by zero.
  let tangent = b.map((value, i) => value - a[i] * Math.cos(angle))
  let length = Math.hypot(...tangent)
  if (length < 0.000001) {
    const axis = Math.abs(a[2]) < 0.9 ? [0, 0, 1] : [0, 1, 0]
    tangent = [a[1] * axis[2] - a[2] * axis[1], a[2] * axis[0] - a[0] * axis[2], a[0] * axis[1] - a[1] * axis[0]]
    length = Math.hypot(...tangent)
  }
  tangent = tangent.map(value => value / length)
  const segments = Math.max(20, Math.min(96, Math.ceil(angle * 60)))
  const altitude = raised ? Math.min(1500000, Math.max(20000, angle * 6371000 * 0.16)) : 0
  return Array.from({ length: segments + 1 }, (_, i) => {
    if (i === 0) return [...from, raised ? 2500 : 0]
    if (i === segments) return [...to, raised ? 2500 : 0]
    const t = i / segments
    const p = a.map((value, k) => value * Math.cos(angle * t) + tangent[k] * Math.sin(angle * t))
    return [Math.atan2(p[1], p[0]) / rad, Math.atan2(p[2], Math.hypot(p[0], p[1])) / rad, 2500 + Math.sin(t * Math.PI) * altitude]
  }) as ArcPosition[]
}

/** Radial simplification preserves ring endpoints and caps expensive GPU geometry. */
export function simplifyRing(points: number[][], tolerance = 0.035): GeoPosition[] {
  const valid = points.filter(validPosition)
  if (valid.length < 3) return []
  const result: GeoPosition[] = [[valid[0][0], valid[0][1]]]
  let previous = valid[0]
  for (let i = 1; i < valid.length - 1; i++) {
    const point = valid[i]
    if (Math.hypot(point[0] - previous[0], point[1] - previous[1]) >= tolerance) {
      result.push([point[0], point[1]])
      previous = point
    }
  }
  result.push([valid[valid.length - 1][0], valid[valid.length - 1][1]])
  return result.length >= 3 ? result : []
}

export interface BoundaryLine { name: string; positions: GeoPosition[] }

export function boundaryLines(geojson: any): BoundaryLine[] {
  const lines: BoundaryLine[] = []
  for (const feature of geojson?.features || []) {
    const geometry = feature.geometry
    const polygons = geometry?.type === 'Polygon' ? [geometry.coordinates] : geometry?.type === 'MultiPolygon' ? geometry.coordinates : []
    for (const polygon of polygons) {
      for (const ring of polygon) {
        const positions = simplifyRing(ring)
        if (positions.length) lines.push({ name: feature.properties?.name || '', positions })
      }
    }
  }
  return lines
}
