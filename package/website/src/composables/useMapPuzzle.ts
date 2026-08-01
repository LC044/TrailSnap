/**
 * 地图拼图状态管理
 *
 * 负责：GeoJSON 加载 → 照片拉取（按评分优选）→ 网格计算 → 照片分配。
 * 实际绘制交给 PuzzleCanvas 组件，本 composable 只产出「渲染所需的数据」。
 */

import { computed, ref, shallowRef } from 'vue'
import request from '@/utils/request'
import { albumService } from '@/api/album'
import { locationService } from '@/api/location'
import { buildRegionGeometry, filterRegionFeatures, shortenRegionName, type RegionGeometry } from '@/utils/mapPuzzle/geoPath'
import { computeBBox, createProjector } from '@/utils/mapPuzzle/geoProjection'
import { assignPhotos, buildGrid, shuffle, type PuzzleCell } from '@/utils/mapPuzzle/gridFill'

/** 拼图层级：全国 / 单省 */
export type PuzzleScope = 'nation' | 'province'

/** 选片策略；manual = 用户手动为每个格子挑照片（结果按省份存本地） */
export type PhotoStrategy = 'memory_score' | 'quality_score' | 'photo_time' | 'random' | 'manual'

export interface PuzzleConfig {
  /** 目标格子数量 */
  targetCount: number
  /** 是否显示区域名 */
  showLabel: boolean
  /** 选片策略 */
  strategy: PhotoStrategy
}

/** 全国图默认配置：格子密、不显示省名（太挤） */
export const NATION_DEFAULTS: PuzzleConfig = {
  targetCount: 600,
  showLabel: false,
  strategy: 'memory_score',
}

/** 单省默认配置：格子大、显示省名 */
export const PROVINCE_DEFAULTS: PuzzleConfig = {
  targetCount: 60,
  showLabel: true,
  strategy: 'memory_score',
}

/**
 * 全国图下每省最多拉取的照片数。
 *
 * 该值同时决定了「照片少时自动增大格子」的触发点：拉得太少会让大省
 * 明明有很多照片却被迫用大格子。实测新疆在 2000 格时需要约 354 格，
 * 故原取 400 以覆盖滑块上限；图片本身按需懒加载，不会一次性全部请求。
 *
 * 开启 dedup_similar 后会移除 30~40% 的 burst 近重复，故上调到 600，
 * 使去重后池子仍接近原来的 400 张。真正的「数量足够」由 buildGrid 的
 * 自适应放大 + assignPhotos 的循环复用兜底，这里只是减少格子被迫放大的程度。
 */
const NATION_PER_PROVINCE_LIMIT = 600
/** 单省图拉取上限，开启 dedup_similar 后上调到 800 留出去重 + 手动换图余量 */
const PROVINCE_FETCH_LIMIT = 800

/**
 * 碎小岛礁裁剪阈值（相对区域内最大面的面积比例）。
 *
 * 实测数据：广东 35 个面、浙江 75 个、海南 328 个（含南海诸岛）。
 * 不裁剪时这些礁石会把包围盒撑大 —— 海南纬度跨度从 12.84° 变成 16.33°，
 * 主体被压缩、拼图出现大片空白，且格子遍历量增加约 10 倍。
 * 取 5% 时 34 个省的填充率全部 ≥25%，且不会误删任何省的主体。
 */
const ISLAND_RATIO = 0.05

