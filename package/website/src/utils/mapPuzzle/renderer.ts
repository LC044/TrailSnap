/**
 * 拼图 Canvas 渲染器
 *
 * 渲染顺序（顺序很关键）：
 *   1. 清空 + 背景
 *   2. save() → clip(轮廓 Path2D) → 铺照片格子 → restore()
 *   3. 轮廓描边 / 外发光
 *   4. 高亮区域（hover）
 *   5. 区域名称文字
 *
 * 第 2 步先 clip 再画照片，边缘格子会被自动切成省界形状，
 * 这正是「照片拼成地图」效果的来源。
 */

import { buildPath2D, type RegionGeometry } from './geoPath'
import type { PuzzleCell } from './gridFill'

export interface RenderTheme {
  /** 画布背景色；传 null 表示透明背景 */
  background: string | null
  /** 已点亮区域的轮廓描边色 */
  stroke: string
  /** 描边宽度 */
  strokeWidth: number
  /** 未点亮（无照片）区域的轮廓色，应明显淡于 stroke */
  unlitStroke: string
  /** 外发光颜色，null 关闭 */
  glow: string | null
  /** 照片加载中的占位格子颜色 */
  placeholder: string
  /** 区域名称文字颜色 */
  labelColor: string
  /** 区域名称描边色（保证在照片上可读） */
  labelStroke: string
}

export interface RenderOptions {
  /** 是否显示区域名称 */
  showLabel: boolean
  /** 标签字号（像素）；不传则按区域尺寸自适应 */
  labelSize?: number
  /** hover 高亮的区域名称 */
  hoverRegion?: string | null
  /**
   * 有照片（已点亮）的区域名集合。
   * 提供后未点亮的区域只画淡描边、不显示名称，与已点亮区域形成对比。
   */
  litRegions?: Set<string>
  theme: RenderTheme
}

/** 图片取用回调：返回已解码的图片，未加载完成时返回 undefined */
export type ImageResolver = (photoId: string) => HTMLImageElement | ImageBitmap | undefined

/** 默认亮色主题 */
export const LIGHT_THEME: RenderTheme = {
  background: null,
  stroke: 'rgba(255,255,255,0.9)',
  strokeWidth: 1.5,
  unlitStroke: 'rgba(148,163,184,0.45)',
  glow: null,
  placeholder: 'rgba(148,163,184,0.25)',
  labelColor: 'rgba(255,255,255,0.95)',
  labelStroke: 'rgba(15,23,42,0.55)',
}

/** 默认暗色主题 */
export const DARK_THEME: RenderTheme = {
  background: null,
  stroke: 'rgba(255,255,255,0.75)',
  strokeWidth: 1.5,
  unlitStroke: 'rgba(100,116,139,0.5)',
  glow: null,
  placeholder: 'rgba(71,85,105,0.35)',
  labelColor: 'rgba(255,255,255,0.95)',
  labelStroke: 'rgba(0,0,0,0.6)',
}

/**
 * 以 object-fit: cover 的语义把图片绘制到目标矩形：
 * 按短边填满并居中裁剪，避免照片被拉伸变形。
 */
function drawImageCover(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement | ImageBitmap,
  dx: number,
  dy: number,
  dw: number,
  dh: number
) {
  const iw = (img as HTMLImageElement).naturalWidth ?? (img as ImageBitmap).width
  const ih = (img as HTMLImageElement).naturalHeight ?? (img as ImageBitmap).height
  if (!iw || !ih) return

  const scale = Math.max(dw / iw, dh / ih)
  const sw = dw / scale
  const sh = dh / scale
  const sx = (iw - sw) / 2
  const sy = (ih - sh) / 2
  ctx.drawImage(img as CanvasImageSource, sx, sy, sw, sh, dx, dy, dw, dh)
}

/**
 * 描边区域轮廓。
 *
 * 已点亮（有照片）的区域用主题色实线 + 可选外发光；
 * 未点亮的区域用更细更淡的线，只作为「中国版图」的参照存在，
 * 这样视觉重心落在你真正去过的地方。
 */
function strokeRegions(
  ctx: CanvasRenderingContext2D,
  geometries: RegionGeometry[],
  theme: RenderTheme,
  litRegions?: Set<string>
) {
  if (theme.strokeWidth <= 0) return

  const lit = litRegions ? geometries.filter((g) => litRegions.has(g.name)) : geometries
  const unlit = litRegions ? geometries.filter((g) => !litRegions.has(g.name)) : []

  // 未点亮区域：淡描边，不发光
  if (unlit.length) {
    const path = buildPath2D(unlit)
    ctx.save()
    ctx.strokeStyle = theme.unlitStroke
    ctx.lineWidth = Math.max(0.5, theme.strokeWidth * 0.6)
    ctx.lineJoin = 'round'
    ctx.stroke(path)
    ctx.restore()
  }

  if (!lit.length) return
  const path = buildPath2D(lit)

  if (theme.glow) {
    ctx.save()
    ctx.shadowColor = theme.glow
    ctx.shadowBlur = 18
    ctx.strokeStyle = theme.stroke
    ctx.lineWidth = theme.strokeWidth
    ctx.stroke(path)
    ctx.restore()
  }

  ctx.save()
  ctx.strokeStyle = theme.stroke
  ctx.lineWidth = theme.strokeWidth
  ctx.lineJoin = 'round'
  ctx.stroke(path)
  ctx.restore()
}

