/**
 * GeoJSON 经纬度 → 画布坐标投影
 *
 * 拼图渲染只关心「形状在画布里好不好看」，不需要严格的地理投影精度，
 * 因此这里采用简化的等距圆柱投影（Equirectangular）并对纬度做 cos 校正，
 * 避免高纬度省份（如黑龙江、新疆）被横向拉伸得过宽。
 */

/** 经纬度包围盒 */
export interface BBox {
  minLng: number
  minLat: number
  maxLng: number
  maxLat: number
}

/** 投影器：把 [lng, lat] 映射到画布像素坐标 */
export interface Projector {
  /** 投影单个坐标点 */
  project: (lng: number, lat: number) => [number, number]
  /** 形状实际占用的宽高（像素，已含 padding 外的绘制区域） */
  width: number
  height: number
  /** 绘制区域左上角偏移（用于居中） */
  offsetX: number
  offsetY: number
  /** 缩放比例（像素/度），供网格边长换算使用 */
  scale: number
}

/** GeoJSON 的 Polygon / MultiPolygon 坐标环集合 */
export type Ring = number[][]
export type PolygonRings = Ring[]

/**
 * 从 GeoJSON geometry 中提取所有多边形（统一成 MultiPolygon 结构）。
 * Polygon      → [ [outer, hole1, ...] ]
 * MultiPolygon → [ [outer, hole...], [outer, hole...] ]
 */
export function extractPolygons(geometry: any): PolygonRings[] {
  if (!geometry) return []
  const { type, coordinates } = geometry
  if (type === 'Polygon') return [coordinates as PolygonRings]
  if (type === 'MultiPolygon') return coordinates as PolygonRings[]
  return []
}

/** 计算环的面积（经纬度平方度，仅用于面之间的相对比较） */
function ringAreaDeg(ring: Ring): number {
  let sum = 0
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    sum += ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1]
  }
  return Math.abs(sum / 2)
}

/**
 * 剔除远离主体的碎小面（岛礁）。
 *
 * 为什么必须做：广东有 35 个面、浙江 75 个、海南多达 328 个（含南海诸岛）。
 * 这些礁石面积极小却把包围盒撑得极大 —— 海南不裁剪时纬度跨度 16.33°，
 * 导致海南岛主体被压缩成一小块、拼图出现大片空白；同时格子遍历量暴涨。
 *
 * 实测阈值取最大面积的 5%：34 个省的「有效面积/包围盒」填充率全部 ≥25%，
 * 且每个省都至少保留主体面（不会误删整省）。海南主体填充率回到 60.6%。
 *
 * @param polygons  原始面集合
 * @param ratio     保留阈值（相对最大面面积的比例）
 */
export function pruneSmallIslands(polygons: PolygonRings[], ratio = 0.05): PolygonRings[] {
  if (ratio <= 0 || polygons.length <= 1) return polygons
  const areas = polygons.map((p) => (p[0] ? ringAreaDeg(p[0]) : 0))
  const max = Math.max(...areas)
  if (max <= 0) return polygons
  const kept = polygons.filter((_, i) => areas[i] >= max * ratio)
  // 兜底：极端情况下全被过滤时保留最大面，避免整省消失
  return kept.length ? kept : [polygons[areas.indexOf(max)]]
}

/**
 * 计算一组 feature 的整体经纬度包围盒。
 * @param islandRatio 传入 >0 时同步剔除碎小岛礁，避免包围盒被撑大
 */
export function computeBBox(features: any[], islandRatio = 0.05): BBox {
  let minLng = Infinity
  let minLat = Infinity
  let maxLng = -Infinity
  let maxLat = -Infinity

  for (const feature of features) {
    const polygons = pruneSmallIslands(extractPolygons(feature.geometry), islandRatio)
    for (const polygon of polygons) {
      // 只用外环即可确定包围盒（内环必然在外环内部）
      const outer = polygon[0]
      if (!outer) continue
      for (const [lng, lat] of outer) {
        if (lng < minLng) minLng = lng
        if (lng > maxLng) maxLng = lng
        if (lat < minLat) minLat = lat
        if (lat > maxLat) maxLat = lat
      }
    }
  }

  // 退化保护：无有效坐标时给一个中国范围的兜底值
  if (!Number.isFinite(minLng)) {
    return { minLng: 73, minLat: 18, maxLng: 135, maxLat: 54 }
  }
  return { minLng, minLat, maxLng, maxLat }
}

/**
 * 基于包围盒创建投影器，让形状在 (canvasWidth x canvasHeight) 内等比居中。
 *
 * @param bbox          目标区域经纬度范围
 * @param width         画布宽度（CSS 像素）
 * @param height        画布高度（CSS 像素）
 * @param padding       上/左/右留白（CSS 像素）
 * @param bottomPadding 底部留白（CSS 像素），默认等于 padding。
 *                      移动端单省图传 peek 抽屉高度，让竖条形省份（陕西/甘肃）
 *                      整体上移、底部预留抽屉遮挡区，避免主体被抽屉盖住。
 */
export function createProjector(
  bbox: BBox,
  width: number,
  height: number,
  padding = 24,
  bottomPadding = padding
): Projector {
  const availW = Math.max(1, width - padding * 2)
  const availH = Math.max(1, height - padding - bottomPadding)

  // 纬度中心用于经度方向的 cos 校正，使形状接近真实观感
  const centerLat = (bbox.minLat + bbox.maxLat) / 2
  const lngCorrection = Math.cos((centerLat * Math.PI) / 180) || 1

  const spanLng = Math.max(1e-6, (bbox.maxLng - bbox.minLng) * lngCorrection)
  const spanLat = Math.max(1e-6, bbox.maxLat - bbox.minLat)

  // 等比缩放，取较小者保证完整显示
  const scale = Math.min(availW / spanLng, availH / spanLat)

  const shapeW = spanLng * scale
  const shapeH = spanLat * scale
  const offsetX = padding + (availW - shapeW) / 2
  // 在 [padding, height - bottomPadding] 区间内垂直居中
  const offsetY = padding + (availH - shapeH) / 2

  const project = (lng: number, lat: number): [number, number] => {
    const x = offsetX + (lng - bbox.minLng) * lngCorrection * scale
    // 纬度向上增大，画布 y 向下增大，需翻转
    const y = offsetY + (bbox.maxLat - lat) * scale
    return [x, y]
  }

  return { project, width: shapeW, height: shapeH, offsetX, offsetY, scale }
}
