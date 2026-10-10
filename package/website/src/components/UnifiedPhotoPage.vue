<template>
  <div class="ts-browse-page unified-photo-page relative mx-auto w-full max-w-screen-2xl py-0 px-[var(--ts-page-gutter)] min-h-screen" :class="{ 'photo-diary-mode': layoutMode === 'diary' }" :style="{ '--photo-page-header-height': `${headerHeight}px` }">
    <span ref="pageTopRef" class="pointer-events-none absolute left-0 top-0 h-px w-px" aria-hidden="true"></span>
    <!-- Toolbar & Header（文件夹视图有自己的工具栏，这里整条隐藏以节省移动端空间） -->
    <div v-if="layoutMode !== 'folder'" ref="headerRef" class="pointer-events-none sticky top-0 z-[45] -mx-[var(--ts-page-gutter)] px-[var(--ts-page-gutter)] pt-[var(--ts-safe-area-top)]">
      <div class="ts-browse-header pointer-events-auto flex items-center justify-between gap-1 sm:gap-3 mx-auto py-1.5 sm:py-2">
        <!-- Back & Title -->
        <slot name="header-left" :scrolled="headerScrolled">
          <div v-if="showBack || title || $slots['title-extra']" class="flex min-w-0 items-center gap-2" :class="headerScrolled ? 'text-white' : 'text-gray-900 dark:text-white'" data-testid="photo-page-title" :data-scrolled="headerScrolled">
            <BackButton label="返回" v-if="showBack" @click="$emit('back')" />
            <div class="min-w-0 transition-colors duration-200" :class="headerScrolled ? 'rounded-full bg-black/60 px-3 py-1.5 backdrop-blur-sm' : 'pr-2'" v-if="!loadingTitle">
              <h1 :title="title" class="ts-page-title flex items-center gap-2" :class="{ 'ts-compact-title': headerScrolled }">
                <span class="truncate">{{ title }}</span>
                <slot name="title-extra"></slot>
              </h1>
              <p v-if="subtitle && !headerScrolled" class="text-xs text-gray-500 dark:text-gray-400 truncate">{{ subtitle }}</p>
            </div>
            <div v-else class="pr-2 animate-pulse">
              <div class="h-6 w-32 bg-gray-200 dark:bg-gray-800 rounded"></div>
            </div>
          </div>
        </slot>

        <!-- Controls -->
        <div class="ts-liquid-glass ts-glass-toolbar flex shrink-0 items-center justify-end gap-1 sm:gap-2 ml-auto">
          
          <slot name="header-controls-start"></slot>

          <!-- View Options Menu -->
          <div class="relative">
             <button
               @click="showViewOptions = !showViewOptions"
               class="ts-glass-button"
               title="视图设置"
               aria-label="更多照片视图"
               :aria-expanded="showViewOptions"
             >
               <Settings2 class="w-5 h-5" />
             </button>

             <!-- Secondary Menu Dropdown -->
            <AdaptiveMenu v-model="showViewOptions" title="照片视图" ref="viewOptionsRef">
                <div class="space-y-3 p-1">
                  <button v-if="allowUpload" type="button" class="sm:hidden flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800" @click="showViewOptions = false; $emit('upload')">
                    <UploadCloud class="h-4 w-4" />
                    <span>上传照片</span>
                  </button>
                  <!-- View Size -->
                  <div v-if="layoutMode !== 'diary'" class="space-y-2">
                    <p class="text-xs font-medium text-gray-500 dark:text-gray-400 px-1">图片大小</p>
                    <div class="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
                      <button v-for="size in ['sm', 'md', 'lg']" :key="size"
                        @click="viewSize = size as any"
                        class="ts-icon-button ts-button-ghost flex-1 min-h-11 text-center dark:bg-gray-800"
                        :class="{ 'bg-white dark:bg-gray-700 shadow-sm text-primary-500': viewSize === size, 'text-gray-700 dark:text-gray-300': viewSize !== size }"
                      >
                        <Grid3x3 v-if="size === 'sm'" class="w-4 h-4 mx-auto" />
                        <Grid2x2 v-if="size === 'md'" class="w-4 h-4 mx-auto" />
                        <Maximize v-if="size === 'lg'" class="w-4 h-4 mx-auto" />
                      </button>
                    </div>
                  </div>

                  <!-- Layout Mode -->
                  <div class="space-y-2">
                    <p class="text-xs font-medium text-gray-500 dark:text-gray-400 px-1">布局模式</p>
                    <div class="grid grid-cols-1 gap-1">
                       <button
                        @click="showViewOptions = false; layoutMode = 'waterfall'"
                        class="ts-button ts-button-ghost flex min-h-11 items-center gap-2"
                        :class="layoutMode === 'waterfall' ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400 font-medium' : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'"
                      >
                        <LayoutDashboard class="w-4 h-4" />
                        <span>自适应</span>
                      </button>
                      <button
                        @click="showViewOptions = false; layoutMode = 'grid'"
                        class="ts-button ts-button-ghost flex min-h-11 items-center gap-2"
                        :class="layoutMode === 'grid' ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400 font-medium' : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'"
                      >
                        <LayoutGrid class="w-4 h-4" />
                        <span>正方形</span>
                      </button>
                      <button
                        @click="showViewOptions = false; layoutMode = 'moments'"
                        class="ts-button ts-button-ghost flex min-h-11 items-center gap-2"
                        :class="layoutMode === 'moments' ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400 font-medium' : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'"
                      >
                        <LayoutList class="w-4 h-4" />
                        <span>朋友圈</span>
                      </button>
                      <button
                        v-if="allowDiaryView"
                        @click="showViewOptions = false; layoutMode = 'diary'"
                        :aria-pressed="layoutMode === 'diary'"
                        class="ts-button ts-button-ghost flex min-h-11 items-center gap-2"
                        :class="layoutMode === 'diary' ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400 font-medium' : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'"
                      >
                        <BookOpen class="w-4 h-4" />
                        <span>日记本</span>
                      </button>
                      <button
                        v-if="allowFolderView"
                        @click="showViewOptions = false; layoutMode = 'folder'"
                        class="ts-button ts-button-ghost flex min-h-11 items-center gap-2"
                        :class="layoutMode === 'folder' ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400 font-medium' : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'"
                      >
                        <FolderTree class="w-4 h-4" />
                        <span>文件夹</span>
                      </button>
                    </div>
                  </div>
                </div>
            </AdaptiveMenu>
           </div>

          <!-- Batch Select -->
          <button 
            @click="enterBatchMode"
            v-if="!mobileMenu" class="ts-glass-button"
            title="批量选择"
          >
            <CheckSquare class="w-5 h-5" />
          </button>

          <!-- Header Actions Slot -->
          <slot name="header-actions"></slot>

          <!-- Mobile Batch Select -->
          <button
            v-if="mobileMenu"
            @click="enterBatchMode"
            class="ts-glass-button"
            title="批量选择"
            aria-label="批量选择"
          >
            <CheckSquare class="w-5 h-5" />
          </button>

          <!-- Desktop Upload Button -->
          <button
            v-if="allowUpload && !mobileMenu"
            @click="$emit('upload')"
            class="ts-glass-button gap-2 text-sm font-medium sm:w-auto sm:px-4"
            title="上传"
            aria-label="上传照片"
          >
            <UploadCloud class="w-5 h-5" />
            <span class="hidden sm:inline">上传</span>
          </button>

        </div>
      </div>

      <!-- Header Extension Slot (e.g. Filter Panel) -->
      <div v-if="$slots['header-extension']" class="pointer-events-auto"><slot name="header-extension"></slot></div>
    </div>

    <div v-if="$slots.hero && layoutMode !== 'diary'" :style="{ marginTop: `-${headerHeight}px` }">
      <slot name="hero"></slot>
    </div>

    <!-- Timeline Navigation Sidebar (Right Sticky) — 文件夹视图有自己的目录树，隐藏时间轴 -->
    <AlbumTimeline
      v-if="layoutMode !== 'folder' && layoutMode !== 'diary'"
      :items="timelineItems"
      :active-date="activeDate"
      @select="scrollToDate"
    />

    <!-- Main Content Area -->
    <div class="photo-page-content mx-auto w-full">
      <div
        v-if="updateAvailable && !isPhotoInteractionActive"
        class="sticky top-[calc(var(--photo-page-header-height)_+_8px)] z-20 flex justify-center mb-3 pointer-events-none"
      >
        <button
          type="button"
          class="ts-button ts-button-primary pointer-events-auto flex items-center gap-2 bg-primary-500 hover:bg-primary-600 text-white shadow-lg shadow-primary-500/30 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          :disabled="refreshingData"
          @click="handleRefreshData"
        >
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': refreshingData }" />
          <span>{{ refreshingData ? '正在刷新…' : updateMessage }}</span>
        </button>
      </div>
      <slot v-if="layoutMode !== 'diary'" name="intro"></slot>

      <!-- 文件夹视图（作为一种布局模式，与自适应/正方形/朋友圈并列） -->
      <FolderBrowser
        v-if="layoutMode === 'folder'"
        v-model:view-size="viewSize"
        :allow-diary-view="allowDiaryView"
        @switch-layout="(m) => layoutMode = m as any"
      />

      <PhotoDiary
        v-else-if="layoutMode === 'diary'"
        ref="diaryRef"
        :store="store"
        :photos="photos"
        :timeline="timelineItems"
        :loading="loading"
        :error="error"
        :initial-date="activeDate"
        @click-photo="openLightbox"
        @active-date="activeDate = $event"
        @entry-update="({ key, state }) => captionMap[key] = state"
        @retry="$emit('retry')"
      >
        <template #empty><slot name="empty" /></template>
      </PhotoDiary>

      <PhotoGallery
        v-else
        ref="galleryRef"
        :store="props.store"
        :photos="photos"
        :timeline-stats="timelineStats"
        :loading="loading"
        :has-more="hasMore"
        :error="error"
        :layout-mode="layoutMode"
        :view-size="viewSize"
        :group-by-date="true"
        :delete-label="deleteLabel"
        :pending-remove-ids="pendingRemoveIds"
        :day-captions="captionMap"
        :day-locations="locationMap"
        :day-highlights="highlightMap"
        :show-moment-caption="showMomentCaption"
        :loading-days="loadingDays"
        v-model:active-date="activeDate"
        @click-photo="openLightbox"
        @load-more="$emit('load-more')"
        @load-range="(offset) => $emit('load-range', offset)"
        @batch-delete="handleBatchDelete"
        @remove-from-album="handleBatchRemoveFromAlbum"
        @add-to-album="handleBatchAddToAlbum"
        @set-album-cover="(ids) => $emit('set-cover', ids)"
        @retry="$emit('retry')"
        @transfer="handleBatchTransfer"
        @batch-edit-location="handleBatchEditLocation"
        @generate-caption="handleGenerateCaption"
        @save-caption="handleSaveCaption"
        @clear-caption="handleClearCaption"
        @visible-months-change="handleVisibleMonthsChange"
      >
        <template #batch-actions="{ selectedIds, clearSelection }">
            <slot name="batch-actions" :selected-ids="selectedIds" :clear-selection="clearSelection"></slot>
        </template>
        
        <template #overlay-actions="{ photo }">
            <slot name="overlay-actions" :photo="photo"></slot>
        </template>

        <template #empty>
            <slot name="empty"></slot>
        </template>
      </PhotoGallery>
      <slot name="after-content"></slot>
    </div>

    <!-- Lightbox -->
    <PhotoLightbox
      :visible="!!lightboxImage"
      :image="lightboxImage"
      :images="photos"
      :current-index="lightboxIndex"
      :has-prev="hasPrev"
      :has-next="hasNext"
      :allow-edit="true"
      :allow-delete="true"
      :allow-add-to-album="true"
      :allow-add-to-person="true"
      :allow-move-to-folder="true"
      :confirm-delete="false"
      :delete-title="deleteLabel"
      @close="closeLightbox"
      @delete="handlePhotoDelete"
      @update="(e) => $emit('photo-update', e)"
      @prev="handlePrev"
      @next="handleNext"
      @select="handleLightboxSelect"
      @add-to-album="handleAddToAlbumFromLightbox"
      @transfer="handleLightboxTransfer"
    />

    <!-- Delete Confirmation -->
    <ConfirmDialog
      v-model:visible="showDeleteConfirm"
      title="确认操作"
      :message="confirmMessage"
      confirm-text="确定"
      cancel-text="取消"
      type="danger"
      @confirm="confirmDelete"
    />

    <!-- Particle Effect -->
    <ParticleExplosion
      v-if="showParticle"
      :active="showParticle"
      @complete="showParticle = false"
    />
    <!-- Album Select Modal -->
    <AlbumSelector
      v-model:visible="showAlbumSelectModal"
      :photo-ids="tempSelectedIds"
      @success="closeAlbumSelectModal"
    />
    <!-- Extra Modals Slot -->
    <slot name="extra-modals"></slot>

    <!-- Folder Selection Dialog -->
    <FolderSelectionDialog
      v-model:visible="showFolderSelector"
      :action="folderAction"
      :photo-ids="transferPhotoIds"
      :default-sub-folder="title"
      @success="handleTransferSuccess"
    />

    <!-- Batch Location Editor -->
    <LocationBatchEditor
      v-model="showLocationBatchEditor"
      :photo-ids="locationEditPhotoIds"
      :photos="locationEditPhotos"
      @success="handleLocationBatchSuccess"
    />
  </div>
