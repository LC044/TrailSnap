<template>
  <UnifiedPhotoPage
    ref="unifiedPhotoPageRef"
    class="journal-library"
    title="照片"
    stable-title
    enable-time-browse
    :loading="photoStore.loading"
    :error="photoStore.error"
    :photos="images"
    :timeline-items="photoStore.timelineStats?.timeline || []"
    :timeline-stats="photoStore.timelineStats"
    :has-more="photoStore.hasMore"
    :allow-upload="true"
    :delete-label="'删除'"
    :confirm-remove="true"
    :show-back="false"
    :allow-folder-view="true"
    :allow-diary-view="true"
    :store="photoStore"
    @clear-filters="clearPhotoFilters"
    @load-more="photoStore.loadPhotos"
    @retry="photoStore.loadPhotos(true)"
    @upload="triggerUpload"
    @confirm-delete="handleConfirmDelete"
    @photo-update="handlePhotoUpdate"
    @refresh-data="refreshPhotoData"
  >
    <template #header-left="{ scrolled }">
      <div class="journal-library-title" data-testid="photo-page-title" :data-scrolled="scrolled">
        <h1 class="journal-page-title whitespace-nowrap">照片</h1>
        <p v-if="photoStore.timelineStats" class="journal-library-count">
          {{ photoStore.timelineStats.total_photos.toLocaleString('zh-CN') }} 项影像
        </p>
      </div>
    </template>

    <!-- Header Controls (Filter Button) -->
    <template #header-controls-start>
      <button 
        ref="filterButtonRef"
        @click="showFilterPanel = !showFilterPanel"
        class="ts-glass-button"
        :class="{ 'bg-primary-50 text-primary-500 border-primary-200': showFilterPanel }"
        title="筛选"
        aria-label="筛选照片"
        :aria-expanded="showFilterPanel"
      >
        <Filter class="w-5 h-5" />
      </button>
    </template>

    <!-- Filter Panel -->
    <template #header-extension>
      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="transform -translate-y-2 opacity-0"
        enter-to-class="transform translate-y-0 opacity-100"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="transform translate-y-0 opacity-100"
        leave-to-class="transform -translate-y-2 opacity-0"
      >
          <div v-if="showFilterPanel && !mobileMenu" class="absolute left-0 right-0 top-full mt-2 pointer-events-none px-[var(--ts-page-gutter)]">
            <div class="max-w-screen-2xl mx-auto flex justify-end">
              <!-- 实心表面 + 浮层阴影：玻璃过透会让照片透上来，条件文字读不清 -->
              <div ref="filterPanelRef" class="filter-popover pointer-events-auto w-full max-w-[26rem] overflow-y-auto overscroll-contain rounded-2xl border border-[var(--ts-color-border)] bg-[var(--ts-color-surface)] p-4 max-h-[calc(100dvh-var(--ts-header-height)-24px)]">
                 <FilterPanel :store="photoStore" />
              </div>
            </div>
          </div>
      </Transition>
    </template>

    <!-- Upload Modal -->
    <template #extra-modals>
        <ResponsiveDialog v-if="mobileMenu" v-model="showFilterPanel" title="筛选照片" :glass="false">
          <FilterPanel ref="mobileFilterRef" :store="photoStore" />
          <template #footer>
            <div class="flex gap-3">
              <button type="button" class="ts-button ts-button-secondary flex-1" @click="mobileFilterRef?.clearAll()">重置</button>
              <button type="button" class="ts-button ts-button-primary flex-[2]" @click="showFilterPanel = false">完成</button>
            </div>
          </template>
        </ResponsiveDialog>

    </template>

    <template #empty>
      <div v-if="hasActiveFilters" class="py-20 text-center ts-muted">
        <p>没有符合条件的照片</p>
        <button type="button" class="ts-button ts-button-primary mt-4" @click="clearPhotoFilters">清除筛选</button>
      </div>
      <div v-else class="journal-library-empty">
        <FolderPlus aria-hidden="true" />
        <h2>留下第一张照片</h2>
        <p>导入照片和视频，或连接已存放照片的文件夹。</p>
        <div class="flex flex-wrap justify-center gap-2">
          <button type="button" class="ts-button journal-library-import" @click="triggerUpload">导入照片</button>
          <RouterLink to="/settings#external" class="ts-button ts-button-secondary">连接图库</RouterLink>
        </div>
      </div>
    </template>

  </UnifiedPhotoPage>
