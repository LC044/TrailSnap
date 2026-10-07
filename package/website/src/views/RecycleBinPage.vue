<template>
  <div class="recycle-bin-page mx-auto w-full max-w-screen-2xl px-[var(--ts-page-gutter)] flex flex-col">
    <div class="sticky top-0 z-[45] -mx-[var(--ts-page-gutter)] px-[var(--ts-page-gutter)] pt-[var(--ts-content-safe-area-top)] mb-4">
      <div class="ts-browse-header flex items-center justify-between gap-2 py-1.5 sm:py-2">
        <div class="flex min-w-0 items-center gap-2">
          <BackButton label="返回" @click="goBack" />
          <div class="min-w-0">
            <h1 class="ts-page-title truncate text-gray-900 dark:text-white">最近删除</h1>
            <p class="truncate text-xs text-gray-500 dark:text-gray-400">{{ recycleSubtitle }}</p>
          </div>
        </div>
        <div v-if="!isSelectionMode" class="ts-liquid-glass ts-glass-toolbar flex shrink-0 items-center gap-1 sm:gap-2">
          <button type="button" class="ts-glass-button disabled:opacity-50 disabled:cursor-not-allowed" title="选择照片" aria-label="选择照片" :disabled="totalCount === 0 || isPurging" @click="handleEnterSelectionMode">
            <CheckSquare class="h-5 w-5" />
          </button>
          <button type="button" class="ts-glass-button disabled:opacity-50 disabled:cursor-not-allowed" title="清空回收站" aria-label="清空回收站" :disabled="totalCount === 0 || isPurging" @click="handleEmptyRecycleBin">
            <Trash2 class="h-5 w-5" />
          </button>
          <div class="relative">
            <button type="button" class="ts-glass-button" title="更多操作" aria-label="更多操作" :aria-expanded="showMoreMenu" @click="showMoreMenu = !showMoreMenu">
              <MoreHorizontal class="h-5 w-5" />
            </button>
            <AdaptiveMenu v-model="showMoreMenu" title="回收站操作" mobile-presentation="popover" close-on-action>
              <button type="button" class="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed" :disabled="totalCount === 0 || isPurging" @click="handleRestoreAll">
                <RefreshCcw class="h-4 w-4" /><span>全部恢复</span>
              </button>
              <button type="button" class="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 disabled:cursor-not-allowed" :disabled="totalCount === 0 || isPurging" @click="handleEmptyRecycleBin">
                <Trash2 class="h-4 w-4" /><span>清空回收站</span>
              </button>
            </AdaptiveMenu>
          </div>
        </div>
      </div>
      <div v-if="isSelectionMode" class="ts-liquid-glass mb-2 flex items-center justify-between gap-2 rounded-2xl px-2 py-1 md:hidden" data-testid="recycle-selection-header">
        <button type="button" class="ts-button ts-button-ghost" @click="toggleSelectAll">{{ isEverythingSelected ? '取消全选' : '全选' }}</button>
        <span class="text-sm font-semibold text-gray-900 dark:text-white" aria-live="polite">已选 {{ effectiveSelectedCount }} 项</span>
        <button type="button" class="ts-icon-button ts-button-ghost" aria-label="取消选择" @click="cancelSelection"><X class="h-5 w-5" /></button>
      </div>
    </div>

    <!-- Purge progress. A big purge runs as a background job on the server, so the
         page stays interactive and reports real progress instead of freezing on a
         request that would otherwise outlive the HTTP timeout. -->
    <Transition name="bar-slide">
      <div v-if="isPurging" class="mx-auto w-full pb-3">
        <div class="rounded-xl border border-gray-200 bg-white/90 px-4 py-3 shadow-sm dark:border-gray-700 dark:bg-gray-800/90">
          <div class="mb-2 flex items-center justify-between text-sm">
            <span class="flex items-center gap-2 font-medium text-gray-700 dark:text-gray-200">
              <Loader2 class="h-4 w-4 animate-spin text-primary-500" />
              正在清理回收站…
            </span>
            <span class="text-gray-500 dark:text-gray-400">{{ purgeProcessed }} / {{ purgeTotal }}</span>
          </div>
          <div class="h-1.5 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
            <div
              class="h-full rounded-full bg-primary-500 transition-[width] duration-300"
              :style="{ width: `${purgeProgress}%` }"
            ></div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- "Select all" spans the whole bin, not just the loaded pages. Say so explicitly
         so a destructive action is never ambiguous. -->
    <div v-if="isSelectionMode && selectAllAcrossPages && totalCount > photos.length" class="mx-auto w-full pb-2">
      <div class="rounded-lg bg-primary-50 px-3 py-2 text-xs text-primary-700 dark:bg-primary-900/30 dark:text-primary-300">
        已选中回收站中的全部 {{ totalCount }} 项（包含尚未加载的 {{ totalCount - photos.length }} 项）
      </div>
    </div>

    <!-- Gallery -->
    <div class="mx-auto w-full" :class="{ 'pb-28': isSelectionMode }">
      <!-- Empty State -->
      <div v-if="!loading && photos.length === 0" class="flex flex-col items-center justify-center py-20 text-gray-500 dark:text-gray-400">
        <div class="p-6 rounded-full bg-gray-100 dark:bg-gray-900 mb-4">
          <Trash2 class="w-12 h-12 opacity-20" />
        </div>
        <p class="text-lg font-medium">回收站为空</p>
      </div>

      <FlatPhotoGallery
        v-else
        ref="galleryRef"
        :photos="photos"
        :loading="loading && photos.length === 0"
        delete-label="永久删除"
        :pending-remove-ids="pendingRemoveIds"
        :show-action-bar="false"
        @click-photo="openLightbox"
        @batch-delete="handlePermanentDelete"
        @selection-change="handleSelectionChange"
      >
        <template #bottom-left-overlay="{ photo }">
           <div class="text-xs text-white drop-shadow-md flex items-center gap-1 px-1">
             <Disc class="w-3.5 h-3.5" />
             <span>{{ calculateDaysRemaining(photo) }}天</span>
           </div>
        </template>
      </FlatPhotoGallery>

      <!-- Explicit pagination control. Infinite scroll alone is fragile (nested
           scroll containers, short viewports), and it was the only way to reach
           the rest of the bin. -->
      <div v-if="photos.length > 0" class="flex flex-col items-center gap-2 py-6 text-sm text-gray-500 dark:text-gray-400">
        <button
          v-if="hasMore"
          type="button"
          :disabled="loading"
          class="rounded-full border border-gray-200 px-5 py-2 font-medium text-gray-700 transition-colors hover:bg-gray-100 disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
          @click="loadMore"
        >
          {{ loading ? '加载中…' : '加载更多' }}
        </button>
        <span>已加载 {{ photos.length }}{{ totalCount ? ` / ${totalCount}` : '' }} 项</span>
      </div>
    </div>

    <PhotoBatchActionBar
      :visible="isSelectionMode"
      :selected-ids="selectedIdSet"
      :selected-count="effectiveSelectedCount"
      :is-all-selected="isEverythingSelected"
      :is-downloading="false"
      :action-columns="2"
      :show-mobile-header="false"
      delete-label="永久删除"
      @cancel="cancelSelection"
      @select-all="toggleSelectAll"
    >
      <template #actions>
        <button type="button" class="ts-icon-button ts-button-ghost text-primary-600 disabled:opacity-50 disabled:cursor-not-allowed" :disabled="effectiveSelectedCount === 0 || isPurging" title="恢复照片" @click="handleRestoreSelection">
          <RefreshCcw class="h-5 w-5" /><span>恢复</span>
        </button>
        <button type="button" class="ts-icon-button ts-icon-danger text-red-500 disabled:opacity-50 disabled:cursor-not-allowed" :disabled="effectiveSelectedCount === 0 || isPurging" title="永久删除" @click="handleDeleteSelection">
          <Trash2 class="h-5 w-5" /><span>永久删除</span>
        </button>
      </template>
    </PhotoBatchActionBar>

    <!-- Lightbox -->
    <PhotoLightbox
      :visible="!!lightboxImage"
      :image="lightboxImage"
      :images="photos"
      :current-index="currentIndex"
      :has-prev="hasPrev"
      :has-next="hasNext"
      :allow-delete="true"
      :confirm-delete="false"
      @close="closeLightbox"
      @delete="handlePhotoDelete"
      @prev="handlePrev"
      @next="handleNext"
      @select="index => (lightboxImage = photos[index] ?? lightboxImage)"
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
  </div>
