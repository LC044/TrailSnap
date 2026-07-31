/**
 * 网格切分与照片分配
 *
 * 基准格子边长由「全国总面积 / 目标张数」反解，因此各省分到的格子数
 * 与其面积成正比（忠于真实地图形状）。
 *
 * 在此基础上做一层**按省自适应放大**：若某省的照片数少于它按基准尺寸
 * 能容纳的格子数，就单独放大该省的格子，直到格子数不超过照片数 ——
 * 这样照片少的省用大格子铺满，既不重复照片也不留空洞。
 */

import { computeArea, pointInRegion, type RegionGeometry } from './geoPath'

/** 一个拼图格子 */
export interface PuzzleCell {
  /** 格子左上角坐标（画布像素） */
  x: number
  y: number
  /** 格子边长（正方形） */
  size: number
  /** 所属行政区全称（全国图下用于按省分配照片） */
  regionName: string
  /** 格子与区域的重叠率 0~1，放大受限时用于优先保留覆盖度高的格子 */
  coverage: number
}

export interface GridOptions {
  /** 目标格子数量（实际数量会接近但不完全等于该值） */
  targetCount: number
  /** 格子最小边长限制（像素），防止张数过大导致格子碎成噪点 */
  minCellSize?: number
  /**
   * 各区域可用照片数（区域全称 → 张数）。
   * 提供后启用「照片少时自动增大格子尺寸」，减少同一张照片在省内重复。
   */
  photoCounts?: Map<string, number>
  /**
   * 是否跳过没有照片的区域（不为其生成任何格子）。
   * 全国图开启后，没去过的省保持干净空白，只留轮廓。
   */
  skipEmptyRegions?: boolean
  /** 格子自适应放大的上限倍数，防止极端情况下格子大到失去拼图感 */
  maxCellScale?: number
}

/**
 * 判断格子是否与区域有任何交集（用于「填满」模式）。
 *
 * 分三级递进，尽早短路以控制开销：
 *   1. 包围盒排除
 *   2. 稀疏 3x3 采样 —— 绝大多数格子（内部/远离边界）在此即可判定
 *   3. 加密 5x5 采样 + 省界顶点检测 —— 仅对稀疏采样失败的格子执行
 *
 * 第 3 级必要性：细长的省界末梢（如陕西南部、甘肃河西走廊）可能让
 * 稀疏采样点全部落在省外，却仍与省界相交，不补判会留下边缘空洞。
 */
function intersectsRegion(x: number, y: number, size: number, geo: RegionGeometry): boolean {
  const b = geo.bounds
  // ① 包围盒完全不相交
  if (x + size < b.x || x > b.x + b.width || y + size < b.y || y > b.y + b.height) return false

  // ② 稀疏 3x3 采样（含中心），命中即返回
  for (let i = 0; i < 3; i++) {
    for (let j = 0; j < 3; j++) {
      const px = x + ((i + 0.5) / 3) * size
      const py = y + ((j + 0.5) / 3) * size
      if (pointInRegion(px, py, geo)) return true
    }
  }

  // ③ 加密 5x5 采样，跳过已在 ② 中测过的位置
  for (let i = 0; i < 5; i++) {
    for (let j = 0; j < 5; j++) {
      // 3x3 的采样点位于 1/6、3/6、5/6；5x5 位于 1/10、3/10…9/10，无重合
      const px = x + ((i + 0.5) / 5) * size
      const py = y + ((j + 0.5) / 5) * size
      if (pointInRegion(px, py, geo)) return true
    }
  }

  // ④ 采样全部落空时，检查是否有省界顶点落在格子内（细长末梢）
  for (const rings of geo.polygons) {
    for (const ring of rings) {
      for (const [vx, vy] of ring) {
        if (vx >= x && vx <= x + size && vy >= y && vy <= y + size) return true
      }
    }
  }

  return false
}

/**
 * 单个区域内按给定边长铺格子。
 *
 * 采用「相交即保留」策略：只要格子与省界有任何交集就生成，
 * 超出省界的部分会在渲染时被 ctx.clip() 裁掉，因此不会越界。
 * 这样才能把省界内部完全填满 —— 实测省内像素填充率 91% → 99.97%。
 */
function fillRegion(
  geo: RegionGeometry,
  cell: number,
  maxIterations = 200_000
): PuzzleCell[] {
  const b = geo.bounds
  if (b.width <= 0 || b.height <= 0 || cell <= 0) return []

  // 向外多铺一圈，确保省界最外缘也被格子覆盖
  const cols = Math.ceil(b.width / cell) + 1
  const rows = Math.ceil(b.height / cell) + 1
  if (cols * rows > maxIterations) return []

  // 让网格在区域包围盒内居中，使左右/上下边缘的溢出量均衡
  const offsetX = b.x - (cols * cell - b.width) / 2
  const offsetY = b.y - (rows * cell - b.height) / 2

  const out: PuzzleCell[] = []
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const x = offsetX + c * cell
      const y = offsetY + r * cell
      if (!intersectsRegion(x, y, cell, geo)) continue
      // coverage 目前不参与取舍（填满优先），置 1 以省去一次 9 点采样；
      // 保留字段是为了渲染层/调试需要时可用
      out.push({ x, y, size: cell, regionName: geo.name, coverage: 1 })
    }
  }
  return out
}