</template>

<script setup lang="ts">
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import { ref, computed, nextTick, onUnmounted, onActivated, onDeactivated, watch } from 'vue'
import { useRouter, useRoute, onBeforeRouteLeave } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useAlbumStore } from '@/stores/albumStore'
import { usePhotosPageStore } from '@/stores/photoStore'
import { normalizeMediaTypeFilters } from '@/utils/mediaTypeFilters'
import { Filter, FolderPlus } from 'lucide-vue-next'
import { useMediaQuery, onClickOutside } from '@vueuse/core'
import UnifiedPhotoPage from '@/components/UnifiedPhotoPage.vue'
import { useUploadStore } from '@/stores/uploadCenterStore'
import FilterPanel from '@/components/FilterPanel.vue'
import { ElMessage } from 'element-plus'

defineOptions({
  name: 'PhotosPage'
})

const router = useRouter()
const route = useRoute()
const store = useAlbumStore()
const photoStore = usePhotosPageStore()
const userStore = useUserStore()
const initializeTimePreferences = () => {
  let saved: { view?: string; time?: string } = {}
  try { saved = JSON.parse(localStorage.getItem(`photo-timeline-preferences:${userStore.userInfo?.id ?? 'anonymous'}`) || '{}') } catch {}
  photoStore.browseEnabled = true
  const view = route.query.view ?? saved.view
  photoStore.browseGranularity = view === 'year' || view === 'month' ? view : 'day'
  photoStore.timeField = (route.query.time ?? saved.time) === 'upload_time' ? 'upload_time' : 'photo_time'
}
initializeTimePreferences()
const unifiedPhotoPageRef = ref<InstanceType<typeof UnifiedPhotoPage> | null>(null)
const pageActive = ref(false)
let autoRefreshTimer: ReturnType<typeof setTimeout> | null = null
let autoRefreshRunning = false

const scheduleAutoRefresh = (delay = 3000) => {
  if (!pageActive.value || autoRefreshTimer !== null || autoRefreshRunning || !photoStore.dataStale) return
  autoRefreshTimer = setTimeout(() => {
    autoRefreshTimer = null
    void autoRefreshIfCountChanged()
  }, delay)
}

const autoRefreshIfCountChanged = async () => {
  if (!pageActive.value || autoRefreshRunning || !photoStore.dataStale) return
  if (!photoStore.timelineStats || unifiedPhotoPageRef.value?.isPhotoInteractionActive) {
    scheduleAutoRefresh(1000)
    return
  }
  autoRefreshRunning = true
  let shouldRetry = true
  try {
    const changed = await photoStore.hasCurrentContextPhotoCountChanged()
    if (changed && pageActive.value) {
      await unifiedPhotoPageRef.value?.refreshDataPreservingPosition()
    }
  } catch (error) {
    shouldRetry = false
    console.error('自动检查照片数量失败', error)
  } finally {
    autoRefreshRunning = false
    if (shouldRetry && pageActive.value && photoStore.dataStale) scheduleAutoRefresh()
  }
}

watch([() => photoStore.dataStale, () => photoStore.dataRevision], ([stale]) => {
  if (stale) scheduleAutoRefresh()
})

// State
const images = computed(() => photoStore.images)
const uploadStore = useUploadStore()
const mobileMenu = useMediaQuery('(max-width: 639px)')
const showFilterPanel = ref(false)
const filterButtonRef = ref<HTMLElement | null>(null)
const filterPanelRef = ref<HTMLElement | null>(null)
// 移动端弹窗的底部「重置」需要调用面板内部的清除逻辑。
const mobileFilterRef = ref<{ clearAll: () => void } | null>(null)

onClickOutside(filterPanelRef, () => {
  if (!mobileMenu.value) showFilterPanel.value = false
}, {
  ignore: [filterButtonRef]
})

// Methods
const triggerUpload = () => uploadStore.open()

const handleConfirmDelete = async (ids: string[], callback: (success: boolean) => void) => {
  try {
    await photoStore.deletePhotos(ids)
    callback(true)
    // deletePhotos updates the loaded list and timeline incrementally, so the
    // virtual gallery keeps its height and current scroll position.
    void Promise.all([
      photoStore.fetchAvailableFilters(),
      store.fetchAlbums(),
    ])
  } catch (e) {
    console.error(e)
    ElMessage.error('删除失败')
    callback(false)
  }
}

