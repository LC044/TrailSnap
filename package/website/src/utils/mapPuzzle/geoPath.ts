/**
 * GeoJSON → Path2D 转换与几何判定
 *
 * 拼图效果的核心是 ctx.clip(path)：先把行政区轮廓设为裁剪区域，
 * 再往里铺照片，边缘照片就会被自动切成省界形状。
 */

import {
  extractPolygons,
  pruneSmallIslands,
  type PolygonRings,
  type Projector,
} from './geoProjection'

/** 一个行政区的几何信息 */
export interface RegionGeometry {
  /** 完整行政区名，如「河南省」 */
  name: string
  /** 国标编码（GeoJSON 字段名为 gb，形如 156410000，前 3 位是国家码 156） */
  code: string
  /** 已投影到画布坐标的多边形集合 */
  polygons: PolygonRings[]
  /** 该区域在画布中的像素包围盒 */
  bounds: { x: number; y: number; width: number; height: number }
}

/**
 * 把 GeoJSON feature 投影成画布坐标的几何对象。
 * 注意：投影后坐标即为像素，后续判定/绘制都在像素空间进行。
 *
 * @param islandRatio 碎小岛礁裁剪阈值，需与 computeBBox 保持一致，
 *                    否则包围盒与实际绘制的面不匹配会导致形状偏移。
 */
export function buildRegionGeometry(
  feature: any,
  projector: Projector,
  islandRatio = 0.05
): RegionGeometry {
  const polygons: PolygonRings[] = []
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity

  const source = pruneSmallIslands(extractPolygons(feature.geometry), islandRatio)
  for (const polygon of source) {
    const projectedRings: PolygonRings = []
    for (const ring of polygon) {
      const projectedRing: number[][] = []
      for (const [lng, lat] of ring) {
        const [x, y] = projector.project(lng, lat)
        projectedRing.push([x, y])
        if (x < minX) minX = x
        if (x > maxX) maxX = x
        if (y < minY) minY = y
        if (y > maxY) maxY = y
      }
      projectedRings.push(projectedRing)
    }
    polygons.push(projectedRings)
  }

  if (!Number.isFinite(minX)) {
    minX = minY = maxX = maxY = 0
  }

  return {
    name: feature?.properties?.name ?? '',
    code: feature?.properties?.gb ?? '',
    polygons,
    bounds: { x: minX, y: minY, width: maxX - minX, height: maxY - minY },
  }
}

/**
 * 构建 Path2D。
 * 外环与内环（孔洞）都加入同一个 Path，配合 'evenodd' 填充规则，
 * 内环会自动被挖空（例如被完全包围的飞地/湖泊）。
 */
export function buildPath2D(geometries: RegionGeometry[]): Path2D {
  const path = new Path2D()
  for (const geo of geometries) {
    for (const rings of geo.polygons) {
      for (const ring of rings) {
        if (ring.length < 2) continue
        path.moveTo(ring[0][0], ring[0][1])
        for (let i = 1; i < ring.length; i++) {
          path.lineTo(ring[i][0], ring[i][1])
        }
        path.closePath()
      }
    }
  }
  return path
}

/**
 * 射线法判断点是否在多边形内（含孔洞处理）。
 * 命中外环记 true，落在孔洞内则取反 → 最终等价于 even-odd 规则。
 */
function pointInRing(x: number, y: number, ring: number[][]): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0]
    const yi = ring[i][1]
    const xj = ring[j][0]
    const yj = ring[j][1]
    // 判断水平射线是否穿过边 (i, j)
    const intersect =
      yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi + Number.EPSILON) + xi
    if (intersect) inside = !inside
  }
  return inside
}

// ---------------------------------------------------------------------------
// 点在多边形内判定的加速索引
//
// 朴素射线法每次要遍历该省的所有边。实测新疆有 8556 个顶点、全国共 68519 个，
// 在密集网格下（3000 格档位）会成为瓶颈（单次 buildGrid 耗时 2.6s）。
//
// 这里按 Y 轴把边分桶：水平扫描线只可能与「跨越该 Y 值」的边相交，
// 因此只需检测落在对应桶内的边，把每次判定的边数从 O(全部边) 降到 O(局部边)。
// ---------------------------------------------------------------------------

