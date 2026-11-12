<template>
  <UnifiedPhotoPage
    :title="title"
    :loading="loading && photos.length === 0"
    :photos="photos"
    :has-more="hasMore"
    :timeline-items="timeline"
    :timeline-stats="{ timeline }"
    @confirm-delete="handleConfirmDelete"
    @back="goBack"
    @load-more="loadMore"
    >
    <template #header-left="{ scrolled }">
      <AlbumDetailTitle :title="title" :scrolled="scrolled" :subtitle="`${photos.length}${hasMore ? '+' : ''} 个项目`" back-label="返回智能分类" @back="goBack" />
    </template>
    <!-- 类别选择条：桌面封面 tile 单行（名称压在封面底部），过多时折叠为一行，按钮展开；移动端无封面胶囊单行，超出左右滑动 -->
    <template #header-extension>
      <div v-if="categoryItems.length" class="mx-auto mb-2 max-w-screen-2xl">
        <nav
          ref="gridRef"
          class="classification-category-grid"
          :class="{ 'is-collapsed': !expanded && !isMobile }"
          :aria-label="`${title}下的类别`"
          data-testid="classification-category-strip"
        >
          <button
            v-for="item in categoryItems"
            :key="item.id"
            type="button"
            class="category-tile group"
            :class="{ 'is-active': item.id === activeTagId, 'is-loading': loading && item.id === activeTagId }"
            :aria-current="item.id === activeTagId ? 'true' : undefined"
            :data-testid="`classification-category-${item.name}`"
            @click="selectCategory(item)"
          >
            <img
              v-if="item.cover && !isMobile"
              :src="mapPhotoToImage(item.cover).thumbnail"
              class="absolute inset-0 h-full w-full object-cover transition-transform duration-300 group-hover:scale-110 motion-reduce:transition-none"
              loading="lazy"
              :alt="item.name"
            />
            <span v-else-if="!isMobile" class="absolute inset-0 flex items-center justify-center bg-gray-100 dark:bg-gray-800">
              <Tag class="h-4 w-4 text-gray-400 dark:text-gray-500" />
            </span>
            <span v-else class="category-tile-name-mobile">{{ item.name }}</span>
            <span v-if="!isMobile" class="category-tile-scrim" aria-hidden="true"></span>
            <span v-if="!isMobile" class="category-tile-caption">
              <span class="category-tile-name">{{ item.name }}</span>
            </span>
            <span v-if="item.id === activeTagId && !isMobile" class="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary-500 text-white shadow-sm" aria-hidden="true">
              <Check class="h-3 w-3" />
            </span>
          </button>
        </nav>
        <button
          v-if="needsToggle && !isMobile"
          type="button"
          class="mt-1.5 inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
          :aria-expanded="expanded"
          data-testid="classification-category-toggle"
          @click="expanded = !expanded"
        >
          <component :is="expanded ? ChevronUp : ChevronDown" class="h-3.5 w-3.5" />
          {{ expanded ? '收起' : `展开全部 ${categoryItems.length} 个类别` }}
        </button>
      </div>
    </template>
    <template #empty>
      <div class="flex min-h-[40vh] flex-col items-center justify-center text-center text-gray-500 dark:text-gray-400">
        <Tag class="h-10 w-10 opacity-20" />
        <p class="mt-4 text-base font-medium">{{ categoryItems.length ? '该类别暂无照片' : '该分组暂无类别' }}</p>
        <p class="mt-1 text-sm">类别统计完成后会自动出现；也可以在分类规则中调整启用的类别。</p>
      </div>
    </template>
    <template #batch-actions="{ selectedIds, clearSelection }">
      <button
          v-if="selectedIds.size === 1"
          type="button"
          class="ts-action-row"
          @click="handleSetCover(Array.from(selectedIds)); clearSelection()"
      >
          <div class="flex items-center gap-2">
            <ImageIcon class="w-4 h-4" />
            <span>设为封面</span>
          </div>
      </button>
      <button
          type="button"
          class="ts-action-row"
          @click="removePhotoFromTags(Array.from(selectedIds)); clearSelection()"
      >
          <div class="flex items-center gap-2">
            <ImageMinus class="w-4 h-4" />
            <span>从分类中移除</span>
          </div>
      </button>
    </template>
  </UnifiedPhotoPage>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import { useAppBack } from '@/composables/useAppBack'
