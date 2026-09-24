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
    :update-available="photoStore.dataStale"
    update-message="相册内容已更新，点击刷新"
    @back="goBack"
    @upload="triggerUpload"
    @load-more="loadMorePhotos"
    @retry="photoStore.loadAlbumPhotos(albumId, true)"
    @confirm-delete="handleConfirmDelete"
    @remove-from-album="handleBatchRemoveFromAlbum"
    @photo-update="handlePhotoUpdate"
    @set-cover="setCover"
    @refresh-data="refreshAlbumData"
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
      <el-dropdown
        v-if="album && album.type !== 'system'"
        trigger="click"
        @command="handleMenuCommand"
      >
        <button
          type="button"
          class="flex items-center justify-center rounded-full bg-white/80 p-2 text-gray-700 shadow-sm backdrop-blur-md transition-all hover:bg-white border border-gray-200/50 dark:border-gray-700/50 dark:bg-gray-900/80 dark:text-gray-200 dark:hover:bg-gray-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
          title="更多操作"
          aria-label="更多操作"
        >
          <MoreVertical class="w-5 h-5" />
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="edit">
              <Edit2 class="mr-2 inline h-4 w-4" />
              <span>编辑相册</span>
            </el-dropdown-item>
            <el-dropdown-item command="cover">
              <ImageIcon class="mr-2 inline h-4 w-4" />
              <span>更换封面</span>
            </el-dropdown-item>
            <el-dropdown-item command="delete" divided>
              <Trash2 class="mr-2 inline h-4 w-4 text-red-500" />
              <span class="text-red-500">删除相册</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
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

      <!-- Edit Album Modal (简化版:仅支持 name + description,适用于 user/custom 相册) -->
      <el-dialog
        v-model="showEditModal"
        title="编辑相册"
        :width="editDialogWidth"
        class="rounded-xl"
        destroy-on-close
      >
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">相册名称</label>
            <input
              v-model="editForm.name"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 outline-none transition-all"
              placeholder="请输入相册名称"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">描述 (可选)</label>
            <textarea
              v-model="editForm.description"
              rows="3"
              class="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 outline-none transition-all resize-none"
              placeholder="相册描述..."
            ></textarea>
          </div>
        </div>
        <template #footer>
          <div class="flex justify-end gap-3">
            <button
              @click="showEditModal = false"
              class="px-4 py-2 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
            >
              取消
            </button>
            <button
              @click="submitEdit"
              class="px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg shadow-lg shadow-primary-500/20 transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="!editForm.name.trim() || editLoading"
            >
              {{ editLoading ? '保存中...' : '保存' }}
            </button>
          </div>
        </template>
      </el-dialog>

      <!-- 更换封面:复用 PhotoSelector 的 is-selector 模式,只显示当前相册内照片 -->
      <Transition name="slide-up">
        <div
          v-if="showCoverSelector"
          class="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm md:p-4"
          @click.self="showCoverSelector = false"
        >
          <div class="bg-white dark:bg-gray-900 md:rounded-2xl shadow-2xl w-full h-full md:max-w-7xl md:h-[90vh] overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
            <PhotoSelector
              :is-selector="true"
              :store="selectionStore"
              :title="`选择 ${album?.title || ''} 的封面`"
              @select="handleCoverSelected"
              @cancel="showCoverSelector = false"
            />
          </div>
        </div>
      </Transition>
    </template>
  </UnifiedPhotoPage>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppBack } from '@/composables/useAppBack'
import { useOverlayStack } from '@/composables/useOverlayStack'
import { useWindowSize } from '@vueuse/core'
import { useAlbumStore } from '@/stores/albumStore'
import { usePhotoStore } from '@/stores/photoStore'
import { useSelectionStore } from '@/stores/selectionStore'
import { albumService } from '@/api/album'
import { X, Folder, Loader2, Check, ImagePlus, MoreVertical, Edit2, Trash2, Image as ImageIcon } from 'lucide-vue-next'
import UnifiedPhotoPage from '@/components/UnifiedPhotoPage.vue'
import MultiFileUpload from '@/components/MultiFileUpload.vue'
import PhotoSelector from '@/components/PhotoSelector.vue'
import { format } from 'date-fns'
import { ElMessage, ElMessageBox } from 'element-plus'

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

// 编辑相册(简化弹窗:仅 name + description)
const showEditModal = ref(false)
const editLoading = ref(false)
const editForm = reactive({ name: '', description: '' })
useOverlayStack(showEditModal, () => { showEditModal.value = false })

// 更换封面
const showCoverSelector = ref(false)
useOverlayStack(showCoverSelector, () => { showCoverSelector.value = false })

const { width } = useWindowSize()
const editDialogWidth = computed(() => width.value < 640 ? 'calc(100% - 24px)' : '480px')

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

const refreshAlbumData = async (done: () => void = () => {}) => {
    try {
        await Promise.all([
            albumStore.fetchAlbums(),
            photoStore.refreshCurrentContext(),
        ])
    } finally {
        done()
    }
}

const setCover = async (ids: string[]) => {
  try {
    await albumService.setAlbumCover(albumId, ids[0])
    ElMessage.success('封面已更新')
  } catch (e) {
    ElMessage.error('封面更新失败')
  }
}

// 菜单命令:edit / cover / delete
const openEditModal = () => {
  if (!album.value) return
  editForm.name = album.value.title || album.value.name || ''
  editForm.description = album.value.description || ''
  showEditModal.value = true
}

const submitEdit = async () => {
  if (!album.value || !editForm.name.trim()) return
  editLoading.value = true
  try {
    await albumStore.updateAlbum(albumId, {
      name: editForm.name.trim(),
      description: editForm.description,
      type: album.value.type,
    })
    await albumStore.fetchAlbums()
    showEditModal.value = false
    ElMessage.success('相册已更新')
  } catch (e) {
    console.error(e)
    ElMessage.error('更新失败')
  } finally {
    editLoading.value = false
  }
}

const openCoverSelector = () => {
  if (album.value?.count === 0) {
    ElMessage.warning('相册内暂无照片,无法更换封面')
    return
  }
  showCoverSelector.value = true
}

const handleCoverSelected = async (ids: string[]) => {
  if (ids.length === 0) return
  try {
    await albumStore.setAlbumCover(albumId, ids[0])
    await albumStore.fetchAlbums()
    showCoverSelector.value = false
    ElMessage.success('封面已更新')
  } catch (e) {
    console.error(e)
    ElMessage.error('封面更新失败')
  }
}

const deleteCurrentAlbum = async () => {
  if (!album.value) return
  try {
    await ElMessageBox.confirm(
      `确定要删除相册 "${album.value.title}" 吗?相册内的照片不会被删除。`,
      '删除相册',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    await albumStore.deleteAlbum(albumId)
    ElMessage.success('相册已删除')
    router.push('/album')
  } catch (e) {
    if (e !== 'cancel') {
      console.error(e)
      ElMessage.error('删除失败')
    }
  }
}

const handleMenuCommand = (command: string) => {
  if (command === 'edit') openEditModal()
  else if (command === 'cover') openCoverSelector()
  else if (command === 'delete') deleteCurrentAlbum()
}

const handleConfirmDelete = async (ids: string[], callback: (success: boolean) => void) => {
    try {
        if (isUserAlbum.value) {
            await albumStore.removePhotosFromAlbum(albumId, ids)
            photoStore.removeLocalPhotos(ids)
        } else {
            await photoStore.deletePhotos(ids)
        }
        callback(true)
        void albumStore.fetchAlbums()
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

        photoStore.removeLocalPhotos(ids)
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

</script>