const handlePhotoUpdate = (event: { id: string; filename?: string; photo_time?: string | null }) => {
  const image = photoStore.images.find(item => item.id === event.id)
  if (image && event.filename !== undefined) image.filename = event.filename
  if (image && event.photo_time !== undefined) {
    image.photoTime = event.photo_time
    image.hasPhotoTime = Boolean(event.photo_time)
    if (photoStore.timeField === 'photo_time') image.timestamp = event.photo_time ? new Date(event.photo_time).getTime() : NaN
    photoStore.markDataStale('EXTRACT_METADATA')
  }
}

const refreshPhotoData = async (done: (success?: boolean) => void = () => {}) => {
  let success = false
  try {
    await photoStore.refreshCurrentContext()
    await Promise.all([
      photoStore.fetchAvailableFilters(),
      store.fetchAlbums(),
    ])
    success = true
  } catch (error) {
    console.error('刷新照片失败', error)
  } finally {
    done(success)
  }
}

// 将路由 query 中的筛选值解析为数组（支持逗号分隔或重复参数）
const parseQueryFilter = (value: unknown): string[] => {
  if (value == null) return []
  if (Array.isArray(value)) value = value.join(',')
  return String(value).split(',').map(s => s.trim()).filter(Boolean)
}

const applyQueryFilters = () => {
  const f = photoStore.selectedFilters
  // 先清空已有筛选，避免上一次访问残留
  f.image_types = []
  f.file_types = []
  f.uploaded_after = undefined
  f.uploaded_before = undefined
  f.years = []
  f.cities = []
  f.makes = []
  f.models = []
  f.people = parseQueryFilter(route.query.people)
  f.categories = parseQueryFilter(route.query.categories)

  const { image_types, file_types, years, cities, makes, models, uploaded_after, uploaded_before, is_panorama } = route.query
  f.image_types = parseQueryFilter(image_types)
  f.file_types = normalizeMediaTypeFilters(parseQueryFilter(file_types), is_panorama)
  f.makes = parseQueryFilter(makes)
  f.models = parseQueryFilter(models)
  f.cities = parseQueryFilter(cities)
  f.years = parseQueryFilter(years).map(y => Number(y)).filter(n => !Number.isNaN(n))
  f.uploaded_after = parseQueryFilter(uploaded_after)[0]
  f.uploaded_before = parseQueryFilter(uploaded_before)[0]
}

const filterQueryKey = () => JSON.stringify(Object.fromEntries(Object.entries(route.query).filter(([key]) => !['view', 'time', 'anchor'].includes(key))))
let lastQueryStr = ''
let initialized = false
let savedScrollTop = 0

const hasActiveFilters = computed(() => Object.values(photoStore.selectedFilters).some(value => Array.isArray(value) ? value.length > 0 : Boolean(value)))
const clearPhotoFilters = async () => {
  const previousKey = filterQueryKey()
  await router.replace({ path: '/photos', query: { view: photoStore.browseGranularity, time: photoStore.timeField } })
  if (previousKey === filterQueryKey()) initData()
}

const getScrollContainer = () => document.querySelector('main') as HTMLElement | null

onBeforeRouteLeave((_to, from) => {
  if (pageActive.value && from.name === 'Photos') {
    savedScrollTop = getScrollContainer()?.scrollTop ?? 0
  }
})

const initData = () => {
  initialized = true
  lastQueryStr = filterQueryKey()
  photoStore.resetAll()
  initializeTimePreferences()
  // 从路由查询参数应用筛选条件（如存储中心跳转过来的“截图/视频/实况图”）
  applyQueryFilters()
  // Initial Load
  photoStore.fetchAvailableFilters()
  store.fetchAlbums()
  photoStore.loadPhotos(true)
  savedScrollTop = 0
}