import { classificationService, clipClassificationService, type TagStats, type ClipCategory } from '@/api/classification'
import UnifiedPhotoPage from '@/components/UnifiedPhotoPage.vue'
import AlbumDetailTitle from '@/components/AlbumDetailTitle.vue'
import { mapPhotoToImage, usePhotoStore } from '@/stores/photoStore'
import type { AlbumImage } from '@/types/album'
import { ElMessage } from 'element-plus'
import { ImageMinus, ImageIcon, Tag, Check, ChevronDown, ChevronUp } from 'lucide-vue-next'

const YOLO_GROUP = 'YOLO / 自定义分类'

const route = useRoute()
const router = useRouter()
const goBack = useAppBack('/album/classification')
const groupName = computed(() => (route.params.group as string) || '')
const photoStore = usePhotoStore()
const loading = ref(false)
const photos = ref<AlbumImage[]>([])
const timeline = ref<any[]>([])
const skip = ref(0)
const hasMore = ref(true)
const pendingRemoveIds = ref(new Set<string>())
const categories = ref<ClipCategory[]>([])
const tags = ref<TagStats[]>([])
const activeTagId = ref<string>('')
const title = computed(() => groupName.value || '分类')

interface CategoryItem { id: string; name: string; count: number; cover: TagStats['cover'] }

const categoryItems = computed<CategoryItem[]>(() => {
  if (groupName.value === YOLO_GROUP) {
    const clipTagIds = new Set(categories.value.map(c => c.tag_id))
    return tags.value
      .filter(t => !clipTagIds.has(t.id))
      .map(t => ({ id: t.id, name: t.tag_name, count: t.count, cover: t.cover }))
  }
  const tagMap = new Map(tags.value.map(t => [t.id, t]))
  return categories.value
    .filter(c => c.groups.includes(groupName.value) && (tagMap.get(c.tag_id)?.count ?? c.count) > 0)
    .map(c => {
      const tag = tagMap.get(c.tag_id)
      return { id: c.tag_id, name: c.name, count: tag?.count ?? c.count, cover: tag?.cover ?? null }
    })
})

const activeItem = computed(() => categoryItems.value.find(i => i.id === activeTagId.value))

const fetchMeta = async () => {
  try {
    tags.value = await classificationService.getTags()
  } catch { /* 标签列表失败时类别条为空，详情仍可按 URL query 定位 */ }
  try {
    const data = await clipClassificationService.list()
    categories.value = Array.isArray(data?.categories) ? data.categories : []
  } catch { /* 仅影响类别条 */ }
}

const resolveActiveTagId = () => {
  const queryId = typeof route.query.tag_id === 'string' ? route.query.tag_id : undefined
  if (queryId && categoryItems.value.some(i => i.id === queryId)) return queryId
  return categoryItems.value[0]?.id ?? ''
}

const resetAndLoad = async () => {
  photos.value = []
  timeline.value = []
  skip.value = 0
  hasMore.value = true
  const item = activeItem.value
  if (!item) { hasMore.value = false; return }
  await loadMore()
}

const selectCategory = (item: CategoryItem) => {
  if (item.id === activeTagId.value) return
  // 兼容旧列表的月亮入口：月亮分类跳转月迹
  if (['月亮', 'moon'].includes(item.name.trim().toLowerCase())) {
    router.push({ name: 'MoonJournal' })
    return
  }
  activeTagId.value = item.id
  router.replace({
    name: 'ClassificationGroup',
    params: { group: groupName.value },
    query: { tag_id: item.id }
  })
  void resetAndLoad()
}

const calculateTimelineStats = (photos: AlbumImage[]) => {
  const stats = new Map<string, { year: number, month: number, day: number, count: number }>()

  photos.forEach(photo => {
    const date = new Date(photo.timestamp)
    const year = date.getFullYear()
    const month = date.getMonth() + 1
    const day = date.getDate()
    const key = `${year}-${month}-${day}`

    if (!stats.has(key)) {
      stats.set(key, { year, month, day, count: 0 })
    }
    stats.get(key)!.count++
  })

  timeline.value = Array.from(stats.values()).sort((a, b) => {
    if (a.year !== b.year) return b.year - a.year
    if (a.month !== b.month) return b.month - a.month
    return b.day - b.day
  })
}

