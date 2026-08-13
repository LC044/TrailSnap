import { ref, computed, watch, type Ref } from 'vue'
import type { TimelineStats, TimelineItem, AlbumImage } from '@/types/album'
import {
  getMobileDateHeaderHeight,
  getPhotoColumns,
  getPhotoGap,
  type MobileDateHeaderMode,
} from '@/utils/photoGridLayout'

export interface DayBlock {
  key: string // YYYY-MM-DD
  year: number
  month: number
  day: number
  count: number
  startIndex: number // Global index
  height: number
  top: number // Relative to Month top
  rows: number
}

export interface MonthBlock {
  key: string
  year: number
  month: number
  count: number
  startIndex: number
  height: number
  top: number
  days: DayBlock[]
}

interface UseVirtualLayoutOptions {
  timelineStats: Ref<TimelineStats | undefined>
  containerWidth: Ref<number>
  layoutMode: Ref<'grid' | 'masonry' | 'waterfall' | 'list' | 'moments'> // Added 'waterfall' and 'moments'
  viewSize: Ref<'sm' | 'md' | 'lg'>
  columnCount?: Ref<number | null>
  gridGap?: Ref<number | null>
  dateHeaderMode?: Ref<MobileDateHeaderMode>
  photos: Ref<AlbumImage[]> // Added photos dependency
  expandedDays?: Ref<Set<string>>
  // 朋友圈布局下，用于按 caption 字数动态计算 day 卡片头部高度
  dayCaptions?: Ref<Record<string, { caption: string }>>
}

