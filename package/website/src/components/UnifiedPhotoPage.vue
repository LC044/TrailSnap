<template>
  <div class="ts-browse-page unified-photo-page relative mx-auto w-full max-w-screen-2xl py-0 px-[var(--ts-page-gutter)] min-h-screen" :class="{ 'photo-diary-mode': layoutMode === 'diary' }" :style="{ '--photo-page-header-height': `${headerHeight}px` }">
    <span ref="pageTopRef" class="pointer-events-none absolute left-0 top-0 h-px w-px" aria-hidden="true"></span>
    <!-- Toolbar & Header（文件夹视图有自己的工具栏，这里整条隐藏以节省移动端空间） -->
    <div v-if="layoutMode !== 'folder'" ref="headerRef" data-photo-header class="pointer-events-none sticky top-0 z-[45] -mx-[var(--ts-page-gutter)] px-[var(--ts-page-gutter)] pt-[var(--ts-safe-area-top)]">
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
            <AdaptiveMenu v-model="showViewOptions" title="照片视图">
              <div class="photo-view-settings">
                <section v-if="enableTimeBrowse" class="photo-view-section" aria-labelledby="photo-sort-heading">
                  <h2 id="photo-sort-heading" class="photo-view-label">排序依据</h2>
                  <div class="photo-choice-grid grid-cols-2" role="group" aria-label="排序依据" data-testid="photo-time-sort">
                    <button type="button" class="photo-choice" :aria-pressed="store.timeField === 'photo_time'" @click="changeSort('photo_time')">照片时间</button>
                    <button type="button" class="photo-choice" :aria-pressed="store.timeField === 'upload_time'" @click="changeSort('upload_time')">添加时间</button>
                  </div>
                </section>

                <section v-if="layoutMode !== 'diary'" class="photo-view-section" aria-labelledby="photo-size-heading">
                  <h2 id="photo-size-heading" class="photo-view-label">图片大小</h2>
                  <div class="photo-choice-grid grid-cols-3" role="group" aria-label="图片大小">
                    <button v-for="size in photoSizeOptions" :key="size.value" type="button"
                      class="photo-choice photo-size-choice" :aria-label="`图片大小：${size.label}`" :aria-pressed="viewSize === size.value" @click="viewSize = size.value">
                      <component :is="size.icon" class="h-4 w-4" aria-hidden="true" />
                      <span>{{ size.label }}</span>
                    </button>
                  </div>
                </section>

                <section class="photo-view-section" aria-labelledby="photo-layout-heading">
                  <h2 id="photo-layout-heading" class="photo-view-label">布局模式</h2>
                  <div class="photo-layout-options" role="group" aria-label="布局模式">
                    <button v-for="option in photoLayoutOptions" :key="option.value" type="button"
                      class="photo-option-row" :aria-pressed="layoutMode === option.value"
                      @click="layoutMode = option.value; showViewOptions = false">
                      <component :is="option.icon" class="h-[18px] w-[18px] shrink-0" aria-hidden="true" />
                      <span class="flex-1">{{ option.label }}</span>
                      <Check v-if="layoutMode === option.value" class="h-4 w-4 shrink-0" aria-hidden="true" />
                    </button>
                  </div>
                </section>

                <div v-if="enableTimeBrowse || (allowUpload && mobileMenu)" class="photo-view-actions">
                  <button v-if="enableTimeBrowse" type="button" class="photo-option-row" @click="showViewOptions = false; enterBatchMode()">
                    <CheckSquare class="h-[18px] w-[18px]" aria-hidden="true" /><span>批量选择</span>
                  </button>
                  <button v-if="enableTimeBrowse" type="button" class="photo-option-row" @click="showViewOptions = false; backToLatest()">
                    <RefreshCw class="h-[18px] w-[18px]" aria-hidden="true" /><span>回到最新</span>
                  </button>
                  <button v-if="allowUpload && mobileMenu" type="button" class="photo-option-row" @click="showViewOptions = false; $emit('upload')">
                    <UploadCloud class="h-[18px] w-[18px]" aria-hidden="true" /><span>上传照片</span>
                  </button>
                </div>
              </div>
            </AdaptiveMenu>
           </div>

          <button v-if="enableTimeBrowse" type="button" class="ts-glass-button text-sm font-medium"
            data-testid="photo-view-cycle" :aria-busy="timeChanging"
            :title="`当前${timeViewLabel}视图，点击切换为${nextTimeViewLabel}视图`"
            :aria-label="`当前${timeViewLabel}视图，点击切换为${nextTimeViewLabel}视图`"
            :class="{ 'animate-pulse motion-reduce:animate-none': timeChanging }"
            @click="changeGranularity(nextGranularity)">{{ timeViewLabel }}</button>
          <span v-if="enableTimeBrowse && timeChanging" role="status" class="sr-only">正在定位照片</span>

          <!-- Batch Select -->
          <button 
            @click="enterBatchMode"
            v-if="!enableTimeBrowse && !mobileMenu" class="ts-glass-button"
            title="批量选择"
          >
            <CheckSquare class="w-5 h-5" />
          </button>

          <!-- Header Actions Slot -->
          <slot name="header-actions"></slot>

          <!-- Mobile Batch Select -->
          <button
            v-if="!enableTimeBrowse && mobileMenu"
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
      <p v-if="timeError" role="alert" class="ts-surface mb-3 p-3 text-sm">{{ timeError }} <button class="text-primary-500" @click="retryTimeChange">重试</button></p>
      <p v-if="enableTimeBrowse && granularity !== 'day' && error" role="alert" class="ts-surface p-3">{{ error }} <button class="text-primary-500" @click="$emit('retry')">重试</button></p>
      <PhotoTimeOverview v-if="enableTimeBrowse && granularity !== 'day'" ref="timeOverviewRef"
        :months="timelineStats?.months || []" :granularity="granularity as 'year' | 'month'" :anchor="timeAnchor"
        :map-photo="store.mapTimelinePhoto" @select="drillIntoTime" />
      <div v-if="enableTimeBrowse && granularity !== 'day' && !error && !timelineStats?.total_photos" class="py-12 text-center ts-muted" role="status">
        {{ loading ? '正在加载照片…' : '没有符合条件的照片' }}
        <button v-if="!loading" class="ts-button ts-button-ghost mt-3" @click="$emit('clear-filters')">清除筛选</button>
      </div>
      <FolderBrowser
        v-if="layoutMode === 'folder'"
        v-show="granularity === 'day'"
        v-model:view-size="viewSize"
        :allow-diary-view="allowDiaryView"
        @switch-layout="(m) => layoutMode = m as any"
      />

      <PhotoDiary
        v-else-if="layoutMode === 'diary'"
        v-show="granularity === 'day'"
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
        v-show="granularity === 'day'"
        :active="granularity === 'day'"
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
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import PhotoTimeOverview from '@/components/PhotoTimeOverview.vue'
import { timelineParts, nearestTimelinePhoto, type TimeField, type TimeGranularity } from '@/utils/photoTimeline'
import BackButton from '@/components/ui/BackButton.vue'
import AdaptiveMenu from '@/components/ui/AdaptiveMenu.vue'
import { ref, computed, nextTick, onMounted, onUnmounted, watch, useSlots } from 'vue'
import { Capacitor, SystemBars, SystemBarsStyle, SystemBarType } from '@capacitor/core'
import { injectTheme } from '@/composables/useTheme'
import { useMediaQuery, useIntersectionObserver, useResizeObserver } from '@vueuse/core'
import {
  Grid3x3, Grid2x2, Maximize, LayoutDashboard, LayoutGrid, LayoutList,
  UploadCloud, Check, CheckSquare, Settings2, FolderTree, RefreshCw, BookOpen } from 'lucide-vue-next'
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