</template>

<script setup lang="ts">
import BackButton from '@/components/ui/BackButton.vue'
import AdaptiveMenu from '@/components/ui/AdaptiveMenu.vue'
import { ref, computed, nextTick, onMounted, onUnmounted, watch, useSlots } from 'vue'
import { Capacitor, SystemBars, SystemBarsStyle, SystemBarType } from '@capacitor/core'
import { injectTheme } from '@/composables/useTheme'
import { useMediaQuery, onClickOutside, useIntersectionObserver, useResizeObserver } from '@vueuse/core'
import {
  Grid3x3, Grid2x2, Maximize, LayoutDashboard, LayoutGrid, LayoutList,
  UploadCloud, CheckSquare, Settings2, FolderTree, RefreshCw, BookOpen } from 'lucide-vue-next'
import { ElMessageBox, ElMessage, ElNotification } from 'element-plus'

import PhotoGallery from '@/components/PhotoGallery.vue'
import PhotoDiary from '@/components/PhotoDiary.vue'
import FolderBrowser from '@/views/album/folder/FolderBrowser.vue'
import AlbumTimeline from '@/components/AlbumTimeline.vue'
import { usePhotoViewer } from '@/composables/usePhotoViewer'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import ParticleExplosion from '@/components/ParticleExplosion.vue'
import AlbumSelector from '@/components/AlbumSelector.vue'
import FolderSelectionDialog from '@/components/FolderSelectionDialog.vue'
import LocationBatchEditor from '@/components/LocationBatchEditor.vue'
import type { AlbumImage } from '@/types/album'