export function useVirtualLayout(options: UseVirtualLayoutOptions) {
  const { timelineStats, containerWidth, layoutMode, viewSize, photos } = options

  const monthBlocks = ref<MonthBlock[]>([])
  const totalHeight = ref(0)
  
  // Expose these for component use
  const colCount = ref(3)
  const rowHeightVal = ref(0)
  const gapVal = ref(0)

  // Configuration constants
  const HEADER_HEIGHT = 0 
  const DAY_HEADER_HEIGHT = 50
  
  const getGap = () => {
    return options.gridGap?.value ?? getPhotoGap(viewSize.value)
  }

  // Get columns based on viewSize（口径复用 utils/photoGridLayout）
  const getColumns = () => {
    return options.columnCount?.value
      ?? getPhotoColumns(containerWidth.value || window.innerWidth, viewSize.value)
  }

  const recalculateLayout = () => {
    // If no timeline, check if we have photos to show in a flat list
    if (!timelineStats.value?.timeline && photos.value.length === 0) {
        monthBlocks.value = []
        totalHeight.value = 0
        return
    }

    // Prepare timeline data
    let timeline = timelineStats.value?.timeline 
      ? [...timelineStats.value.timeline].sort((a, b) => {
          if (a.year !== b.year) return b.year - a.year
          if (a.month !== b.month) return b.month - a.month
          return b.day - a.day
        })
      : []

    // If no timeline data but we have photos, create a dummy timeline item
    if (timeline.length === 0 && photos.value.length > 0) {
       // Create a single "All Photos" block
       // We can iterate photos to find date range or just group them all
       // For simplicity, let's treat them as one large group
       timeline = [{
         year: 0,
         month: 0,
         day: 0,
         count: photos.value.length
       }]
    }

    const mode = layoutMode.value
    const cols = getColumns()
    const gap = getGap()
    const width = containerWidth.value || 1000 
    
    // Update refs
    colCount.value = cols
    gapVal.value = gap

    let rowHeight = 0
    if (mode === 'grid' || mode === 'masonry') {
         const colWidth = (width - (cols - 1) * gap) / cols
         const aspectRatio = (mode === 'grid') ? 1 : 1.5 
         rowHeight = colWidth / aspectRatio
    } else if (mode === 'waterfall') {
         rowHeight = 220 // Target Row Height for Waterfall
    } else if (mode === 'moments') {
         rowHeight = width < 640 ? Math.floor((width - 32 - gap * 2) / 3) : 120 // Roughly 120px or container width based
    }
    
    rowHeightVal.value = rowHeight
    
    // Group photos by day for Waterfall calculation
    const photosByDay = new Map<string, AlbumImage[]>()
    if (mode === 'waterfall') {
        photos.value.forEach(p => {
             const d = new Date(p.timestamp)
             const key = `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`
             if (!photosByDay.has(key)) photosByDay.set(key, [])
             photosByDay.get(key)!.push(p)
        })
    }

    // Group Timeline by Month
    const months = new Map<string, { year: number, month: number, days: TimelineItem[] }>()
    timeline.forEach(item => {
        const key = `${item.year}-${item.month}`
        if (!months.has(key)) {
            months.set(key, { year: item.year, month: item.month, days: [] })
        }
        months.get(key)!.days.push(item)
    })

    const blocks: MonthBlock[] = []
    let currentTop = 0
    let globalIndex = 0
    let previousYear: number | null = null

    months.forEach((data, key) => {
        const isFirstMonthOfYear = data.year !== previousYear
        previousYear = data.year
        const dayBlocks: DayBlock[] = []
        let currentMonthTop = HEADER_HEIGHT 
        let monthCount = 0

        data.days.forEach((dayItem, dayIndex) => {
            let rows = 0
            let contentHeight = 0
            
            if (mode === 'waterfall') {
                // Calculate rows for Justified Layout
                let currentWidth = 0
                rows = 1
                for (let i = 0; i < dayItem.count; i++) {
                    let ar = 1.5
                    const pIndex = globalIndex + i
                    if (pIndex < photos.value.length) {
                        const p = photos.value[pIndex]
                        if (p.width && p.height) ar = p.width / p.height
                    }
                    const itemWidth = rowHeight * ar
                    if (currentWidth + itemWidth > width) {
                        rows++
                        currentWidth = itemWidth + gap
                    } else {
                        currentWidth += (currentWidth > 0 ? gap : 0) + itemWidth
                    }
                }
                contentHeight = rows * rowHeight + Math.max(0, rows - 1) * gap
            } else if (mode === 'moments') {
                const dayKey = (dayItem.year === 0) ? 'all' : `${dayItem.year}-${dayItem.month}-${dayItem.day}`
                const isExpanded = options.expandedDays?.value.has(dayKey)
                const displayCount = isExpanded ? dayItem.count : Math.min(dayItem.count, 9)
                
                const isMobile = width < 640
                const actualGap = isMobile ? 6 : 8 // gap-1.5 (6px) or gap-2 (8px)
                const fullContentWidth = width - 32 - 40 - 12

                if (isExpanded && dayItem.count > 9) {
                    const contentWidth = fullContentWidth
                    const minItemWidth = isMobile ? 80 : 120
                    const expandedCols = Math.floor((contentWidth + actualGap) / (minItemWidth + actualGap)) || 1
                    const expandedItemWidth = (contentWidth - (expandedCols - 1) * actualGap) / expandedCols
                    rows = Math.ceil(displayCount / expandedCols)
                    contentHeight = rows * expandedItemWidth + Math.max(0, rows - 1) * actualGap
                } else {
                    const contentWidth = Math.min(fullContentWidth, 600)
                    const baseItemWidth = (Math.min(contentWidth, 360) - 2 * actualGap) / 3
                    if (displayCount === 1) {
                        rows = 1
                        // 与 PhotoGallery 的 singlePhotoBoxStyle 口径一致：
                        // 按照片真实比例在 240×250 边界框内取高度，避免预留高度小于实际
                        // 渲染高度导致下一天块压上来、间距变小。
                        const p = photos.value[globalIndex]
                        if (p?.width && p?.height) {
                            let dh = 240 / (p.width / p.height)
                            if (dh > 250) dh = 250
                            contentHeight = dh
                        } else {
                            contentHeight = 200 // 无尺寸元数据时的退化估值
                        }
                    } else if (displayCount === 4) {
                        rows = 2
                        contentHeight = rows * baseItemWidth + actualGap
                    } else {
                        rows = Math.ceil(displayCount / 3)
                        contentHeight = rows * baseItemWidth + Math.max(0, rows - 1) * actualGap
                    }
                }
            } else {
                // Standard Grid / Square
                rows = Math.ceil(dayItem.count / cols)
                contentHeight = rows * rowHeight + Math.max(0, rows - 1) * gap
            }
            
            // If it's the dummy day, don't show header?
            // Or just show 0 height header.
            const isDummy = dayItem.year === 0
            let effectiveHeaderHeight = options.dateHeaderMode
                ? getMobileDateHeaderHeight(
                    options.dateHeaderMode.value,
                    dayIndex === 0,
                    isFirstMonthOfYear,
                    isDummy,
                  )
                : (isDummy ? 0 : DAY_HEADER_HEIGHT)
            
            if (mode === 'moments') {
                // 头部：头像 40 + 昵称 20 + 单行占位文案 24 + 上下 margin ≈ 36
                effectiveHeaderHeight = 120

                // 如果该天已生成 caption，按字数估算多行文本占用的额外高度
                const dayKeyForCap = isDummy ? 'all' : `${dayItem.year}-${dayItem.month}-${dayItem.day}`
                const cap = options.dayCaptions?.value?.[dayKeyForCap]?.caption
                if (cap) {
                    // 每行字数按内容区宽度粗算：文案宽 = min(fullContentWidth, 600) - 内边距
                    const captionMaxWidth = Math.min(width - 32 - 40 - 12, 600) - 8
                    const perLine = Math.max(16, Math.floor(captionMaxWidth / 15)) // 15px 一个字大约
                    // caption 里的显式换行也算行数
                    const explicitBreaks = (cap.match(/\n/g) || []).length
                    const lines = Math.max(1, Math.ceil(cap.length / perLine) + explicitBreaks)
                    // 首行已经算在 120 里，超过一行的每行按 22px 累加；再为按钮/操作条留 4px
                    effectiveHeaderHeight += Math.max(0, lines - 1) * 22 + 4
                }

                if (options.expandedDays?.value.has(dayKeyForCap) && dayItem.count > 9) {
                    effectiveHeaderHeight += 30 // "Collapse" button height
                }
            }

            // moments 布局给每张卡片额外的底部留白，防止下一个 day-block 覆盖当前操作按钮：
            // - 桌面端：32px 冗余（原始设计）
            // - 移动端：72px 冗余（+8px mb-10 组间距、+4px mb-4 文案下方、+4px mt-2 按钮上方、+24px 按钮组常显高度）
            //   桌面端 hover 才显示按钮，故不占实际高度；移动端按钮组常驻显示，必须给它留位置
            const bottomSpacing = (mode === 'moments')
                ? (width < 640 ? 72 : 32)
                : 0

            const dayHeight = effectiveHeaderHeight + contentHeight + gap + bottomSpacing
            
            dayBlocks.push({
                key: isDummy ? 'all' : `${dayItem.year}-${dayItem.month}-${dayItem.day}`,
                year: dayItem.year,
                month: dayItem.month,
                day: dayItem.day,
                count: dayItem.count,
                startIndex: globalIndex,
                height: dayHeight,
                top: currentMonthTop,
                rows
            })

            currentMonthTop += dayHeight
            monthCount += dayItem.count
            globalIndex += dayItem.count
        })

        const monthHeight = currentMonthTop 
        
        blocks.push({
            key,
            year: data.year,
            month: data.month,
            count: monthCount,
            startIndex: globalIndex - monthCount,
            height: monthHeight,
            top: currentTop,
            days: dayBlocks
        })
        
        currentTop += monthHeight
    })

    monthBlocks.value = blocks
    totalHeight.value = currentTop
  }

  // Watchers
  // Added photos to watch list; 朋友圈日文案变化也需要重算布局（不同 caption 高度不同）
  watch([
      () => timelineStats.value,
      containerWidth,
      layoutMode,
      viewSize,
      () => options.columnCount?.value,
      () => options.gridGap?.value,
      () => options.dateHeaderMode?.value,
      () => photos.value.length,
      () => options.expandedDays?.value.size,
      () => {
          const map = options.dayCaptions?.value
          if (!map) return ''
          // 用 "key|长度" 组合作为签名，字符串或键变化都会触发重算
          return Object.keys(map).map(k => `${k}|${(map[k]?.caption || '').length}`).sort().join(',')
      }
  ], () => {
    recalculateLayout()
  }, { immediate: true })

  const getVisibleBlocks = (scrollTop: number, viewportHeight: number, buffer = 1000) => {
    const startY = scrollTop - buffer
    const endY = scrollTop + viewportHeight + buffer
    
    return monthBlocks.value.filter(block => {
        const blockEnd = block.top + block.height
        return blockEnd > startY && block.top < endY
    })
  }

  return {
    monthBlocks,
    totalHeight,
    colCount,
    rowHeight: rowHeightVal,
    gap: gapVal,
    getVisibleBlocks,
    recalculateLayout
  }
}