const loadMore = async () => {
  if (loading.value || !hasMore.value) return
  const item = activeItem.value
  if (!item) { hasMore.value = false; return }
  loading.value = true
  try {
    const limit = 500
    let hasNext = true

    while (hasNext) {
      const current = activeItem.value
      if (!current || current.id !== item.id) break
      const rawPhotos = await classificationService.getTagPhotos(current.name, skip.value, limit, current.id)

      if (rawPhotos.length < limit) {
        hasMore.value = false
        hasNext = false
      }

      const newPhotos = rawPhotos.map(mapPhotoToImage)
      photos.value.push(...newPhotos)
      skip.value += limit

      calculateTimelineStats(photos.value)
    }
  } catch (e) {
    console.error('Failed to load tag photos:', e)
  } finally {
    loading.value = false
  }
}

const handleConfirmDelete = async (ids: string[], callback: (success: boolean) => void) => {
  try {
    ids.forEach(id => pendingRemoveIds.value.add(id))

    await photoStore.deletePhotos(ids)
    // Remove from local list
    photos.value = photos.value.filter(img => !ids.includes(img.id))
    calculateTimelineStats(photos.value)
    ElMessage.success('删除成功')

    callback(true)

  } catch (e) {
    ElMessage.error('删除失败')
    callback(false)
  } finally {
    ids.forEach(id => pendingRemoveIds.value.delete(id))
  }
}

const removePhotoFromTags = async (ids: string[]) => {
  const item = activeItem.value
  if (!item) return
  try {
    await classificationService.removePhotosFromTag(item.name, ids, item.id)
    photos.value = photos.value.filter(img => !ids.includes(img.id))
    calculateTimelineStats(photos.value)
    ElMessage.success('从分类中移除成功')
  } catch (e) {
    ElMessage.error('从分类中移除失败')
  }
}

const handleSetCover = async (ids: string[]) => {
  const item = activeItem.value
  if (!item || !ids.length) return
  const photoId = ids[0]
  try {
    await classificationService.setCover(item.name, photoId, item.id)
    ElMessage.success('已设为封面')
  } catch (e) {
    ElMessage.error('设置封面失败')
  }
}

const gridRef = ref<HTMLElement | null>(null)
const expanded = ref(false)
// 移动端：无封面胶囊单行，超出左右滑动，不需要折叠/展开
const isMobile = useMediaQuery('(max-width: 767px)')
const visibleCount = ref(Infinity)
const needsToggle = computed(() => !isMobile.value && visibleCount.value < categoryItems.value.length)
// 移动端切回桌面时恢复折叠度量
watch(isMobile, () => {
  if (!isMobile.value) requestAnimationFrame(() => measureVisibleCount())
})

const measureVisibleCount = () => {
  if (isMobile.value) { visibleCount.value = Infinity; return }
  const grid = gridRef.value
  if (!grid) return
  const tiles = Array.from(grid.querySelectorAll<HTMLElement>('.category-tile'))
  if (tiles.length <= 1) { visibleCount.value = Infinity; return }
  // 折叠高度（一行）内能塞多少个 tile：直接数第一行的 tile
  const firstTop = tiles[0].getBoundingClientRect().top
  let count = 0
  for (const tile of tiles) {
    if (Math.abs(tile.getBoundingClientRect().top - firstTop) > 5) break
    count++
  }
  visibleCount.value = count
}

watch(() => categoryItems.value.length, () => {
  requestAnimationFrame(() => measureVisibleCount())
})

let resizeMeasureTimer: ReturnType<typeof setTimeout> | undefined
const handleResize = () => {
  clearTimeout(resizeMeasureTimer)
  resizeMeasureTimer = setTimeout(() => measureVisibleCount(), 150)
}
onMounted(() => window.addEventListener('resize', handleResize))
onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  clearTimeout(resizeMeasureTimer)
})