</template>

<script setup lang="ts">
import BackButton from '@/components/ui/BackButton.vue'
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useAppBack } from '@/composables/useAppBack'
import { ElMessage } from 'element-plus'
import { RefreshCcw, Trash2, CheckSquare, MoreHorizontal, Disc, Loader2, X } from 'lucide-vue-next'
import FlatPhotoGallery from '@/components/FlatPhotoGallery.vue'
import { usePhotoViewer } from '@/composables/usePhotoViewer'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import type { AlbumImage } from '@/types/album'
import request from '@/utils/request'
import { mapPhotoToImage } from '@/stores/photoStore'
import { useScroll } from '@vueuse/core'
import { useUiStore } from '@/stores/uiStore'
import AdaptiveMenu from '@/components/ui/AdaptiveMenu.vue'
import PhotoBatchActionBar from '@/components/PhotoBatchActionBar.vue'

const goBack = useAppBack('/')
const showMoreMenu = ref(false)
const loading = ref(false)
const photos = ref<AlbumImage[]>([])
const pendingRemoveIds = ref(new Set<string>())
const skip = ref(0)
// Larger page: the bin is a flat grid of thumbnails, and 100 meant a user had to
// scroll five times before "select all" could even reach 500 items.
const limit = 200
const hasMore = ref(true)
// Server-reported size of the whole bin, so "select all" and "empty bin" no longer
// depend on how much has been scrolled into the browser.
const totalCount = ref(0)
// Whether totalCount came from the authoritative stats endpoint. Without this the
// pagination fallback would overwrite a real total with the loaded-page length.
const hasStats = ref(false)