const slots = useSlots()
const { isDarkMode } = injectTheme()
function updateStatusBar(overlay: boolean) {
  if (Capacitor.getPlatform() !== 'android') return
  // The hero has a dark top gradient, so white status icons remain readable.
  void SystemBars.setStyle({
    bar: SystemBarType.StatusBar,
    style: overlay || isDarkMode.value ? SystemBarsStyle.Dark : SystemBarsStyle.Light,
  }).catch(error => console.warn('Unable to update status bar style', error))
}
onUnmounted(() => updateStatusBar(false))

import { useAlbumStore } from '@/stores/albumStore'
import { usePhotoStore } from '@/stores/photoStore'
import { useMomentCaptions } from '@/composables/useMomentCaptions'
import { useMomentLocations } from '@/composables/useMomentLocations'
import { useMomentHighlights } from '@/composables/useMomentHighlights'

const props = withDefaults(defineProps<{
  title?: string
  subtitle?: string
  loading?: boolean
  loadingTitle?: boolean
  error?: string | null
  photos?: AlbumImage[]
  timelineItems?: any[]
  allowUpload?: boolean
  deleteLabel?: string
  hasMore?: boolean
  timelineStats?: any
  confirmRemove?: boolean
  pendingRemoveIds?: Set<string>
  store?: any
  showBack?: boolean
  allowFolderView?: boolean
  allowDiaryView?: boolean
  updateAvailable?: boolean
  updateMessage?: string
}>(), {
  title: '',
  subtitle: '',
  loading: false,
  loadingTitle: false,
  error: null,
  photos: () => [],
  timelineItems: () => [],
  allowUpload: false,
  deleteLabel: '删除',
  hasMore: false,
  timelineStats: null,
  confirmRemove: false,
  pendingRemoveIds: () => new Set(),
  showBack: true,
  allowFolderView: false,
  allowDiaryView: false,
  updateAvailable: false,
  updateMessage: '发现照片更新，点击刷新'
})