export function useMapPuzzle() {
  /** 当前层级 */
  const scope = ref<PuzzleScope>('nation')
  /** 单省模式下的目标省份全称，如「河南省」 */
  const activeProvince = ref<string | null>(null)

  const config = ref<PuzzleConfig>({ ...NATION_DEFAULTS })

  /** 画布尺寸（由容器 ResizeObserver driven） */
  const canvasWidth = ref(800)
  const canvasHeight = ref(600)

  /**
   * 移动端判定：单省图投影时底部预留 peek 抽屉高度，让竖条形省份（陕西/甘肃）
   * 整体上移，避免主体被底部抽屉遮挡。沿用 MainLayout 的 ref + resize 监听模式。
   */
  const isMobile = ref(false)
  const updateIsMobile = () => { isMobile.value = window.innerWidth < 768 }
  /**
   * 移动端单省图底部预留高度。
   * = peek 抽屉高度（128，与 LocationPuzzleView 的 PEEK_H 一致）
   * + 轮廓描边的 glow 外溢（renderer 的 shadowBlur=18）
   * + 少量余量（圆角/手柄阴影/格子描边），共 +24。
   * 不留这 24px 时，竖省最底一行格子的照片会被抽屉圆角 + 描边 glow 啃掉半张。
   */
  const SHEET_PEEK_H = 128 + 24

  const loading = ref(false)
  const error = ref<string | null>(null)

  /** 投影后的行政区几何（shallowRef：数据量大且整体替换，无需深响应） */
  const geometries = shallowRef<RegionGeometry[]>([])
  /** 网格格子 */
  const cells = shallowRef<PuzzleCell[]>([])
  /** 格子 → 照片 id */
  const assignments = shallowRef<(string | null)[]>([])

  /**
   * 手动模式下用户覆盖的格子（稀疏）。
   * key = 格子索引(string)，value = 照片 id 或 null（留空）。
   * 只记录被用户手动改过的格子，auto-assign 的结果不入此表。
   * 按省份持久化到 localStorage，刷新后恢复。
   */
  const manualAssignments = ref<Record<string, string | null>>({})

  const manualKey = (province: string) => `trailsnap:puzzle-manual:${province}`

  const loadManualAssignments = (province: string): Record<string, string | null> => {
    try {
      const raw = localStorage.getItem(manualKey(province))
      if (!raw) return {}
      const record = JSON.parse(raw)
      return record?.overrides ?? {}
    } catch {
      return {}
    }
  }

  const persistManualAssignments = (province: string) => {
    try {
      localStorage.setItem(
        manualKey(province),
        JSON.stringify({ overrides: manualAssignments.value })
      )
    } catch (e) {
      console.warn('[puzzle] 手动分配持久化失败', e)
    }
  }

  /**
   * 在 auto-assign 结果上叠加手动覆盖。
   *
   * 两遍策略，让 targetCount / 画布尺寸变化时自愈，无需存额外元数据：
   *   Pass 1: 原索引在范围内且未被占用 → 按索引套用（刷新场景保持布局不变）；
   *   Pass 2: 剩余（原索引越界或已被占用）→ first-fit 找空位塞（改精细度时尽力保留）。
   *
   * 返回新数组（[...base]），满足 assignments shallowRef 的整体替换要求。
   * `remapped` 是按新索引重写后的 overrides，供调用方同步内存状态。
   */
  const applyManualOverlay = (
    base: (string | null)[],
    overrides: Record<string, string | null>
  ): { assignments: (string | null)[]; remapped: Record<string, string | null> } => {
    const result = [...base]
    const overridden = new Set<number>()
    const applied = new Set<string>()
    const remapped: Record<string, string | null> = {}

    // Pass 1: 按原索引
    for (const [key, photoId] of Object.entries(overrides)) {
      const idx = Number(key)
      if (Number.isInteger(idx) && idx >= 0 && idx < result.length && !overridden.has(idx)) {
        result[idx] = photoId
        overridden.add(idx)
        remapped[String(idx)] = photoId
        applied.add(key)
      }
    }

    // Pass 2: first-fit
    for (const [key, photoId] of Object.entries(overrides)) {
      if (applied.has(key)) continue
      let target = -1
      for (let i = 0; i < result.length; i++) {
        if (!overridden.has(i)) {
          target = i
          break
        }
      }
      if (target >= 0) {
        result[target] = photoId
        overridden.add(target)
        remapped[String(target)] = photoId
      }
      // 否则无空位，丢弃该覆盖（极端情况：手选数 > 格子数）
    }

    return { assignments: result, remapped }
  }

  /** 省份全称 → 照片 id 池。拼图严格按省取图，不存在跨省的全局池。 */
  const photosByRegion = shallowRef<Map<string, string[]>>(new Map())

  /** 省份全称 → 照片数量，用于 hover 提示 */
  const regionCounts = shallowRef<Map<string, number>>(new Map())

  /** 原始 GeoJSON features 缓存，切换层级时避免重复请求 */
  const geoCache = new Map<string, any[]>()

  /** 有效照片数（去重后） */
  const usedPhotoCount = computed(() => new Set(assignments.value.filter(Boolean)).size)

  /**
   * 拉取 GeoJSON features。
   * 后端接口带一年强缓存，且无鉴权，这里再加一层内存缓存。
   */
  const fetchGeoFeatures = async (level: 'province' | 'city', parent?: string) => {
    const key = `${level}:${parent ?? ''}`
    const cached = geoCache.get(key)
    if (cached) return cached

    const params: Record<string, string> = { level, v: '2' }
    if (parent) params.parent = parent
    const res = await request.get('/api/medias/geojson', { params })
    // request 封装对 BaseResponse 解包，但 geojson 接口直接返回裸对象，两种都兼容
    const geoJson = (res as any)?.data ?? res
    // 必须过滤：原始数据含 8 个「境界线」MultiLineString，会撑坏包围盒
    const features = filterRegionFeatures(geoJson?.features ?? [])
    geoCache.set(key, features)
    return features
  }

  /**
   * 按策略拉取某个省份的照片 id。
   * 后端 order_by 已原生支持 memory_score / quality_score 且 nulls_last，
   * 因此高分优先时不必担心未做 AI 分析的照片挤占前排。
   */
  const fetchProvincePhotos = async (
    provinceName: string,
    limit: number,
    strategy: PhotoStrategy,
    startDate?: string,
    endDate?: string
  ): Promise<string[]> => {
    const filters: Record<string, any> = {
      // 用单数 province（ilike 模糊匹配）以兼容「河南省」与「河南」两种写法
      province: provinceName,
      file_type: 'image',
      // 按策略拉取后服务端再做 CLIP 相似度去重，避免相邻格子铺出近重复/burst 照片。
      // 无 embedding 的照片会原样透传，去重不截断，数量由 buildGrid 自适应放大兜底。
      dedup_similar: true,
    }
    if (startDate) filters.start_time = startDate
    if (endDate) filters.end_time = endDate

    if (strategy === 'memory_score' || strategy === 'quality_score') {
      filters.order_by = strategy
    } else if (strategy === 'photo_time') {
      filters.order_by = 'photo_time'
      filters.order_dir = 'desc'
    }

    try {
      const photos = await albumService.getAllPhotos(0, limit, filters)
      const ids = (photos ?? []).map((p: any) => p.id).filter(Boolean)
      // 随机策略在前端打乱，避免后端不支持随机排序
      return strategy === 'random' ? shuffle(ids) : ids
    } catch (e) {
      console.error(`[puzzle] 拉取 ${provinceName} 照片失败`, e)
      return []
    }
  }

  /** 重新计算网格与照片分配（几何或配置变化时调用，不重新请求数据） */
  const recompute = () => {
    if (!geometries.value.length) {
      cells.value = []
      assignments.value = []
      return
    }
    // 各省实际可用照片数，驱动「照片少时自动增大格子」
    const photoCounts = new Map<string, number>()
    for (const [name, ids] of photosByRegion.value) {
      photoCounts.set(name, ids.length)
    }

    const grid = buildGrid(geometries.value, {
      targetCount: config.value.targetCount,
      // 格子小于 9px 时照片内容已无法辨识，不如少铺几格
      minCellSize: scope.value === 'nation' ? 9 : 12,
      photoCounts,
      // 没去过的省不生成格子，保持轮廓内干净空白
      skipEmptyRegions: true,
    })
    cells.value = grid
    const base = assignPhotos(grid, photosByRegion.value)
    // 手动模式：在 auto-assign 之上叠加用户的手选覆盖（单省图才有手选）
    if (
      config.value.strategy === 'manual' &&
      scope.value === 'province' &&
      Object.keys(manualAssignments.value).length
    ) {
      const { assignments: final, remapped } = applyManualOverlay(base, manualAssignments.value)
      assignments.value = final
      // 同步内存中的索引（remap 后可能变了）；不在此落盘，落盘交给 setManualCell / loadProvince
      manualAssignments.value = remapped
    } else {
      assignments.value = base
    }
  }

  /** 依据当前画布尺寸重新投影几何（尺寸变化时调用） */
  const reproject = (features: any[]) => {
    // ISLAND_RATIO 必须在 computeBBox 与 buildRegionGeometry 间保持一致，
    // 否则包围盒与实际绘制的面不匹配，形状会偏移出画布。
    const bbox = computeBBox(features, ISLAND_RATIO)
    // 移动端单省图：底部多留 peek 抽屉高度，竖条形省份整体上移、不被抽屉遮挡。
    // 全国图/桌面端：均匀 padding（bottomPadding 默认等于 padding）。
    // updateIsMobile 兜底：首次 load 时 isMobile 尚未初始化，此处读最新值。
    updateIsMobile()
    const bottomPadding = isMobile.value && scope.value === 'province' ? SHEET_PEEK_H : 24
    const projector = createProjector(bbox, canvasWidth.value, canvasHeight.value, 24, bottomPadding)
    geometries.value = features.map((f) => buildRegionGeometry(f, projector, ISLAND_RATIO))
  }

  /** 当前使用的 features，用于尺寸变化时重新投影 */
  const activeFeatures = shallowRef<any[]>([])

  /** 加载全国拼图 */
  const loadNation = async (startDate?: string, endDate?: string) => {
    loading.value = true
    error.value = null
    try {
      const features = await fetchGeoFeatures('province')
      activeFeatures.value = features
      reproject(features)

      // 用分布接口一次拿到各省照片数，避免对 34 个省逐个试探
      const distribution = await locationService.getDistribution('province', startDate, endDate)
      const counts = new Map<string, number>()
      const nameToFull = new Map<string, string>()
      for (const f of features) {
        const full = f?.properties?.name
        if (!full) continue
        nameToFull.set(full, full)
        nameToFull.set(shortenRegionName(full), full)
      }
      for (const item of distribution ?? []) {
        const full = nameToFull.get(item.name) ?? nameToFull.get(shortenRegionName(item.name))
        if (full) counts.set(full, (counts.get(full) ?? 0) + item.count)
      }
      regionCounts.value = counts

      // 只对「有照片的省」发起请求，按照片数降序优先
      const targets = [...counts.entries()]
        .filter(([, count]) => count > 0)
        .sort((a, b) => b[1] - a[1])

      const poolMap = new Map<string, string[]>()
      // 分批并发，避免 34 个省同时发请求
      const BATCH = 6
      for (let i = 0; i < targets.length; i += BATCH) {
        const batch = targets.slice(i, i + BATCH)
        const results = await Promise.all(
          batch.map(([name]) =>
            fetchProvincePhotos(
              name,
              NATION_PER_PROVINCE_LIMIT,
              config.value.strategy,
              startDate,
              endDate
            )
          )
        )
        batch.forEach(([name], idx) => {
          const ids = results[idx]
          if (ids.length) poolMap.set(name, ids)
        })
      }
      photosByRegion.value = poolMap

      recompute()
    } catch (e: any) {
      console.error('[puzzle] 加载全国拼图失败', e)
      error.value = e?.message ?? '加载失败'
    } finally {
      loading.value = false
    }
  }

  /** 加载单省拼图 */
  const loadProvince = async (provinceName: string, startDate?: string, endDate?: string) => {
    loading.value = true
    error.value = null
    try {
      // 从全国 features 里挑出目标省，避免为单省再请求一次 geojson
      const allFeatures = await fetchGeoFeatures('province')
      const short = shortenRegionName(provinceName)
      const feature = allFeatures.find((f: any) => {
        const full = f?.properties?.name ?? ''
        return full === provinceName || shortenRegionName(full) === short
      })
      if (!feature) {
        error.value = `未找到「${provinceName}」的边界数据`
        geometries.value = []
        cells.value = []
        return
      }

      const fullName = feature.properties.name
      activeProvince.value = fullName
      activeFeatures.value = [feature]
      // 手动模式：进入省份时先恢复持久化的手选覆盖，recompute 才能立即套用
      manualAssignments.value =
        config.value.strategy === 'manual' ? loadManualAssignments(fullName) : {}
      reproject([feature])

      const ids = await fetchProvincePhotos(
        fullName,
        PROVINCE_FETCH_LIMIT,
        config.value.strategy,
        startDate,
        endDate
      )
      photosByRegion.value = new Map([[fullName, ids]])
      regionCounts.value = new Map([[fullName, ids.length]])

      recompute()
      // 手动模式：recompute 可能 remap 了索引，把对齐后的结果落盘一次
      if (config.value.strategy === 'manual') {
        persistManualAssignments(fullName)
      }
    } catch (e: any) {
      console.error('[puzzle] 加载单省拼图失败', e)
      error.value = e?.message ?? '加载失败'
    } finally {
      loading.value = false
    }
  }

  /** 画布尺寸变化：只重新投影 + 重算网格，不重新请求数据 */
  const resize = (width: number, height: number) => {
    if (width <= 0 || height <= 0) return
    // 变化小于 2px 时忽略，避免 ResizeObserver 抖动导致频繁重算
    const sizeChanged =
      Math.abs(width - canvasWidth.value) >= 2 || Math.abs(height - canvasHeight.value) >= 2
    // 同步移动端判定（跨档时底部留白策略需切换）
    updateIsMobile()
    if (!sizeChanged) return
    canvasWidth.value = width
    canvasHeight.value = height
    if (activeFeatures.value.length) {
      reproject(activeFeatures.value)
      recompute()
    }
  }

  /** 进入单省视图 */
  const drillDown = async (provinceName: string, startDate?: string, endDate?: string) => {
    scope.value = 'province'
    config.value = { ...PROVINCE_DEFAULTS, strategy: config.value.strategy }
    await loadProvince(provinceName, startDate, endDate)
  }

  /** 返回全国视图 */
  const drillUp = async (startDate?: string, endDate?: string) => {
    scope.value = 'nation'
    activeProvince.value = null
    config.value = { ...NATION_DEFAULTS, strategy: config.value.strategy }
    await loadNation(startDate, endDate)
  }

  /**
   * 替换某个格子的照片。
   *
   * 候选照片**只从该格子所属省份的照片池里取**，不跨省借图，
   * 与 assignPhotos 的严格归属规则保持一致。
   * 优先取当前画面里尚未用到的照片，避免换图后出现重复。
   */
  const replaceCellPhoto = (cellIndex: number, photoId?: string) => {
    const next = [...assignments.value]
    if (photoId) {
      next[cellIndex] = photoId
      assignments.value = next
      return
    }

    const cell = cells.value[cellIndex]
    const pool = cell ? photosByRegion.value.get(cell.regionName) : undefined
    if (!pool || !pool.length) return

    const used = new Set(next.filter(Boolean) as string[])
    const candidate = pool.find((id) => !used.has(id))
    // 本省照片已全部用上时，在本省池内随机取一张（仍不跨省）
    next[cellIndex] = candidate ?? pool[Math.floor(Math.random() * pool.length)] ?? null
    assignments.value = next
  }

  /** 剔除某个格子的照片（留空为占位色） */
  const removeCellPhoto = (cellIndex: number) => {
    const next = [...assignments.value]
    next[cellIndex] = null
    assignments.value = next
  }

  /**
   * 手动模式下设置某个格子的照片（或留空）。
   * 复用 replaceCellPhoto / removeCellPhoto 更新画面，同时记录覆盖并按省份持久化。
   * 仅在 strategy==='manual' 且单省 scope 下有意义。
   */
  const setManualCell = (cellIndex: number, photoId: string | null) => {
    if (photoId) {
      replaceCellPhoto(cellIndex, photoId)
    } else {
      removeCellPhoto(cellIndex)
    }
    if (scope.value === 'province' && activeProvince.value) {
      manualAssignments.value = {
        ...manualAssignments.value,
        [String(cellIndex)]: photoId,
      }
      persistManualAssignments(activeProvince.value)
    }
  }

  /**
   * 清除某个格子的手动覆盖，恢复 auto-assign。
   * 从 manualAssignments 删除该 key 并落盘，再用 replaceCellPhoto(auto-pick) 填一张。
   */
  const clearManualCell = (cellIndex: number) => {
    if (scope.value === 'province' && activeProvince.value) {
      const next = { ...manualAssignments.value }
      delete next[String(cellIndex)]
      manualAssignments.value = next
      persistManualAssignments(activeProvince.value)
    }
    // 不传 photoId → 走池内 auto-pick
    replaceCellPhoto(cellIndex)
  }

  /** 重新随机分配（换一批）。各省独立打乱，照片不会跨省流动。 */
  const reshuffle = () => {
    const seed = Date.now() & 0xffff
    const shuffledMap = new Map<string, string[]>()
    for (const [name, ids] of photosByRegion.value) {
      shuffledMap.set(name, shuffle(ids, seed))
    }
    photosByRegion.value = shuffledMap
    recompute()
  }

  return {
    // 状态
    scope,
    activeProvince,
    config,
    loading,
    error,
    geometries,
    cells,
    assignments,
    regionCounts,
    photosByRegion,
    canvasWidth,
    canvasHeight,
    usedPhotoCount,
    manualAssignments,
    // 动作
    loadNation,
    loadProvince,
    drillDown,
    drillUp,
    resize,
    recompute,
    replaceCellPhoto,
    removeCellPhoto,
    setManualCell,
    clearManualCell,
    reshuffle,
  }
}