/** 绘制区域名称：粗体白字 + 深色描边，保证压在照片上仍可读 */
function drawLabel(
  ctx: CanvasRenderingContext2D,
  geo: RegionGeometry,
  options: RenderOptions
) {
  const { theme } = options
  const b = geo.bounds
  // 未指定字号时按区域短边自适应，并限制上下限
  const size =
    options.labelSize ?? Math.max(12, Math.min(72, Math.min(b.width, b.height) * 0.28))

  ctx.save()
  ctx.font = `700 ${size}px "PingFang SC", "Microsoft YaHei", system-ui, sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.lineJoin = 'round'

  const cx = b.x + b.width / 2
  const cy = b.y + b.height / 2

  ctx.lineWidth = Math.max(2, size * 0.14)
  ctx.strokeStyle = theme.labelStroke
  ctx.strokeText(geo.name, cx, cy)
  ctx.fillStyle = theme.labelColor
  ctx.fillText(geo.name, cx, cy)
  ctx.restore()
}

export interface RenderContext {
  ctx: CanvasRenderingContext2D
  /** CSS 像素尺寸（非物理像素） */
  width: number
  height: number
  geometries: RegionGeometry[]
  cells: PuzzleCell[]
  /** 格子索引 → 照片 id */
  assignments: (string | null)[]
  resolveImage: ImageResolver
  options: RenderOptions
}

/**
 * 执行一次完整渲染。
 * 该函数为纯绘制、无副作用，可在任意时机重复调用（图片到货后重绘即可）。
 */
export function renderPuzzle(context: RenderContext): void {
  const { ctx, width, height, geometries, cells, assignments, resolveImage, options } = context
  const { theme } = options

  ctx.clearRect(0, 0, width, height)

  if (theme.background) {
    ctx.fillStyle = theme.background
    ctx.fillRect(0, 0, width, height)
  }

  if (!geometries.length) return

  // ---- 照片层：按省分组，每个省用「自己的轮廓」裁剪 ----
  //
  // 关键点：裁剪路径必须是单个省的轮廓，不能是全部省合成的大路径。
  // 若用合成路径，陕西的格子只要落在「任意一个省」范围内就不会被裁掉，
  // 于是会溢出到邻省地盘上（全国图曾出现此问题；单省图因只有 1 个省而正常）。
  const cellsByRegion = new Map<string, number[]>()
  for (let i = 0; i < cells.length; i++) {
    if (!assignments[i]) continue // 无照片的格子不画
    const name = cells[i].regionName
    const list = cellsByRegion.get(name)
    if (list) list.push(i)
    else cellsByRegion.set(name, [i])
  }

  for (const geo of geometries) {
    const indices = cellsByRegion.get(geo.name)
    if (!indices || !indices.length) continue

    ctx.save()
    // evenodd 让内环（孔洞）不被填充，与 buildPath2D 的环收集方式配套
    ctx.clip(buildPath2D([geo]), 'evenodd')

    for (const i of indices) {
      const cell = cells[i]
      const size = cell.size
      if (size <= 0) continue

      const img = resolveImage(assignments[i] as string)
      if (img) {
        drawImageCover(ctx, img, cell.x, cell.y, size, size)
      } else {
        // 图片尚在加载中：画占位色，到货后重绘替换
        ctx.fillStyle = theme.placeholder
        ctx.fillRect(cell.x, cell.y, size, size)
      }
    }

    ctx.restore()
  }

  // ---- hover 高亮层 ----
  if (options.hoverRegion) {
    const target = geometries.find((g) => g.name === options.hoverRegion)
    if (target) {
      const hoverPath = buildPath2D([target])
      ctx.save()
      ctx.fillStyle = 'rgba(255,255,255,0.18)'
      ctx.fill(hoverPath, 'evenodd')
      ctx.strokeStyle = theme.stroke
      ctx.lineWidth = theme.strokeWidth * 2
      ctx.lineJoin = 'round'
      ctx.stroke(hoverPath)
      ctx.restore()
    }
  }

  // ---- 轮廓描边层 ----
  strokeRegions(ctx, geometries, theme, options.litRegions)

  // ---- 文字层 ----
  if (options.showLabel) {
    for (const geo of geometries) {
      // 太小的区域画字反而糊，跳过
      if (geo.bounds.width < 28 || geo.bounds.height < 20) continue
      // 未点亮的区域不标名称，避免空白省份的文字抢走视觉重心
      if (options.litRegions && !options.litRegions.has(geo.name)) continue
      drawLabel(ctx, geo, options)
    }
  }
}

/**
 * 按设备像素比初始化画布，避免高分屏下模糊。
 * 返回 CSS 像素下的绘制上下文（已 scale，绘制时无需关心 dpr）。
 */
/**
 * 移动端 Safari 对单 canvas 后备尺寸有较严上限（远低于桌面），
 * 高 dpr 机型（dpr=3+）会让 canvas 像素数翻 9 倍，触达上限后整块画布拒绝渲染
 * （表现为完全空白 + 主线程卡死）。封顶 2：清晰度足够，且把像素数压回 4 倍以内。
 */
export const MAX_CANVAS_DPR = 2

export function setupCanvas(
  canvas: HTMLCanvasElement,
  width: number,
  height: number,
  dpr = Math.min(window.devicePixelRatio || 1, MAX_CANVAS_DPR)
): CanvasRenderingContext2D | null {
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  canvas.width = Math.round(width * dpr)
  canvas.height = Math.round(height * dpr)
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  return ctx
}