const emit = defineEmits<{
  (e: 'back'): void
  (e: 'upload'): void
  (e: 'delete', ids: string[]): void // General delete/remove event
  (e: 'load-more'): void
  (e: 'load-range', offset: number): void
  (e: 'retry'): void
  (e: 'set-cover', ids: string[]): void
  (e: 'add-to-album', id: string): void
  (e: 'photo-update', event: any): void
  (e: 'remove-from-album', ids: string[]): void // General delete/remove event
  (e: 'confirm-delete', ids: string[], callback: (success: boolean) => void): void
  (e: 'refresh-data', done: (success?: boolean) => void): void
}>()

// UI State
const pageTopRef = ref<HTMLElement | null>(null)
const headerScrolled = ref(false)
useIntersectionObserver(pageTopRef, ([entry]) => {
  if (entry) headerScrolled.value = !entry.isIntersecting
})
const headerRef = ref<HTMLElement | null>(null)
const headerHeight = ref(0)
useResizeObserver(headerRef, () => {
  headerHeight.value = headerRef.value?.offsetHeight ?? 0
}, { box: 'border-box' })
const viewSize = ref<'sm' | 'md' | 'lg'>('md')
const layoutMode = ref<'masonry' | 'grid' | 'list' | 'waterfall' | 'moments' | 'folder' | 'diary'>('grid')
watch([isDarkMode, layoutMode], () => updateStatusBar(Boolean(slots.hero) && !['folder', 'diary'].includes(layoutMode.value)), { immediate: true })
const activeDate = ref('')
const { currentPhoto: lightboxImage, currentIndex: lightboxIndex, hasPrev, hasNext, open: openLightbox, close: closeLightbox, prev: handlePrev, next: handleNext } = usePhotoViewer(() => props.photos)
const mobileMenu = useMediaQuery('(max-width: 639px)')
const showViewOptions = ref(false)
const viewOptionsRef = ref<InstanceType<typeof AdaptiveMenu> | null>(null)
const galleryRef = ref<InstanceType<typeof PhotoGallery> | null>(null)
const diaryRef = ref<InstanceType<typeof PhotoDiary> | null>(null)
const refreshingData = ref(false)
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 768)
const scrolling = ref(false)
let scrollingTimer: ReturnType<typeof setTimeout> | undefined
const handleBrowsingScroll = () => {
  scrolling.value = true
  clearTimeout(scrollingTimer)
  scrollingTimer = setTimeout(() => { scrolling.value = false }, 600)
}
onMounted(() => document.addEventListener('scroll', handleBrowsingScroll, { capture: true, passive: true }))
onUnmounted(() => {
  document.removeEventListener('scroll', handleBrowsingScroll, true)
  clearTimeout(scrollingTimer)
})
const isPhotoInteractionActive = computed(() =>
  scrolling.value || !!lightboxImage.value || !!galleryRef.value?.isSelectionMode || !!diaryRef.value?.isEditing
)
watch(layoutMode, async (mode, previous) => {
  showViewOptions.value = false
  if (previous === 'diary' && mode !== 'folder') {
    await nextTick()
    galleryRef.value?.scrollToDate(activeDate.value, 'auto')
  }
})

