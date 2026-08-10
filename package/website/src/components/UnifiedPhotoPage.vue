<template>
  <div class="unified-photo-page container mx-auto py-1 px-4 min-h-screen">
    <!-- Toolbar & Header（文件夹视图有自己的工具栏，这里整条隐藏以节省移动端空间） -->
    <div v-if="layoutMode !== 'folder'" class="sticky md:top-0 z-30 pointer-events-none">
      <div class="flex md:flex-row items-center justify-between gap-4 mx-auto px-4 py-3 pointer-events-auto">
        <!-- Back & Title -->
        <slot name="header-left">
          <div v-if="showBack || title || $slots['title-extra']" class="flex items-center gap-3 w-full max-w-full md:w-auto bg-white/80 dark:bg-gray-900/80 backdrop-blur-md px-3 py-1.5 rounded-full shadow-sm border border-gray-200/50 dark:border-gray-700/50">
            <button v-if="showBack" @click="$emit('back')" class="p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors bg-white dark:bg-gray-900">
              <ArrowLeft class="w-5 h-5 text-gray-600 dark:text-gray-300" />
            </button>
            <div class="pr-2 min-w-0" v-if="!loadingTitle">
              <h1 class="max-w-[140px] md:max-w-[300px] text-sm md:text-lg font-bold text-gray-900 dark:text-white leading-tight flex items-center gap-2 truncate">
                <span class="truncate">{{ title }}</span>
                <slot name="title-extra"></slot>
              </h1>
              <p class="text-xs text-gray-500 truncate">{{ subtitle }}</p>
            </div>
            <div v-else class="pr-2 animate-pulse">
              <div class="h-6 w-32 bg-gray-200 dark:bg-gray-800 rounded"></div>
            </div>
          </div>
        </slot>

        <!-- Controls -->
        <div class="flex items-center gap-2 ml-auto animate-in fade-in slide-in-from-right-4 duration-300">
          
          <slot name="header-controls-start"></slot>

          <!-- View Options Menu -->
          <div class="relative">
             <button
               @click="showViewOptions = !showViewOptions"
               class="p-2 text-gray-700 dark:text-gray-200 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md hover:bg-white dark:hover:bg-gray-900 rounded-full shadow-sm border border-gray-200/50 dark:border-gray-700/50 transition-all"
               title="视图设置"
             >
               <Settings2 class="w-5 h-5" />
             </button>

             <!-- Secondary Menu Dropdown -->
            <Transition
              enter-active-class="transition duration-200 ease-out"
              enter-from-class="transform scale-95 opacity-0"
              enter-to-class="transform scale-100 opacity-100"
              leave-active-class="transition duration-75 ease-in"
              leave-from-class="transform scale-100 opacity-100"
              leave-to-class="transform scale-95 opacity-0"
            >
              <div v-if="showViewOptions" 
                   ref="viewOptionsRef"
                   class="absolute right-0 top-full mt-2 w-48 bg-white dark:bg-gray-900 rounded-xl shadow-xl border border-gray-100 dark:border-gray-800 p-2 z-50 origin-top-right"
              >
                <div class="space-y-3 p-1">
                  <!-- View Size -->
                  <div class="space-y-2">
                    <p class="text-xs font-medium text-gray-500 px-1">图片大小</p>
                    <div class="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
                      <button v-for="size in ['sm', 'md', 'lg']" :key="size"
                        @click="viewSize = size as any"
                        class="flex-1 p-1.5 rounded text-center transition-colors dark:bg-gray-800"
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
                    <p class="text-xs font-medium text-gray-500 px-1">布局模式</p>
                    <div class="grid grid-cols-1 gap-1">
                       <button
                        @click="layoutMode = 'waterfall'"
                        class="flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm"
                        :class="layoutMode === 'waterfall' ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400 font-medium' : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'"
                      >
                        <LayoutDashboard class="w-4 h-4" />
                        <span>自适应</span>
                      </button>
                      <button
                        @click="layoutMode = 'grid'"
                        class="flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm"
                        :class="layoutMode === 'grid' ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400 font-medium' : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'"
                      >
                        <LayoutGrid class="w-4 h-4" />
                        <span>正方形</span>
                      </button>
                      <button
                        @click="layoutMode = 'moments'"
                        class="flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm"
                        :class="layoutMode === 'moments' ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400 font-medium' : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'"
                      >
                        <LayoutList class="w-4 h-4" />
                        <span>朋友圈</span>
                      </button>
                      <button
                        v-if="allowFolderView"
                        @click="layoutMode = 'folder'"
                        class="flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm"
                        :class="layoutMode === 'folder' ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400 font-medium' : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'"
                      >
                        <FolderTree class="w-4 h-4" />
                        <span>文件夹</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </Transition>
           </div>

          <!-- Batch Select -->
          <button 
            @click="enterBatchMode"
            class="p-2 text-gray-700 dark:text-gray-200 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md hover:bg-white dark:hover:bg-gray-900 rounded-full shadow-sm border border-gray-200/50 dark:border-gray-700/50 transition-all"
            title="批量选择"
          >
            <CheckSquare class="w-5 h-5" />
          </button>

          <!-- Header Actions Slot -->
          <slot name="header-actions"></slot>

          <!-- Upload Button -->
          <template v-if="allowUpload">
            <button 
              @click="$emit('upload')"
              class="bg-primary-500 hover:bg-primary-600 text-white p-2 sm:px-4 sm:py-2 rounded-full shadow-lg shadow-primary-500/30 flex items-center gap-2 text-sm font-medium transition-all active:scale-95"
            >
              <UploadCloud class="w-5 h-5" />
              <span class="hidden sm:inline">上传</span>
            </button>
          </template>

        </div>
      </div>

      <!-- Header Extension Slot (e.g. Filter Panel) -->
      <slot name="header-extension"></slot>
    </div>

    <!-- Timeline Navigation Sidebar (Right Sticky) — 文件夹视图有自己的目录树，隐藏时间轴 -->
    <AlbumTimeline
      v-if="layoutMode !== 'folder'"
      :items="timelineItems"
      :active-date="activeDate"
      @select="scrollToDate"
    />

    <!-- Main Content Area -->
    <div class="mx-auto sm:px-6 lg:px-8">
      <slot name="intro"></slot>

      <!-- 文件夹视图（作为一种布局模式，与自适应/正方形/朋友圈并列） -->
      <FolderBrowser
        v-if="layoutMode === 'folder'"
        v-model:view-size="viewSize"
        @switch-layout="(m) => layoutMode = m as any"
      />

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
    </div>

    <!-- Lightbox -->
    <PhotoLightbox
      :visible="!!lightboxImage"
      :image="lightboxImage"
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
import { ref, computed, onUnmounted, watch } from 'vue'
import { onClickOutside } from '@vueuse/core'
import {
  ArrowLeft, Grid3x3, Grid2x2, Maximize, LayoutDashboard, LayoutGrid, LayoutList,
  UploadCloud, CheckSquare, Settings2, FolderTree
} from 'lucide-vue-next'
import { ElMessageBox, ElMessage, ElNotification } from 'element-plus'