const galleryRef = ref<InstanceType<typeof FlatPhotoGallery> | null>(null)
const selectedIds = ref<string[]>([])
const selectedIdSet = computed(() => new Set(selectedIds.value))
const isSelectionMode = ref(false)
// True when the user asked for "everything in the bin" rather than "the ids
// currently on screen". Actions then target the server-side set, so the client
// never has to enumerate tens of thousands of ids.
const selectAllAcrossPages = ref(false)

// 同步到全局 UI 状态：移动端底部 Tab 栏 / Agent FAB 在选择模式激活时隐藏
const uiStore = useUiStore()
watch(isSelectionMode, (v) => uiStore.setSelectionActive(v))

const allLoadedSelected = computed(() => {
  return photos.value.length > 0 && selectedIds.value.length === photos.value.length
})

// "Everything" means the whole bin when we know its size, otherwise every loaded item.
const isEverythingSelected = computed(() => {
  if (selectAllAcrossPages.value) return true
  return allLoadedSelected.value && !hasMore.value
})

const effectiveSelectedCount = computed(() => {
  if (selectAllAcrossPages.value) return Math.max(totalCount.value, selectedIds.value.length)
  return selectedIds.value.length
})

const recycleSubtitle = computed(() => {
  const retention = `已删除的内容仅保留${retentionDays.value}天`
  return totalCount.value > 0 ? `${retention} · 共 ${totalCount.value} 项` : retention
})

const handleEnterSelectionMode = () => {
  isSelectionMode.value = true
  galleryRef.value?.enterSelectionMode()
}

const toggleSelectAll = () => {
  const loadedIds = photos.value.map(p => p.id)

  if (isEverythingSelected.value) {
    // Clear the whole-bin intent first so the resulting selection-change event
    // does not immediately re-derive it.
    selectAllAcrossPages.value = false
    // useSelection.selectAll() toggles: passing an already fully selected list
    // deselects it, which keeps us in selection mode.
    if (loadedIds.length > 0) galleryRef.value?.selectAll(loadedIds)
    return
  }

  // Tick every loaded thumbnail for immediate feedback, and flag the whole-bin
  // intent so pages that were never scrolled into view are covered too.
  const unselected = loadedIds.filter(id => !selectedIds.value.includes(id))
  if (unselected.length > 0) galleryRef.value?.selectAll(unselected)
  selectAllAcrossPages.value = totalCount.value > 0 || hasMore.value

  if (!isSelectionMode.value) {
    galleryRef.value?.enterSelectionMode()
    isSelectionMode.value = true
  }
}

