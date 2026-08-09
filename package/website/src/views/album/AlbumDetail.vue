<template>
  <UnifiedPhotoPage
    :title="album?.title || '相册详情'"
    :subtitle="`${album?.count || 0} 个项目`"
    :loading="photoStore.loading"
    :photos="images"
    :timeline-stats="photoStore.timelineStats"
    :timeline-items="timelineItems"
    :allow-upload="isUserAlbum"
    :delete-label="isUserAlbum ? '从相册中移除' : '删除'"
    :pending-remove-ids="pendingRemoveIds"
    :has-more="photoStore.hasMore"
    @back="goBack"
    @upload="triggerUpload"
    @load-more="loadMorePhotos"
    @retry="photoStore.loadAlbumPhotos(albumId, true)"
    @confirm-delete="handleConfirmDelete"
    @remove-from-album="handleBatchRemoveFromAlbum"
    @photo-update="handlePhotoUpdate"
    @set-cover="setCover"
  >
    <template #header-actions>
      <button 
        v-if="album?.type === 'custom' || album?.type === 'user'"
        @click="showPhotoSelector = true"
        class="flex items-center gap-2 p-2 sm:px-4 sm:py-2 text-primary-500 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-full transition-colors font-medium text-sm"
        title="添加照片"
      >
        <ImagePlus class="w-5 h-5" />
        <span class="hidden sm:inline">添加照片</span>
      </button>
    </template>
    <template #extra-modals>
      <!-- Photo Selector Modal -->
      <Transition name="slide-up">
        <div v-if="showPhotoSelector" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm md:p-4" @click.self="showPhotoSelector = false">
          <div class="bg-white dark:bg-gray-900 md:rounded-2xl shadow-2xl w-full h-full md:max-w-7xl md:h-[90vh] overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
            <PhotoSelector 
              :is-selector="true" 
              :store="selectionStore"
              :title="`添加到 ${album?.title}`"
              @select="handleAddPhotosToAlbum"
              @cancel="showPhotoSelector = false"
            />
          </div>
        </div>
      </Transition>

      <!-- Upload Progress Toast -->
      <Transition name="slide-up">
        <div v-if="showUploadModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div class="bg-white dark:bg-gray-900 rounded-xl shadow-xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh] animate-in zoom-in-95 duration-200">
            <div class="p-4 border-b border-gray-100 dark:border-gray-800 flex justify-between items-center">
              <h3 class="font-bold text-lg text-gray-900 dark:text-white">上传照片</h3>
              <button @click="showUploadModal = false" class="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full"><X class="w-5 h-5" /></button>
            </div>
            <div class="p-6 overflow-y-auto">
              <MultiFileUpload :albumId="albumId" @upload-complete="handleUploadComplete" />
            </div>
          </div>
        </div>
      </Transition>
    </template>
  </UnifiedPhotoPage>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppBack } from '@/composables/useAppBack'
import { useOverlayStack } from '@/composables/useOverlayStack'
import { useAlbumStore } from '@/stores/albumStore'
import { usePhotoStore } from '@/stores/photoStore'
import { useSelectionStore } from '@/stores/selectionStore'
import { albumService } from '@/api/album'
import { X, Folder, Loader2, Check, ImagePlus } from 'lucide-vue-next'
import UnifiedPhotoPage from '@/components/UnifiedPhotoPage.vue'
import MultiFileUpload from '@/components/MultiFileUpload.vue'
import PhotoSelector from '@/components/PhotoSelector.vue'
import { format } from 'date-fns'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const goBack = useAppBack('/album')
const albumStore = useAlbumStore()
const photoStore = usePhotoStore()
const selectionStore = useSelectionStore()
const albumId = route.params.id as string

// State
const album = computed(() => albumStore.getAlbumDetails(albumId))
const images = computed(() => photoStore.images)
// 当前后端创建的普通相册类型为 user；兼容已有的 legacy custom 数据。
const isUserAlbum = computed(() => album.value?.type === 'user' || album.value?.type === 'custom')

// UI State
const showUploadModal = ref(false)
const showPhotoSelector = ref(false)
useOverlayStack(showUploadModal, () => { showUploadModal.value = false })
useOverlayStack(showPhotoSelector, () => { showPhotoSelector.value = false })
const pendingRemoveIds = ref(new Set<string>())

// Used by UnifiedPhotoPage for sidebar
const timelineItems = computed(() => photoStore.timelineStats?.timeline || [])

// Actions
const triggerUpload = () => {
    showUploadModal.value = true
}

const handleUploadComplete = () => {
    showUploadModal.value = false
    photoStore.loadAlbumPhotos(albumId, true)
}

const handleAddPhotosToAlbum = async (ids: string[]) => {
    if (ids.length === 0) return
    try {
        await albumStore.addPhotosToAlbum(ids, 'add_to_album', albumId)
        ElMessage.success(`成功添加 ${ids.length} 张照片`)
        showPhotoSelector.value = false
        photoStore.resetAll()
        albumStore.fetchAlbums()
        photoStore.loadAlbumPhotos(albumId, true)
    } catch (e) {
        console.error(e)
        ElMessage.error('添加失败')
    }
}

const loadMorePhotos = () => {
    photoStore.loadAlbumPhotos(albumId)
}

const handlePhotoUpdate = (event: { id: string, location?: string, tags?: string[] }) => {
    const img = photoStore.images.find(i => i.id === event.id)
}

const setCover = async (ids: string[]) => {
  try {
    await albumService.setAlbumCover(albumId, ids[0])
    ElMessage.success('封面已更新')
  } catch (e) {
    ElMessage.error('封面更新失败')
  }
}

const handleConfirmDelete = async (ids: string[], callback: (success: boolean) => void) => {
    try {
        if (isUserAlbum.value) {
            await albumStore.removePhotosFromAlbum(albumId, ids)
        } else {
            await photoStore.deletePhotos(ids)
        }
        photoStore.loadAlbumPhotos(albumId, true)
        callback(true)
    } catch (e) {
        console.error(e)
        ElMessage.error('操作失败')
        callback(false)
    }
}

const handleBatchRemoveFromAlbum = async (ids: string[]) => {
    if (ids.length === 0) return
    if (album.value?.type !== 'user') {
        ElMessage.warning('仅普通相册支持批量移出')
        return
    }
    // Optimistic UI: Mark as pending remove (shrink animation)
    ids.forEach(id => pendingRemoveIds.value.add(id))

    // Timeout Promise (3s)
    const timeout = new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Timeout')), 3000)
    )

    try {
        await Promise.race([
            albumStore.removePhotosFromAlbum(albumId, ids),
            timeout
        ])

        photoStore.loadAlbumPhotos(albumId, true)
        ElMessage.success('已移出相册')

        // Clear pending IDs after successful removal and reload
        // We delay slightly to ensure the list update has processed
        setTimeout(() => {
             ids.forEach(id => pendingRemoveIds.value.delete(id))
        }, 500)
    } catch (e: any) {
        if (e.message === 'Timeout') {
            ElMessage.warning('操作超时，标记为待删除')
            // Keep in pendingRemoveIds to maintain visual state
        } else {
            ElMessage.error('移出失败')
            // Revert optimistic update on error
            ids.forEach(id => pendingRemoveIds.value.delete(id))
        }
    }
}

onMounted(() => {
    photoStore.resetAll()
    albumStore.fetchAlbums()
    photoStore.loadAlbumPhotos(albumId, true)
})

onUnmounted(() => {
    photoStore.resetAll()
})

</script>