const getScrollContainer = (): HTMLElement | Window => {
  const main = document.querySelector('main') as HTMLElement | null
  return main && window.getComputedStyle(main).overflowY === 'auto' ? main : window
}

const captureVisibleMonth = () => {
  const blocks = Array.from(document.querySelectorAll<HTMLElement>('.month-block[data-month]'))
  const block = blocks.find((item) => {
    const rect = item.getBoundingClientRect()
    return rect.bottom > 0 && rect.top < window.innerHeight
  })
  return block ? { month: block.dataset.month, top: block.getBoundingClientRect().top } : null
}

const restoreVisibleMonth = (anchor: { month?: string; top: number } | null) => {
  if (!anchor?.month) return false
  const block = document.querySelector<HTMLElement>(`.month-block[data-month="${CSS.escape(anchor.month)}"]`)
  if (!block) return false
  const delta = block.getBoundingClientRect().top - anchor.top
  const container = getScrollContainer()
  container.scrollBy({ top: delta, behavior: 'auto' })
  return true
}

const captureVisiblePhoto = (excludedIds: string[]) => {
  const excluded = new Set(excludedIds)
  const container = getScrollContainer()
  const containerRect = container === window
    ? { top: 0, bottom: window.innerHeight }
    : (container as HTMLElement).getBoundingClientRect()
  const gallery = (galleryRef.value?.$el as HTMLElement | undefined) ?? document
  const element = Array.from(gallery.querySelectorAll<HTMLElement>('[data-photo-id]')).find((item) => {
    const id = item.dataset.photoId
    if (!id || excluded.has(id)) return false
    const rect = item.getBoundingClientRect()
    return rect.bottom > containerRect.top && rect.top < containerRect.bottom
  })
  return element
    ? { id: element.dataset.photoId!, top: element.getBoundingClientRect().top }
    : null
}