/** 一条边的紧凑表示（避免对象属性访问开销） */
interface EdgeIndex {
  /** 每条边 4 个数：x0, y0, x1, y1 */
  edges: Float64Array
  /** 桶数组，每个桶存边在 edges 中的起始下标 */
  buckets: Int32Array[]
  minY: number
  /** 1 / 桶高度，乘法比除法快 */
  invBucketH: number
  bucketCount: number
  /** 该环是否为孔洞 */
  isHole: boolean
}

/** 按 Y 轴分桶构建边索引 */
function buildEdgeIndex(ring: number[][], isHole: boolean): EdgeIndex {
  const n = ring.length
  const edges = new Float64Array(n * 4)
  let minY = Infinity
  let maxY = -Infinity

  for (let i = 0, j = n - 1; i < n; j = i++) {
    const o = i * 4
    edges[o] = ring[j][0]
    edges[o + 1] = ring[j][1]
    edges[o + 2] = ring[i][0]
    edges[o + 3] = ring[i][1]
    const y0 = ring[j][1]
    const y1 = ring[i][1]
    if (y0 < minY) minY = y0
    if (y0 > maxY) maxY = y0
    if (y1 < minY) minY = y1
    if (y1 > maxY) maxY = y1
  }

  // 桶数按边数开方量级选取，兼顾内存与命中率
  const bucketCount = Math.max(1, Math.min(512, Math.ceil(Math.sqrt(n))))
  const height = Math.max(1e-9, maxY - minY)
  const bucketH = height / bucketCount
  const invBucketH = 1 / bucketH

  // 先统计每桶边数，再一次性分配（避免动态数组扩容）
  const counts = new Int32Array(bucketCount)
  for (let i = 0; i < n; i++) {
    const o = i * 4
    const ya = edges[o + 1]
    const yb = edges[o + 3]
    const lo = Math.min(ya, yb)
    const hi = Math.max(ya, yb)
    let b0 = Math.floor((lo - minY) * invBucketH)
    let b1 = Math.floor((hi - minY) * invBucketH)
    if (b0 < 0) b0 = 0
    if (b1 >= bucketCount) b1 = bucketCount - 1
    for (let b = b0; b <= b1; b++) counts[b]++
  }

  const buckets: Int32Array[] = new Array(bucketCount)
  for (let b = 0; b < bucketCount; b++) buckets[b] = new Int32Array(counts[b])
  const cursors = new Int32Array(bucketCount)

  for (let i = 0; i < n; i++) {
    const o = i * 4
    const ya = edges[o + 1]
    const yb = edges[o + 3]
    const lo = Math.min(ya, yb)
    const hi = Math.max(ya, yb)
    let b0 = Math.floor((lo - minY) * invBucketH)
    let b1 = Math.floor((hi - minY) * invBucketH)
    if (b0 < 0) b0 = 0
    if (b1 >= bucketCount) b1 = bucketCount - 1
    for (let b = b0; b <= b1; b++) buckets[b][cursors[b]++] = o
  }

  return { edges, buckets, minY, invBucketH, bucketCount, isHole }
}

/** 借助边索引做射线法判定 */
function pointInIndexedRing(x: number, y: number, idx: EdgeIndex): boolean {
  let b = Math.floor((y - idx.minY) * idx.invBucketH)
  if (b < 0 || b >= idx.bucketCount) return false
  const bucket = idx.buckets[b]
  const edges = idx.edges
  let inside = false
  for (let k = 0; k < bucket.length; k++) {
    const o = bucket[k]
    const xj = edges[o]
    const yj = edges[o + 1]
    const xi = edges[o + 2]
    const yi = edges[o + 3]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi + Number.EPSILON) + xi) {
      inside = !inside
    }
  }
  return inside
}

/** 每个区域一组索引：外层数组对应 polygons，内层对应该 polygon 的环 */
const indexCache = new WeakMap<RegionGeometry, EdgeIndex[][]>()