const handleSelectionChange = (ids: string[]) => {
  // Unticking a single item must cancel the whole-bin intent, otherwise the
  // action bar would still delete items the user just excluded.
  if (selectAllAcrossPages.value && ids.length < photos.value.length) {
    selectAllAcrossPages.value = false
  }
  selectedIds.value = ids
  if (ids.length > 0) {
    isSelectionMode.value = true
  } else if (isSelectionMode.value && galleryRef.value && !galleryRef.value.isSelectionMode) {
    isSelectionMode.value = false
  }
}

const cancelSelection = () => {
  isSelectionMode.value = false
  selectAllAcrossPages.value = false
  galleryRef.value?.exitSelectionMode()
}

// Config
const retentionDays = ref(7)

const fetchConfig = async () => {
    try {
        const { data } = await request.get('/api/system/config')
        if (data && data.recycle_bin && data.recycle_bin.retention_days) {
            retentionDays.value = data.recycle_bin.retention_days
        }
    } catch (e) {
        console.error('Failed to load system config', e)
    }
}

// Calculate days remaining
const calculateDaysRemaining = (photo: AlbumImage) => {
    if (photo.deleted_at) {
        // Assume deleted_at might be in UTC string format, like "2023-10-25T10:00:00"
        // Ensure timezone correctness if backend doesn't return Z
        const deletedAt = new Date(photo.deleted_at + (photo.deleted_at.includes('Z') ? '' : 'Z')).getTime()
        const now = Date.now()
        // Calculate full 24 hour periods passed
        const daysPassed = Math.floor((now - deletedAt) / (1000 * 60 * 60 * 24))
        return Math.max(0, retentionDays.value - daysPassed)
    }
    return retentionDays.value // Fallback
}

// Lightbox state
const { currentPhoto: lightboxImage, currentIndex, hasPrev, hasNext, open: openLightbox, close: closeLightbox, prev: handlePrev, next: handleNext } = usePhotoViewer(photos, { onNextAtEnd: () => { if (hasMore.value) loadMore() } })

const handlePhotoDelete = (photoId: string) => {
  showDeleteConfirm.value = true
  confirmMessage.value = '确定要永久删除这张照片吗？该操作不可恢复！'
  pendingDeleteIds.value = [photoId]
  pendingDeleteAll.value = false
}

// Delete Confirm state
const showDeleteConfirm = ref(false)
const confirmMessage = ref('')
const pendingDeleteIds = ref<string[]>([])
// `null` photo_ids tells the server "purge my whole bin", which is what makes
// emptying the bin possible without listing every id in the browser first.
const pendingDeleteAll = ref(false)
let deleteCallback: ((success: boolean) => void) | null = null

// Purge progress (async server job)
const isPurging = ref(false)
const purgeTotal = ref(0)
const purgeProcessed = ref(0)
const purgeProgress = computed(() => {
  if (purgeTotal.value === 0) return 0
  return Math.min(100, Math.round((purgeProcessed.value / purgeTotal.value) * 100))
})
let pollTimer: ReturnType<typeof setTimeout> | null = null