const init = async () => {
  loading.value = false
  photos.value = []
  timeline.value = []
  await fetchMeta()
  activeTagId.value = resolveActiveTagId()
  await resetAndLoad()
  // 类别网格渲染后测量折叠容量，决定是否显示展开按钮
  requestAnimationFrame(() => measureVisibleCount())
}

// 同一组件实例在不同分组间跳转（params 变化）时重新初始化
watch(() => groupName.value, () => {
  void init()
})

onMounted(() => {
  void init()
})
</script>

<style scoped>
/* 类别选择条：桌面封面 tile 换行（名称压在封面底部），过多时折叠一行 + 展开按钮；移动端见下方媒体查询 */
.classification-category-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.category-tile {
  position: relative;
  display: flex;
  width: 68px;
  height: 68px;
  flex-direction: column;
  overflow: hidden;
  border-radius: 12px;
  background: var(--ts-color-surface-muted);
  box-shadow: 0 1px 2px rgb(15 23 42 / 6%);
  transition: box-shadow var(--ts-motion-fast) ease, outline-color var(--ts-motion-fast) ease;
  outline: 2px solid transparent;
  outline-offset: -1px;
  text-align: left;
}
.category-tile:hover {
  box-shadow: 0 4px 12px rgb(15 23 42 / 12%);
}
.category-tile:focus-visible {
  outline-color: var(--theme-primary);
}

/* 名称叠在封面底部的渐变压条上 */
.category-tile-scrim {
  position: absolute;
  inset: auto 0 0 0;
  height: 30px;
  background: linear-gradient(to top, rgb(0 0 0 / 62%), rgb(0 0 0 / 0%));
}
.category-tile-caption {
  position: absolute;
  inset: auto 0 3px;
  display: flex;
  justify-content: center;
  padding-inline: 5px;
  color: #fff;
  line-height: 1.25;
}
.category-tile-name {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  text-shadow: 0 1px 2px rgb(0 0 0 / 45%);
}

/* 选中态：主色描边 + 角标勾 */
.category-tile.is-active {
  outline: 2px solid var(--theme-primary);
  outline-offset: 0;
}

/* 折叠：限高一行，溢出隐藏 */
.classification-category-grid.is-collapsed {
  max-height: 68px;
  overflow: hidden;
}

/* 加载中当前类别：封面轻呼吸提示 */
.category-tile.is-loading img {
  animation: category-tile-pulse 1.2s ease-in-out infinite;
}
@keyframes category-tile-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}
@media (prefers-reduced-motion: reduce) {
  .category-tile.is-loading img { animation: none; }
  .category-tile.is-loading { animation: none; }
}

/* 移动端：去掉封面，胶囊只显示分类名，单行超出左右滑动，不折叠 */
@media (max-width: 767px) {
  .classification-category-grid {
    flex-wrap: nowrap;
    gap: 6px;
    overflow-x: auto;
    /* 负边距吃掉页面横向留白，让首尾胶囊贴近屏幕边缘 */
    margin-inline: calc(var(--ts-page-gutter, 16px) * -1);
    padding-inline: var(--ts-page-gutter, 16px);
    padding-bottom: 2px;
    scroll-snap-type: x proximity;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }
  .classification-category-grid::-webkit-scrollbar { display: none; }
  .category-tile {
    width: auto;
    height: auto;
    flex-shrink: 0;
    flex-direction: row;
    align-items: center;
    justify-content: center;
    border-radius: 9999px;
    padding: 6px 14px;
    box-shadow: none;
    background: var(--ts-color-surface-muted);
    scroll-snap-align: start;
  }
  .category-tile-name-mobile {
    font-size: 13px;
    font-weight: 500;
    line-height: 1.4;
    white-space: nowrap;
    max-width: 6em;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--ts-color-text);
  }
  /* 选中态：主色胶囊 */
  .category-tile.is-active {
    outline: none;
    background: var(--theme-primary);
  }
  .category-tile.is-active .category-tile-name-mobile {
    color: #fff;
    font-weight: 600;
  }
  .category-tile.is-loading {
    animation: category-tile-pulse 1.2s ease-in-out infinite;
  }
}
</style>