import { albumService } from '@/api/album'
import { useAlbumStore } from '@/stores/albumStore'
import { usePhotoStore } from '@/stores/photoStore'
import { useMomentCaptions } from '@/composables/useMomentCaptions'
import { useMomentLocations } from '@/composables/useMomentLocations'
import { useMomentHighlights } from '@/composables/useMomentHighlights'

const props = withDefaults(defineProps<{
  enableTimeBrowse?: boolean
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
  (e: 'clear-filters'): void
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
const photoSizeOptions = [
  { value: 'sm', label: '小图', icon: Grid3x3 },
  { value: 'md', label: '中图', icon: Grid2x2 },
  { value: 'lg', label: '大图', icon: Maximize },
] as const
const photoLayoutOptions = computed(() => [
  { value: 'waterfall', label: '自适应', icon: LayoutDashboard },
  { value: 'grid', label: '正方形', icon: LayoutGrid },
  { value: 'moments', label: '朋友圈', icon: LayoutList },
  ...(props.allowDiaryView ? [{ value: 'diary' as const, label: '日记本', icon: BookOpen }] : []),
  ...(props.allowFolderView ? [{ value: 'folder' as const, label: '文件夹', icon: FolderTree }] : []),
] as const)
watch([isDarkMode, layoutMode], () => updateStatusBar(Boolean(slots.hero) && !['folder', 'diary'].includes(layoutMode.value)), { immediate: true })
const activeDate = ref('')
const { currentPhoto: lightboxImage, currentIndex: lightboxIndex, hasPrev, hasNext, open: openLightbox, close: closeLightbox, prev: handlePrev, next: handleNext } = usePhotoViewer(() => props.photos)
const mobileMenu = useMediaQuery('(max-width: 639px)')
const showViewOptions = ref(false)
const galleryRef = ref<InstanceType<typeof PhotoGallery> | null>(null)
const diaryRef = ref<InstanceType<typeof PhotoDiary> | null>(null)
const refreshingData = ref(false)
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 768)
const scrolling = ref(false)
let scrollingTimer: ReturnType<typeof setTimeout> | undefined
const handleBrowsingScroll = () => {
  scrolling.value = true
  if (props.enableTimeBrowse && granularity.value !== 'day') {
    const photo = timeOverviewRef.value?.capture()
    if (photo) {
      const parts = timelineParts(photo.timestamp)
      activeDate.value = parts.year ? `${parts.year}年${String(parts.month).padStart(2, '0')}月` : '时间未知'
    }
  }
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
  const minTop = containerRect.top + headerHeight.value + 8
  const candidates = Array.from(gallery.querySelectorAll<HTMLElement>('[data-photo-id]')).filter(item => {
    const id = item.dataset.photoId
    if (!id || excluded.has(id)) return false
    const rect = item.getBoundingClientRect()
    return rect.bottom > minTop && rect.top < containerRect.bottom
  })
  const element = candidates.find(item => {
    const rect = item.getBoundingClientRect()
    return rect.top >= minTop && rect.bottom <= containerRect.bottom
  }) ?? candidates[0]
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

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const granularity = computed<TimeGranularity>(() => props.enableTimeBrowse ? store.value.browseGranularity : 'day')
const timeViewLabels = { day: '日', month: '月', year: '年' } as const
const nextGranularity = computed<TimeGranularity>(() => ({ day: 'month', month: 'year', year: 'day' } as const)[granularity.value])
const timeViewLabel = computed(() => timeViewLabels[granularity.value])
const nextTimeViewLabel = computed(() => timeViewLabels[nextGranularity.value])
const timeOverviewRef = ref<InstanceType<typeof PhotoTimeOverview> | null>(null)
const timeAnchor = ref<AlbumImage | null>(null)
const timeChanging = ref(false)
const timeError = ref('')
let timeIntent = 0
let retryTimeChange = () => {}
let originalLayout: typeof layoutMode.value | null = null
let anchorTop: number | undefined
let lastViewedId = ''
watch(lightboxImage, (image, previous) => {
  if (!image && previous) lastViewedId = previous.id
})
const preferenceKey = () => `photo-timeline-preferences:${userStore.userInfo?.id ?? 'anonymous'}`
const saveTimePreference = () => {
  try { localStorage.setItem(preferenceKey(), JSON.stringify({ view: granularity.value, time: store.value.timeField })) } catch {}
}
const captureTimeAnchor = () => {
  if (granularity.value !== 'day') return timeOverviewRef.value?.capture() ?? timeAnchor.value
  const visible = captureVisiblePhoto([])
  anchorTop = visible ? Math.max(visible.top, headerHeight.value + 12) : undefined
  const viewed = props.photos.find(photo => photo.id === lastViewedId)
  return viewed ?? props.photos.find(photo => photo.id === visible?.id) ?? timeAnchor.value
}
const locateTimeAnchor = async (focus = true) => {
  await nextTick()
  const photo = timeAnchor.value
  if (!photo) return
  const parts = timelineParts(photo.timestamp)
  activeDate.value = parts.year ? `${parts.year}年${String(parts.month).padStart(2, '0')}月` : '时间未知'
  if (granularity.value === 'day') {
    if (layoutMode.value === 'diary') diaryRef.value?.scrollToDate(parts.dayKey)
    else await galleryRef.value?.scrollToPhoto(photo, anchorTop)
  } else timeOverviewRef.value?.locate(parts.year, parts.month, focus)
}
const publishTimeState = () => {
  saveTimePreference()
  void router.push({ query: { ...route.query, view: granularity.value, time: store.value.timeField, anchor: timeAnchor.value?.id || undefined } })
}
const animateTimeContent = () => {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return
  const element = granularity.value === 'day' ? galleryRef.value?.$el : timeOverviewRef.value?.$el
  element?.animate?.([{ opacity: .65, transform: 'translateY(4px)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 220, easing: 'ease-out' })
}
const changeGranularity = async (target: TimeGranularity, clicked?: AlbumImage, navigation = false) => {
  if (!props.enableTimeBrowse) return
  const intent = ++timeIntent
  if (clicked) { anchorTop = undefined; lastViewedId = '' }
  const photo = clicked ?? captureTimeAnchor() ?? (props.timelineStats?.months?.[0]?.cover ? store.value.mapTimelinePhoto(props.timelineStats.months[0].cover) : null)
  timeChanging.value = true; timeError.value = ''
  retryTimeChange = () => { void changeGranularity(target, photo ?? undefined, navigation) }
  try {
    if (target === 'day' && photo) {
      const parts = timelineParts(photo.timestamp)
      await store.value.loadPhotosByMonth(parts.year, parts.month)
      if (store.value.error) throw new Error(store.value.error)
    }
    if (intent !== timeIntent) return
    const resolved = props.photos.find(item => item.id === photo?.id)
    timeAnchor.value = target === 'day' && photo && !resolved
      ? nearestTimelinePhoto(props.photos, photo)
      : photo
    if (target !== 'day' && ['folder', 'diary'].includes(layoutMode.value)) {
      originalLayout = layoutMode.value; layoutMode.value = 'grid'
    } else if (target === 'day' && originalLayout) {
      layoutMode.value = originalLayout; originalLayout = null
    }
    store.value.browseGranularity = target
    await locateTimeAnchor()
    if (intent !== timeIntent) return
    animateTimeContent()
    if (!navigation) publishTimeState()
  } catch {
    if (intent === timeIntent) timeError.value = '暂时无法加载目标照片，请重试。'
  } finally { if (intent === timeIntent) timeChanging.value = false }
}
const drillIntoTime = (photo: AlbumImage) => changeGranularity(granularity.value === 'year' ? 'month' : 'day', photo)
const changeSort = async (field: TimeField, navigation = false, provided?: AlbumImage | null) => {
  const intent = ++timeIntent
  const photo = provided ?? captureTimeAnchor()
  timeChanging.value = true; timeError.value = ''
  retryTimeChange = () => { void changeSort(field, navigation, photo) }
  try {
    const changed = await store.value.changeTimeField(field, photo, () => intent === timeIntent, granularity.value === 'day')
    if (!changed || intent !== timeIntent) return
    timeAnchor.value = store.value.images.find((item: AlbumImage) => item.id === photo?.id) ?? store.value.images[0] ?? null
    await locateTimeAnchor()
    if (intent !== timeIntent) return
    animateTimeContent()
    if (!navigation) publishTimeState()
  } catch { if (intent === timeIntent) timeError.value = '暂时无法切换排序，请重试。' }
  finally { if (intent === timeIntent) timeChanging.value = false }
}
const backToLatest = async () => {
  const cover = props.timelineStats?.months?.[0]?.cover
  if (!cover) return
  anchorTop = undefined; lastViewedId = ''
  await changeGranularity(granularity.value, store.value.mapTimelinePhoto(cover))
}
const timeNavigationKey = () => [route.query.view, route.query.time, route.query.anchor].join(':')
const restoreTimeNavigation = async () => {
  const navigationKey = timeNavigationKey()
  try {
    if (!props.enableTimeBrowse || route.name !== 'Photos') return
    const target = ['year', 'month', 'day'].includes(String(route.query.view)) ? String(route.query.view) as TimeGranularity : 'day'
    const field: TimeField = route.query.time === 'upload_time' ? 'upload_time' : 'photo_time'
    const id = String(route.query.anchor ?? '')
    if (target === granularity.value && field === store.value.timeField && (!id || id === timeAnchor.value?.id)) return
    let photo = props.photos.find(item => item.id === id)
    if (!photo && id) {
      const rows = await albumService.getAllPhotos(0, 1, { ...store.value.getPickerSearchFilters(), ids: [id] })
      if (navigationKey !== timeNavigationKey()) return
      if (rows[0]) photo = store.value.mapTimelinePhoto(rows[0])
    }
    if (field !== store.value.timeField) await changeSort(field, true, photo)
    else if (photo) timeAnchor.value = photo
    if (navigationKey !== timeNavigationKey()) return
    await changeGranularity(target, timeAnchor.value ?? undefined, true)
  } catch {
    timeError.value = '暂时无法恢复照片位置，请重试。'
    retryTimeChange = () => { void restoreTimeNavigation() }
  }
}
watch(timeNavigationKey, restoreTimeNavigation)
watch(() => props.timelineStats, async stats => {
  if (!props.enableTimeBrowse || !stats) return
  if (timeAnchor.value) {
    const parts = timelineParts(timeAnchor.value.timestamp)
    if (!stats.timeline.some((day: { year: number; month: number }) => day.year === parts.year && day.month === parts.month)) {
      timeAnchor.value = nearestTimelinePhoto((stats.months ?? []).map((month: import('@/types/album').TimelineMonth) => store.value.mapTimelinePhoto(month.cover)), timeAnchor.value)
    }
  }
  if (!timeAnchor.value) {
    const id = String(route.query.anchor ?? '')
    let rows: import('@/types/album').Photo[] = []
    try { rows = id ? await albumService.getAllPhotos(0, 1, { ...store.value.getPickerSearchFilters(), ids: [id] }) : [] }
    catch { timeError.value = '暂时无法恢复照片位置，请重试。'; retryTimeChange = () => { void restoreTimeNavigation() }; return }
    if (stats !== props.timelineStats || id !== String(route.query.anchor ?? '')) return
    timeAnchor.value = rows[0] ? store.value.mapTimelinePhoto(rows[0]) : stats.months?.[0]?.cover ? store.value.mapTimelinePhoto(stats.months[0].cover) : null
    if (id && timeAnchor.value) await changeGranularity(granularity.value, timeAnchor.value, true)
  }
}, { immediate: true })
watch(() => userStore.userInfo?.id, () => {
  ++timeIntent; timeAnchor.value = null; lastViewedId = ''; timeError.value = ''; anchorTop = undefined
})
watch(() => props.photos, (photos, previous) => {
  const anchor = timeAnchor.value
  if (!props.enableTimeBrowse || !anchor || !previous.some(item => item.id === anchor.id) || photos.some(item => item.id === anchor.id)) return
  timeAnchor.value = nearestTimelinePhoto(photos, anchor)
})
watch(layoutMode, mode => {
  if (props.enableTimeBrowse && ['diary', 'folder'].includes(mode)) store.value.browseGranularity = 'day'
})

// ---- Moments 朋友圈日文案 ----
// MVP 阶段只在 "全部照片" 视图启用（scope='all'）
const showMomentCaption = computed(() =>
  layoutMode.value === 'moments' && (!props.enableTimeBrowse || store.value.timeField === 'photo_time') && (store.value?.currentContext?.type === 'all')
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

const scrollToDate = (date: string, behavior: ScrollBehavior = 'smooth') => {
  if (props.enableTimeBrowse && granularity.value !== 'day') {
    const match = date.match(/(\d+)(?:年|-)(\d+)/)
    if (date === '时间未知') timeOverviewRef.value?.locate(0, 0)
    else if (match) timeOverviewRef.value?.locate(Number(match[1]), Number(match[2]))
    return
  }
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
.photo-view-settings { padding: 10px; }
.photo-view-section + .photo-view-section { margin-top: 16px; }
.photo-view-label { margin: 0 0 8px; padding-inline: 2px; font-size: 12px; font-weight: 500; color: var(--ts-color-text-secondary); }
.photo-choice-grid { display: grid; gap: 4px; padding: 4px; border-radius: 12px; background: var(--ts-color-surface-muted); }
.photo-choice { display: flex; align-items: center; justify-content: center; min-height: 40px; padding: 8px 4px; border-radius: 9px; font-size: 13px; font-weight: 500; color: var(--ts-color-text-secondary); transition: background-color 160ms ease, color 160ms ease; }
.photo-choice:hover { color: var(--ts-color-text); }
.photo-choice[aria-pressed="true"] { background: var(--ts-color-surface); color: var(--theme-primary); box-shadow: 0 1px 4px rgb(0 0 0 / 8%); }
.photo-size-choice { flex-direction: column; gap: 5px; min-height: 58px; font-size: 12px; }
.photo-layout-options { display: grid; gap: 2px; }
.photo-option-row { display: flex; align-items: center; justify-content: flex-start; gap: 10px; width: 100%; min-height: 44px; padding: 10px; border-radius: 10px; text-align: left; font-size: 14px; font-weight: 500; color: var(--ts-color-text-secondary); transition: background-color 160ms ease, color 160ms ease; }
.photo-option-row:hover { background: var(--ts-color-surface-muted); color: var(--ts-color-text); }
.photo-option-row[aria-pressed="true"] { background: rgba(var(--theme-rgb), .1); color: var(--theme-primary); }
.photo-view-actions { margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--ts-color-divider); }
.photo-choice:focus-visible, .photo-option-row:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 2px; }
@media (max-width: 767px) { .photo-choice { min-height: 44px; } }
@media (prefers-reduced-motion: reduce) { .photo-choice, .photo-option-row { transition: none; } }
</style>