import PhotoGallery from '@/components/PhotoGallery.vue'
import FolderBrowser from '@/views/album/folder/FolderBrowser.vue'
import AlbumTimeline from '@/components/AlbumTimeline.vue'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import ParticleExplosion from '@/components/ParticleExplosion.vue'
import AlbumSelector from '@/components/AlbumSelector.vue'
import FolderSelectionDialog from '@/components/FolderSelectionDialog.vue'
import LocationBatchEditor from '@/components/LocationBatchEditor.vue'
import type { AlbumImage } from '@/types/album'

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
  allowFolderView: false
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
}>()

// UI State
const viewSize = ref<'sm' | 'md' | 'lg'>('md')
const layoutMode = ref<'masonry' | 'grid' | 'list' | 'waterfall' | 'moments' | 'folder'>('grid')
const activeDate = ref('')
const lightboxImage = ref<AlbumImage | null>(null)
const showViewOptions = ref(false)
const viewOptionsRef = ref<HTMLElement | null>(null)
const galleryRef = ref<InstanceType<typeof PhotoGallery> | null>(null)
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 768)

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
  showViewOptions.value = false
})

const scrollToDate = (date: string) => {
  galleryRef.value?.scrollToDate(date)
  activeDate.value = date
}

const enterBatchMode = () => {
  galleryRef.value?.enterSelectionMode()
}

const closeAlbumSelectModal = () => {
  showAlbumSelectModal.value = false
  tempSelectedIds.value = []
  galleryRef.value?.exitSelectionMode()
}

// Lightbox
const lightboxIndex = computed(() => {
  if (!lightboxImage.value) return -1
  return props.photos.findIndex(img => img.id === lightboxImage.value?.id)
})

const hasPrev = computed(() => lightboxIndex.value > 0)
const hasNext = computed(() => lightboxIndex.value < props.photos.length - 1 && lightboxIndex.value !== -1)

const openLightbox = (img: AlbumImage) => {
  lightboxImage.value = img
}

const closeLightbox = () => {
  lightboxImage.value = null
}

const handlePrev = () => {
  if (hasPrev.value) {
    lightboxImage.value = props.photos[lightboxIndex.value - 1]
  }
}

const handleNext = () => {
  if (hasNext.value) {
    lightboxImage.value = props.photos[lightboxIndex.value + 1]
  }
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
    emit('confirm-delete', idsToDelete.value, (success: boolean) => {
        if (success) {
            // Show particle if needed (usually for permanent delete)
            if (props.deleteLabel === '删除') {
                showParticle.value = true
            }
            galleryRef.value?.exitSelectionMode()
            if (lightboxDeleteId.value) closeLightbox()
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
    pendingRemoveIds
})
</script>

<style scoped>
/* Scoped styles if necessary */
</style>