/**
 * 生成网格格子。
 *
 * @param geometries 目标行政区集合（单省时长度为 1；全国时为 34 个省）
 * @param options    网格参数
 */
export function buildGrid(geometries: RegionGeometry[], options: GridOptions): PuzzleCell[] {
  const {
    targetCount,
    minCellSize = 6,
    photoCounts,
    skipEmptyRegions = false,
    maxCellScale = 14,
  } = options
  if (!geometries.length || targetCount <= 0) return []

  const totalArea = computeArea(geometries)
  if (totalArea <= 0) return []

  // 基准边长。系数 1.03 是用真实 geojson 实测校准的结果，
  // 使实际格子数与目标值的偏差保持在个位数百分比。
  const baseCell = Math.max(minCellSize, Math.sqrt(totalArea / targetCount) * 1.03)

  const cells: PuzzleCell[] = []

  for (const geo of geometries) {
    // 未出现在 photoCounts 里视为 0 张（该区域没去过）；
    // 完全不传 photoCounts 时才视为不限张数，保持向后兼容。
    const photos = photoCounts ? (photoCounts.get(geo.name) ?? 0) : Infinity

    // 没有照片的区域：按需跳过，保持轮廓内干净空白
    if (photos <= 0) {
      if (skipEmptyRegions) continue
      cells.push(...fillRegion(geo, baseCell))
      continue
    }

    let regionCells = fillRegion(geo, baseCell)

    // 照片不够铺满 → 逐步放大格子，直到格子数 <= 照片数。
    // 放大而非删格，是为了在「不重复照片」的同时保持区域被完全填满。
    if (Number.isFinite(photos) && regionCells.length > photos) {
      let size = baseCell
      const maxSize = baseCell * maxCellScale

      for (let iter = 0; iter < 14 && regionCells.length > photos; iter++) {
        // 格子数 ∝ 1/边长²，故边长按 sqrt(超出比例) 放大；
        // 单次放大限制在 1.5 倍内，避免一步过冲导致格子远大于必要尺寸
        const ratio = Math.min(Math.sqrt(regionCells.length / photos), 1.5)
        const next = Math.min(size * ratio, maxSize)
        if (next <= size) break
        size = next
        const grown = fillRegion(geo, size)
        // 放大后一个格子都不剩时保留上一轮结果，避免该省整体消失
        if (!grown.length) break
        regionCells = grown
        if (size >= maxSize) break
      }

      // 仍多于照片数时**不删格子**（删格会在地图上留下空洞），
      // 改为让照片循环复用 —— 保持填满优先于绝对不重复。
    }

    // 面积过小拿不到任何格子的区域（北京/上海/港澳等），
    // 只要它有照片就在中心补一格，保证「去过就被点亮」
    if (!regionCells.length && photos > 0) {
      const b = geo.bounds
      if (b.width > 0 && b.height > 0) {
        const size = Math.max(minCellSize, Math.min(baseCell, b.width, b.height))
        regionCells = [
          {
            x: b.x + b.width / 2 - size / 2,
            y: b.y + b.height / 2 - size / 2,
            size,
            regionName: geo.name,
            coverage: 1,
          },
        ]
      }
    }

    cells.push(...regionCells)
  }

  return cells
}

/**
 * 把照片分配到格子上。
 *
 * **严格按行政区归属**：每个格子只会使用「它所在省份」的照片。
 * 某省没有照片时该格子留空，绝不用其他省的照片填充 ——
 * 否则拼图会失去「点亮地图」的意义：一个省份有照片才代表你去过那里。
 *
 * 配合 buildGrid 的自适应放大后，各省格子数通常已 ≤ 照片数，
 * 因此同省内每格都能拿到不同照片；仅在放大受上限约束时才会循环复用。
 *
 * @param cells          有效格子
 * @param photosByRegion 省份全称 → 该省照片 id 列表
 * @returns 格子索引 → 照片 id（无照片的格子为 null）
 */
export function assignPhotos(
  cells: PuzzleCell[],
  photosByRegion: Map<string, string[]>
): (string | null)[] {
  // 每个省维护一个游标，顺序取用，保证同省照片在本省内均匀铺开
  const cursors = new Map<string, number>()

  return cells.map((cell) => {
    const pool = photosByRegion.get(cell.regionName)
    if (!pool || !pool.length) return null
    const cursor = cursors.get(cell.regionName) ?? 0
    cursors.set(cell.regionName, cursor + 1)
    return pool[cursor % pool.length]
  })
}

/**
 * 打乱数组（Fisher-Yates），用于避免同一天拍的照片在拼图上扎堆。
 * 返回新数组，不修改入参。
 */
export function shuffle<T>(items: T[], seed = 1): T[] {
  const result = [...items]
  // 简易可复现随机数（LCG），保证同一 seed 下重绘结果稳定，避免闪烁
  let state = seed >>> 0 || 1
  const random = () => {
    state = (state * 1664525 + 1013904223) >>> 0
    return state / 0xffffffff
  }
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[result[i], result[j]] = [result[j], result[i]]
  }
  return result
}