function getIndex(geo: RegionGeometry): EdgeIndex[][] {
  let cached = indexCache.get(geo)
  if (cached) return cached
  cached = geo.polygons.map((rings) => rings.map((ring, i) => buildEdgeIndex(ring, i > 0)))
  indexCache.set(geo, cached)
  return cached
}

/**
 * 判断点是否落在某个行政区内部（考虑孔洞）。
 * 首次调用会为该区域构建 Y 轴边索引并缓存（按几何对象弱引用，
 * 几何随画布尺寸变化重建时旧索引会自动被回收）。
 */
export function pointInRegion(x: number, y: number, geo: RegionGeometry): boolean {
  const index = getIndex(geo)
  for (let p = 0; p < index.length; p++) {
    const rings = index[p]
    const outer = rings[0]
    if (!outer || !pointInIndexedRing(x, y, outer)) continue
    // 命中外环后，检查是否落在任一孔洞里
    let inHole = false
    for (let h = 1; h < rings.length; h++) {
      if (pointInIndexedRing(x, y, rings[h])) {
        inHole = true
        break
      }
    }
    if (!inHole) return true
  }
  return false
}

/** 判断点是否落在一组行政区中的任意一个内部，返回命中的区域 */
export function findRegionAt(
  x: number,
  y: number,
  geometries: RegionGeometry[]
): RegionGeometry | null {
  for (const geo of geometries) {
    // 先用包围盒快速排除，避免对每个省都跑射线法
    const b = geo.bounds
    if (x < b.x || x > b.x + b.width || y < b.y || y > b.y + b.height) continue
    if (pointInRegion(x, y, geo)) return geo
  }
  return null
}

/** 计算多边形面积（像素²，用于反解网格边长），带孔洞扣除 */
export function computeArea(geometries: RegionGeometry[]): number {
  let area = 0
  for (const geo of geometries) {
    for (const rings of geo.polygons) {
      rings.forEach((ring, index) => {
        // 鞋带公式求有向面积
        let sum = 0
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
          sum += ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1]
        }
        const ringArea = Math.abs(sum / 2)
        // 外环加，内环（孔洞）减
        area += index === 0 ? ringArea : -ringArea
      })
    }
  }
  return Math.max(0, area)
}

/**
 * 行政区名称归一化，用于把 GeoJSON 全称与数据库/接口返回的简称对齐。
 * 与 MapContainer.vue / media.py 中的处理保持一致。
 */
const ADMIN_SUFFIX_REGEX =
  /(省|市|自治区|特别行政区|回族自治区|壮族自治区|维吾尔自治区|自治州|地区|盟|县|区)$/

export function shortenRegionName(name: string): string {
  if (!name) return ''
  return name.replace(ADMIN_SUFFIX_REGEX, '') || name
}

/**
 * 过滤出可用于拼图的行政区 feature。
 *
 * 后端 geojson 里混有 8 个名为「境界线」的 MultiLineString（国界/未定国界绘制用），
 * 它们没有 gb 编码、也不是面要素。若不剔除：
 *   1. 会把包围盒撑大（境界线延伸到国境外），导致省份形状被压缩偏移；
 *   2. extractPolygons 返回空数组，白占一个几何位。
 * 因此这里只保留 Polygon / MultiPolygon 且带 gb 编码的要素。
 */
export function filterRegionFeatures(features: any[]): any[] {
  return (features ?? []).filter((f) => {
    const type = f?.geometry?.type
    if (type !== 'Polygon' && type !== 'MultiPolygon') return false
    const name = f?.properties?.name
    if (!name || name === '境界线') return false
    return true
  })
}

/**
 * 构建「简称 → 全称」映射表，便于用统计接口返回的名字反查 GeoJSON feature。
 */
export function buildNameMap(features: any[]): Record<string, string> {
  const map: Record<string, string> = {}
  for (const feature of features) {
    const fullName: string = feature?.properties?.name
    if (!fullName) continue
    map[fullName] = fullName
    const short = shortenRegionName(fullName)
    if (short && short !== fullName) map[short] = fullName
  }
  return map
}