const restoreVisiblePhoto = (anchor: { id: string; top: number } | null) => {
  if (!anchor) return
  const gallery = (galleryRef.value?.$el as HTMLElement | undefined) ?? document
  const element = gallery.querySelector<HTMLElement>(`[data-photo-id="${CSS.escape(anchor.id)}"]`)
  if (!element) return
  const container = getScrollContainer()
  container.scrollBy({
    top: element.getBoundingClientRect().top - anchor.top,
    behavior: 'auto',
  })
}

const refreshDataPreservingPosition = (): Promise<boolean> => {
  if (refreshingData.value || isPhotoInteractionActive.value) return Promise.resolve(false)
  refreshingData.value = true
  const monthAnchor = captureVisibleMonth()
  const photoAnchor = captureVisiblePhoto([])
  const container = getScrollContainer()
  const previousScrollTop = container === window ? window.scrollY : (container as HTMLElement).scrollTop
  return new Promise((resolve) => {
    emit('refresh-data', (success = true) => {
      void nextTick(() => requestAnimationFrame(() => requestAnimationFrame(() => {
        // Restore the month first so the virtual gallery renders the same area,
        // then align the exact photo if it still exists.
        if (!restoreVisibleMonth(monthAnchor)) {
          container.scrollTo({ top: previousScrollTop, behavior: 'auto' })
        }
        requestAnimationFrame(() => {
          restoreVisiblePhoto(photoAnchor)
          refreshingData.value = false
          resolve(success)
        })
      })))
    })
  })
}

const handleRefreshData = () => { void refreshDataPreservingPosition() }

const handleResize = () => {
  isMobile.value = window.innerWidth < 768
}
window.addEventListener('resize', handleResize)
onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})

const albumStore = useAlbumStore()
const photoStore = usePhotoStore()
const store = computed(() => props.store || photoStore)

// ---- Moments 朋友圈日文案 ----
// MVP 阶段只在 "全部照片" 视图启用（scope='all'）
const showMomentCaption = computed(() =>
  layoutMode.value === 'moments' && (store.value?.currentContext?.type === 'all')
)
const {
  captionMap,
  loadingDays,
  loadMonth,
  generate: generateCaption,
  save: saveCaption,
  clear: clearCaption,
  abortAll: abortAllCaptions,
} = useMomentCaptions()