onActivated(() => {
  pageActive.value = true
  const currentQueryStr = filterQueryKey()
  if (!initialized || currentQueryStr !== lastQueryStr) {
    initData()
  } else {
    if (photoStore.dataStale) {
      scheduleAutoRefresh()
    } else {
      photoStore.fetchAvailableFilters()
      store.fetchAlbums()
    }
  }

  // 重新进入缓存页时，主滚动容器由前一个页面共用。恢复位置后主动同步可见范围，
  // 因为滚动位置没变时浏览器不会派发 scroll。
  void nextTick(() => {
    if (!pageActive.value) return
    const container = getScrollContainer()
    if (container) container.scrollTop = savedScrollTop
    const gallery = unifiedPhotoPageRef.value?.galleryRef
    gallery?.updateVisibleBlocks()
    gallery?.checkAndLoadVisibleMonths()
  })
})

watch(() => userStore.userInfo?.id, () => {
  initialized = false
  photoStore.resetAll()
  initializeTimePreferences()
  if (pageActive.value) initData()
})

watch(filterQueryKey, key => {
  if (pageActive.value && route.name === 'Photos' && key !== lastQueryStr) initData()
})

onDeactivated(() => {
  pageActive.value = false
  if (autoRefreshTimer !== null) clearTimeout(autoRefreshTimer)
  autoRefreshTimer = null
})

onUnmounted(() => {
  pageActive.value = false
  if (autoRefreshTimer !== null) clearTimeout(autoRefreshTimer)
  // photoStore.resetAll() // 移除销毁时的清空，让 keep-alive 保持数据
})
</script>

<style scoped>
.journal-library-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
  padding-right: 8px;
}
.journal-library-count { color: var(--ts-color-text-secondary); font-size: 12px; white-space: nowrap; }
@media (max-width: 767px) {
  .journal-library :deep([data-photo-header]:has([data-scrolled="true"])::before) {
    content: '';
    position: absolute;
    z-index: -1;
    inset: 0 0 -24px;
    pointer-events: none;
    background: linear-gradient(to bottom, rgb(0 0 0 / 42%), rgb(0 0 0 / 28%) calc(100% - 24px), transparent);
  }
  .journal-library-title[data-scrolled="true"] :is(h1, .journal-library-count) {
    color: white;
    text-shadow: 0 1px 3px rgb(0 0 0 / 75%), 0 0 7px rgb(0 0 0 / 45%);
  }
  .journal-library :deep([data-photo-header]:has([data-scrolled="true"]) .ts-glass-toolbar) {
    --glass-tint: rgb(0 0 0 / 32%);
    --glass-rim-color: rgb(255 255 255 / 24%);
    --ts-glass-highlight: rgb(255 255 255 / 22%);
    --ts-glass-sheen: linear-gradient(155deg, rgb(255 255 255 / 12%), transparent 55%);
  }
  .journal-library :deep([data-photo-header]:has([data-scrolled="true"]) .ts-glass-button) { color: white; }
  .journal-library :deep([data-photo-header]:has([data-scrolled="true"]) .ts-glass-button:is(:hover, [aria-expanded="true"])) {
    background-color: rgb(255 255 255 / 18%);
  }
  .journal-library :deep([data-photo-header]:has([data-scrolled="true"]) .ts-glass-button:focus-visible) {
    outline-color: white;
  }
}
.journal-library-empty {
  display: grid;
  justify-items: center;
  gap: 15px;
  margin: clamp(20px, 5vw, 65px) auto;
  padding: clamp(28px, 6vw, 80px) 14px;
  border: 1px dashed var(--ts-color-border);
  border-radius: 22px;
  background: var(--ts-color-surface);
  text-align: center;
}
.journal-library-empty > svg { box-sizing: content-box; width: 26px; padding: 14px; border-radius: 50%; background: var(--ts-journal-active); }
.journal-library-empty h2 { font: 700 clamp(26px, 3vw, 38px)/1.15 var(--ts-journal-serif); }
.journal-library-empty p { color: var(--ts-color-text-secondary); font-size: 14px; }
.journal-library-import { background: var(--ts-journal-action); color: white; }
.journal-library-import:hover { background: var(--ts-journal-action-hover); }
@media (max-width: 639px) { .journal-library-count { display: none; } }
.slide-up-enter-active, .slide-up-leave-active { transition: all 0.3s ease; }
.slide-up-enter-from, .slide-up-leave-to { transform: translateY(20px); opacity: 0; }
/* 浮层阴影用变量直出：Tailwind 的 shadow-[var(...)] 在此配置下不生效 */
.filter-popover { box-shadow: var(--ts-shadow-floating); }
</style>