const stopPolling = () => {
  if (pollTimer !== null) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

const handlePermanentDelete = (ids: string[], callback?: (success: boolean) => void) => {
  showDeleteConfirm.value = true
  confirmMessage.value = `确定要永久删除这 ${ids.length} 张照片吗？该操作不可恢复！`
  pendingDeleteIds.value = ids
  pendingDeleteAll.value = false
  deleteCallback = callback || null
}

const handleDeleteSelection = () => {
  if (selectAllAcrossPages.value) {
    showDeleteConfirm.value = true
    confirmMessage.value = `确定要永久删除回收站中的全部 ${effectiveSelectedCount.value} 张照片吗？该操作不可恢复！`
    pendingDeleteIds.value = []
    pendingDeleteAll.value = true
    deleteCallback = null
    return
  }
  handlePermanentDelete(selectedIds.value)
}

const handleEmptyRecycleBin = () => {
  if (totalCount.value === 0) {
    ElMessage.info('回收站已经是空的')
    return
  }
  showDeleteConfirm.value = true
  confirmMessage.value = `确定要清空回收站吗？将永久删除 ${totalCount.value} 张照片，该操作不可恢复！`
  pendingDeleteIds.value = []
  pendingDeleteAll.value = true
  deleteCallback = null
}

/** Poll a background purge job until it finishes, keeping the progress bar live. */
const pollPurgeJob = (jobId: string) => {
  stopPolling()
  pollTimer = setTimeout(async () => {
    try {
      const { data } = await request.get(`/api/photos/recycle-bin/purge/${jobId}`)
      purgeProcessed.value = data?.processed ?? purgeProcessed.value
      purgeTotal.value = data?.total ?? purgeTotal.value

      if (data?.status === 'completed') {
        finishPurge(`成功永久删除 ${data.deleted ?? purgeTotal.value} 张照片`)
        return
      }
      if (data?.status === 'failed') {
        finishPurge(null)
        ElMessage.error(`清理失败：${data.error || '未知错误'}`)
        return
      }
      pollPurgeJob(jobId)
    } catch (error) {
      console.error(error)
      // The job itself may still be running server-side; stop polling and let a
      // manual refresh reflect reality rather than spinning forever.
      finishPurge(null)
    }
  }, 1000)
}

const finishPurge = (successMessage: string | null) => {
  stopPolling()
  isPurging.value = false
  purgeProcessed.value = 0
  purgeTotal.value = 0
  if (successMessage) ElMessage.success(successMessage)
  cancelSelection()
  refresh()
}

const confirmDelete = async () => {
  const deleteAll = pendingDeleteAll.value
  const ids = pendingDeleteIds.value
  if (!deleteAll && ids.length === 0) return

  showDeleteConfirm.value = false

  try {
    const { data } = await request.post('/api/photos/recycle-bin/purge', {
      photo_ids: deleteAll ? null : ids,
    })

    if (data?.mode === 'async' && data?.job_id) {
      // Big batch: the server is working in the background. Show progress
      // instead of blocking the UI on a request that would likely time out.
      isPurging.value = true
      purgeTotal.value = data.total ?? ids.length
      purgeProcessed.value = data.processed ?? 0
      ElMessage.info(`正在后台清理 ${purgeTotal.value} 张照片，可继续浏览`)
      pollPurgeJob(data.job_id)
      if (deleteCallback) {
        deleteCallback(true)
        deleteCallback = null
      }
      return
    }

    const deleted = data?.deleted ?? ids.length
    ElMessage.success(`成功永久删除 ${deleted} 张照片`)

    if (deleteAll) {
      photos.value = []
      totalCount.value = 0
      hasMore.value = false
      closeLightbox()
    } else {
      photos.value = photos.value.filter(p => !ids.includes(p.id))
      totalCount.value = Math.max(0, totalCount.value - deleted)
      if (lightboxImage.value && ids.includes(lightboxImage.value.id)) {
        closeLightbox()
      }
    }

    if (deleteCallback) {
      deleteCallback(true)
      deleteCallback = null
    }
    cancelSelection()
  } catch (error) {
    console.error(error)
    ElMessage.error('永久删除失败')
    if (deleteCallback) {
      deleteCallback(false)
      deleteCallback = null
    }
  } finally {
    pendingDeleteIds.value = []
    pendingDeleteAll.value = false
  }
}

/** Load the bin size so "select all" / "empty bin" can act on the whole set. */
const fetchStats = async () => {
  try {
    const { data } = await request.get('/api/photos/recycle-bin/stats')
    // Guard the shape: this path is easy to shadow with a broad `/recycle-bin*`
    // mock or an older server, and a bad value must not break the page.
    if (data && typeof data.total === 'number') {
      totalCount.value = data.total
      hasStats.value = true
    }
    if (data && typeof data.retention_days === 'number' && data.retention_days > 0) {
      retentionDays.value = data.retention_days
    }
  } catch (e) {
    console.error('Failed to load recycle bin stats', e)
  }
}

const fetchPhotos = async (isLoadMore = false) => {
  if (loading.value) return
  if (!isLoadMore) {
    skip.value = 0
    hasMore.value = true
  }
  if (!hasMore.value) return

  loading.value = true
  try {
    const { data } = await request.get('/api/photos/recycle-bin', {
      params: { skip: skip.value, limit }
    })
    
    if (data.length < limit) {
      hasMore.value = false
    }

    const mappedPhotos = data.map(mapPhotoToImage)
    
    if (isLoadMore) {
      photos.value = [...photos.value, ...mappedPhotos]
    } else {
      photos.value = mappedPhotos
    }
    skip.value += data.length

    // Keep a whole-bin selection consistent as new pages arrive, so the
    // checkmarks match what the pending action will actually delete.
    if (selectAllAcrossPages.value && mappedPhotos.length > 0) {
      const newIds = mappedPhotos
        .map((p: AlbumImage) => p.id)
        .filter((id: string) => !selectedIds.value.includes(id))
      if (newIds.length > 0) galleryRef.value?.selectAll(newIds)
    }

    // The stats endpoint is authoritative for the bin size. Only fall back to
    // the loaded length when it is unavailable (older server / failed request),
    // otherwise a short first page would clobber the real total.
    if (!hasStats.value) {
      if (!hasMore.value) {
        totalCount.value = photos.value.length
      } else if (photos.value.length > totalCount.value) {
        totalCount.value = photos.value.length
      }
    }
  } catch (error) {
    console.error(error)
    ElMessage.error('加载回收站照片失败')
  } finally {
    loading.value = false
  }
}

const loadMore = () => {
  fetchPhotos(true)
}

const refresh = async () => {
  await Promise.all([fetchStats(), fetchPhotos(false)])
}

const handleRestore = async (ids: string[]) => {
  if (ids.length === 0) return
  try {
    await request.post('/api/photos/recycle-bin/restore', { photo_ids: ids })
    ElMessage.success(`成功恢复 ${ids.length} 张照片`)
    photos.value = photos.value.filter(p => !ids.includes(p.id))
    totalCount.value = Math.max(0, totalCount.value - ids.length)
    cancelSelection()
  } catch (error) {
    console.error(error)
    ElMessage.error('恢复失败')
  }
}

/** Restore the entire bin server-side — no id enumeration in the browser. */
const handleRestoreAll = async () => {
  if (totalCount.value === 0) {
    ElMessage.info('回收站已经是空的')
    return
  }
  try {
    const { data } = await request.post('/api/photos/recycle-bin/restore-all')
    ElMessage.success(`成功恢复 ${data?.restored ?? totalCount.value} 张照片`)
    cancelSelection()
    await refresh()
  } catch (error) {
    console.error(error)
    ElMessage.error('恢复失败')
  }
}

const handleRestoreSelection = () => {
  if (selectAllAcrossPages.value) {
    handleRestoreAll()
    return
  }
  handleRestore(selectedIds.value)
}

const scrollContainer = ref<HTMLElement | Window>(window)
const { y: windowScrollY } = useScroll(scrollContainer)

onMounted(async () => {
  await fetchConfig()
  fetchStats()
  fetchPhotos()
  
  const mainEl = document.querySelector('main')
  if (mainEl && window.getComputedStyle(mainEl).overflowY === 'auto') {
    scrollContainer.value = mainEl
  }
})

onUnmounted(() => {
  stopPolling()
  uiStore.setSelectionActive(false)
})

watch(windowScrollY, (y) => {
    if (!hasMore.value || loading.value) return
    
    let scrollHeight = 0
    let clientHeight = 0
    if (scrollContainer.value === window) {
      scrollHeight = document.documentElement.scrollHeight
      clientHeight = window.innerHeight
    } else {
      scrollHeight = (scrollContainer.value as HTMLElement).scrollHeight
      clientHeight = (scrollContainer.value as HTMLElement).clientHeight
    }
    
    const bottom = scrollHeight - clientHeight - y
    if (bottom < 500) {
        loadMore()
    }
})

</script>

<style scoped>
/* Floating action bar slides up from the bottom when selection is active. */
.bar-slide-enter-active,
.bar-slide-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.bar-slide-enter-from,
.bar-slide-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
</style>
