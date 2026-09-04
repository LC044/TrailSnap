/**
 * 拼图图片加载器
 *
 * 全国拼图可能需要上千张缩略图，直接 new Image() 并发会打满浏览器连接池、
 * 拖垮页面。这里做三件事：
 *   1. 并发限流（默认 8 路）
 *   2. 已解码图片缓存（同一张照片在多个格子复用时零成本）
 *   3. 批量到货回调 —— 攒一批再触发重绘，避免每张图都重画一次画布
 */

import { onUnmounted, ref } from 'vue'
import { toServerUrl } from '@/config/server'
import { thumbnailUrl } from '@/utils/mediaUrl'

export interface ImageLoaderOptions {
  /** 并发上限 */
  concurrency?: number
  /** 重绘节流间隔（毫秒）：期间内到货的图片攒到一起触发一次回调 */
  flushInterval?: number
  /** 缩略图尺寸 */
  size?: 'small' | 'medium' | 'large'
}

export function usePuzzleImageLoader(options: ImageLoaderOptions = {}) {
  const { concurrency = 8, flushInterval = 120, size = 'small' } = options

  /** photoId → 已解码图片 */
  const cache = new Map<string, HTMLImageElement>()
  /** 加载失败的 id，避免无限重试 */
  const failed = new Set<string>()
  /** 正在加载中的 id */
  const pending = new Set<string>()

  const queue: string[] = []
  let active = 0
  let destroyed = false

  /** 已完成数量（含失败），用于进度展示 */
  const loadedCount = ref(0)
  /** 本轮请求总数 */
  const totalCount = ref(0)

  let flushTimer: number | null = null
  let onBatchReady: (() => void) | null = null

  const scheduleFlush = () => {
    if (destroyed || flushTimer !== null) return
    flushTimer = window.setTimeout(() => {
      flushTimer = null
      onBatchReady?.()
    }, flushInterval)
  }

  const pump = () => {
    if (destroyed) return
    while (active < concurrency && queue.length > 0) {
      const photoId = queue.shift()!
      active++

      const img = new Image()
      // 同源请求（Vite /api 代理），无需 crossOrigin；
      // 但显式声明可避免未来接入 CDN 时 canvas 被污染。
      img.decoding = 'async'
      img.src = thumbnailUrl(photoId, size)

      const finalize = (ok: boolean) => {
        active--
        pending.delete(photoId)
        loadedCount.value++
        if (ok) {
          cache.set(photoId, img)
          scheduleFlush()
        } else {
          failed.add(photoId)
        }
        pump()
      }

      img.onload = () => finalize(true)
      img.onerror = () => finalize(false)
    }
  }

  /**
   * 请求一批照片。已缓存/已在队列中的会自动跳过。
   * @param photoIds 需要的照片 id（可含重复，内部去重）
   * @param onReady  有新图片到货时的批量回调（用于触发重绘）
   */
  const request = (photoIds: (string | null)[], onReady: () => void) => {
    onBatchReady = onReady
    const unique = new Set<string>()
    for (const id of photoIds) {
      if (!id) continue
      if (cache.has(id) || failed.has(id) || pending.has(id)) continue
      unique.add(id)
    }
    if (!unique.size) return
    for (const id of unique) {
      pending.add(id)
      queue.push(id)
    }
    totalCount.value += unique.size
    pump()
  }

  /** 渲染器用的图片取用函数 */
  const resolveImage = (photoId: string): HTMLImageElement | undefined => cache.get(photoId)

  /** 放弃队列中尚未开始的任务（例如用户切换了省份） */
  const cancelPending = () => {
    queue.length = 0
    pending.clear()
  }

  /** 重置进度计数（不清缓存，切换区域时照片可能复用） */
  const resetProgress = () => {
    loadedCount.value = 0
    totalCount.value = 0
  }

  const dispose = () => {
    destroyed = true
    cancelPending()
    cache.clear()
    failed.clear()
    if (flushTimer !== null) {
      clearTimeout(flushTimer)
      flushTimer = null
    }
    onBatchReady = null
  }

  onUnmounted(dispose)

  return {
    request,
    resolveImage,
    cancelPending,
    resetProgress,
    dispose,
    loadedCount,
    totalCount,
    /** 判断某张图是否已就绪，供换图预览使用 */
    isReady: (id: string) => cache.has(id),
  }
}