// 朋友圈日位置：实时从 photo_metadata 聚合（景区优先），不落库；
// 与 caption 服从相同的可见月份触发机制，同一个朋友圈视图中共享。
const { locationMap, loadMonth: loadLocationMonth } = useMomentLocations()

// 朋友圈日精选：服务端做相似去重 + memory/quality 打分排序，实时计算不落库。
const { highlightMap, loadMonth: loadHighlightMonth } = useMomentHighlights()

const handleVisibleMonthsChange = (months: { year: number; month: number }[]) => {
  if (!showMomentCaption.value) return
  months.forEach((m) => {
    loadMonth(m.year, m.month)
    loadLocationMonth(m.year, m.month)
    loadHighlightMonth(m.year, m.month)
  })
}

const handleGenerateCaption = async (payload: { day: { key: string }; force?: boolean }) => {
  try {
    await generateCaption(payload.day.key, { force: !!payload.force })
  } catch (e: any) {
    const raw = (e?.message || e?.response?.data?.detail || '').toString()
    // 根据错误关键字给出类型化提示，避免用户看到模糊的 "生成失败"
    // 共 3 种常见情形：
    //   1) 未配置 AI 模型            → 引导到设置页（不跳转、只提示）
    //   2) 当天没有可识别的照片      → 说明 photo_time 缺失，请先完成元数据提取
    //   3) LLM 返回为空 / 内部错误  → 提示重试
    if (/AI\s*模型|AI\s*连接|API\s*Key/i.test(raw)) {
      ElNotification({
        type: 'warning',
        title: '还没配置 AI 模型',
        message: '请到「设置 → AI 相关配置」选一个对话模型后再试。',
        duration: 6000,
      })
      return
    }
    if (/没有照片|无法生成文案/i.test(raw)) {
      ElNotification({
        type: 'info',
        title: '这一天暂时无法生成',
        message: '这一天的照片还没识别到拍摄时间，稍后再试。也可以自己点「手动写」写一段。',
        duration: 6000,
      })
      return
    }
    if (/LLM\s*返回为空|内部错误/i.test(raw)) {
      ElNotification({
        type: 'error',
        title: 'AI 没返回内容',
        message: '稍后再试一次。如果一直这样，检查一下 AI 配置。',
        duration: 6000,
      })
      return
    }
    // 其他未知错误：保底提示，但把系统消息完整展示。
    ElMessage.error(raw || 'AI 生成失败，请稍后重试')
  }
}

const handleSaveCaption = async (payload: { day: { key: string }; text: string }) => {
  try {
    await saveCaption(payload.day.key, payload.text)
    ElMessage.success('已保存')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  }
}

const handleClearCaption = async (payload: { day: { key: string } }) => {
  try {
    await clearCaption(payload.day.key)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '操作失败')
  }
}

// 切换布局或组件卸载时，中止所有进行中的 SSE 流
watch(showMomentCaption, (v) => {
  if (!v) abortAllCaptions()
})
onUnmounted(() => {
  abortAllCaptions()
})

// Delete/Remove State
const showDeleteConfirm = ref(false)
const showAlbumSelectModal = ref(false)
const idsToDelete = ref<string[]>([])
const lightboxDeleteId = ref<string | null>(null)
const showParticle = ref(false)
const pendingRemoveIds = ref(new Set<string>())
// UI State
const showUploadModal = ref(false)
const tempSelectedIds = ref<string[]>([])

// Transfer state
const showFolderSelector = ref(false)
const folderAction = ref<'move' | 'copy'>('move')
const transferPhotoIds = ref<string[]>([])

// Batch location edit state
const showLocationBatchEditor = ref(false)
const locationEditPhotoIds = ref<string[]>([])
const locationEditPhotos = computed(() => props.photos?.filter(p => locationEditPhotoIds.value.includes(p.id)) || [])
const handleLightboxTransfer = (action: 'move' | 'copy') => {
  if (lightboxImage.value) {
    folderAction.value = action
    transferPhotoIds.value = [lightboxImage.value.id]
    showFolderSelector.value = true
  }
}

const handleBatchTransfer = (action: 'move' | 'copy', ids: string[]) => {
  folderAction.value = action
  transferPhotoIds.value = ids
  showFolderSelector.value = true
}

const handleTransferSuccess = () => {
  if (galleryRef.value) {
    galleryRef.value.exitSelectionMode()
  }
  closeLightbox()
  emit('retry')
}

const handleBatchEditLocation = (ids: string[]) => {
  locationEditPhotoIds.value = ids
  showLocationBatchEditor.value = true
}

const handleLocationBatchSuccess = () => {
  if (galleryRef.value) {
    galleryRef.value.exitSelectionMode()
  }
  emit('retry')
}

onClickOutside(viewOptionsRef, () => {
  if (!mobileMenu.value) showViewOptions.value = false
})

const scrollToDate = (date: string, behavior: ScrollBehavior = 'smooth') => {
  if (layoutMode.value === 'diary') diaryRef.value?.scrollToDate(date)
  else galleryRef.value?.scrollToDate(date, behavior)
  activeDate.value = date
}

const enterBatchMode = async () => {
  if (layoutMode.value === 'diary') {
    layoutMode.value = 'grid'
    await nextTick()
    galleryRef.value?.scrollToDate(activeDate.value, 'auto')
  }
  galleryRef.value?.enterSelectionMode()
}

const closeAlbumSelectModal = () => {
  showAlbumSelectModal.value = false
  tempSelectedIds.value = []
  galleryRef.value?.exitSelectionMode()
}

// Lightbox
const handleLightboxSelect = (index: number) => {
  const target = props.photos[index]
  if (target) lightboxImage.value = target
}

// Delete Logic
const handleBatchDelete = (ids: string[]) => {
  if (ids.length === 0) return
  lightboxDeleteId.value = null
  idsToDelete.value = ids
  showDeleteConfirm.value = true
}

// Reuse for remove-from-album which is essentially a delete from this view
const handleBatchRemoveFromAlbum = (ids: string[]) => {
    if (ids.length === 0) return
    // 确认对话框
    ElMessageBox.confirm(`确定要将选中的 ${ids.length} 张照片移出相册吗？`, '确认', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
    }).then(() => {
        if (props.confirmRemove) {
            handleBatchDelete(ids)
        } else {
            emit('remove-from-album', ids)
            galleryRef.value?.exitSelectionMode()
        }
    }).catch(() => {
        // 用户点击取消
    })
}

const handlePhotoDelete = (id: string) => {
    lightboxDeleteId.value = id
    idsToDelete.value = [id]
    showDeleteConfirm.value = true
}

const confirmMessage = computed(() => {
  if (props.deleteLabel === '删除') {
    return `确定要删除选中的 ${idsToDelete.value.length} 张照片吗？删除的照片将放入回收站，可稍后恢复。`
  }
  return `确定要${props.deleteLabel}选中的 ${idsToDelete.value.length} 张照片吗？`
})

const confirmDelete = () => {
    const scrollAnchor = captureVisiblePhoto(idsToDelete.value)
    emit('confirm-delete', idsToDelete.value, (success: boolean) => {
        if (success) {
            // Show particle if needed (usually for permanent delete)
            if (props.deleteLabel === '删除') {
                showParticle.value = true
            }
            galleryRef.value?.exitSelectionMode()
            if (lightboxDeleteId.value) closeLightbox()
            nextTick(() => requestAnimationFrame(() => requestAnimationFrame(() => {
                restoreVisiblePhoto(scrollAnchor)
            })))
        }
        lightboxDeleteId.value = null
    })
}

const handleAddToAlbumFromLightbox = (img: AlbumImage) => {
    tempSelectedIds.value = [img.id]
    showAlbumSelectModal.value = true
}

const handleBatchAddToAlbum = (ids: string[]) => {
  if (ids.length === 0) return
  tempSelectedIds.value = ids
  showAlbumSelectModal.value = true
  albumStore.fetchAlbums()
  console.log('handleBatchAddToAlbum', ids)
}

// Expose pendingRemoveIds to parent if needed, or methods to manipulate it
defineExpose({
    galleryRef,
    pendingRemoveIds,
    refreshDataPreservingPosition,
    isPhotoInteractionActive
})
</script>

<style scoped>
/* Scoped styles if necessary */
</style>
