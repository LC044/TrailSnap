<template>
  <div v-if="visible" class="fixed inset-0 z-[1000] flex items-end justify-center bg-black/50 backdrop-blur-sm sm:items-center sm:p-4" @click.self="close">
    <div role="dialog" aria-modal="true" aria-label="选择相册" class="flex max-h-[90dvh] w-full flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl dark:bg-gray-800 sm:max-h-[80dvh] sm:max-w-lg sm:rounded-2xl">
      <div class="p-4 border-b border-gray-100 dark:border-gray-700 flex justify-between items-center shrink-0">
        <h3 class="text-lg font-bold text-gray-900 dark:text-white">选择相册</h3>
        <button type="button" aria-label="关闭" @click="close" class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full transition-colors bg-transparent">
          <X class="w-5 h-5 text-gray-500" />
        </button>
      </div>

      <!-- Search & Add Album -->
      <div class="p-4 pb-0 flex gap-2 shrink-0">
        <div class="relative min-w-0 flex-1">
          <input 
            v-model="searchQuery" 
            type="text" 
            placeholder="搜索相册..." 
            class="w-full pl-9 pr-4 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 transition-all"
          />
          <Search class="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
        </div>
        <button v-if="mode === 'add'" type="button" class="ts-button ts-button-secondary shrink-0"
          :disabled="!!loadingAlbumId || !!successAlbumId" @click="openCreateDialog">
          <Plus class="h-4 w-4" aria-hidden="true" />
          <span>新建相册</span>
        </button>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto p-4 pb-[max(1rem,var(--ts-safe-area-bottom))]">
        <div v-if="loading" class="flex justify-center py-10 text-primary-500"><Loader2 class="h-6 w-6 animate-spin" /></div>
        <div v-else-if="filteredAlbums.length === 0" class="text-center py-8 text-gray-500 dark:text-gray-400">
          {{ searchQuery ? '未找到相关相册' : mode === 'add' ? '暂无普通相册' : '暂无可选相册' }}
        </div>
        <div v-else class="space-y-2">
          <button
            v-for="album in filteredAlbums"
            :key="album.id"
            type="button"
            @click="chooseAlbum(album.id)"
            class="group relative flex w-full items-center gap-3 overflow-hidden rounded-xl border border-gray-100 bg-gray-50 p-2 text-left transition-colors hover:border-primary-300 hover:bg-primary-50/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-gray-700 dark:bg-gray-900/80 dark:hover:border-primary-600 dark:hover:bg-gray-700/50 sm:p-3"
            :class="{ 'shake-animation border-red-500': errorAlbumId === album.id, 'border-primary-500 dark:border-primary-500': mode === 'select' && selectedAlbumId === album.id }"
          >
            <div class="relative flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-primary-100 text-primary-500 dark:bg-primary-900/30 sm:h-16 sm:w-16">
              <img v-if="album.coverUrl" :src="album.coverUrl" :alt="`${album.title}的封面`" class="h-full w-full object-cover" loading="lazy" />
              <Folder v-else class="h-6 w-6" />
              <div v-if="loadingAlbumId === album.id || successAlbumId === album.id" class="absolute inset-0 flex items-center justify-center bg-black/50 text-white">
                <Loader2 v-if="loadingAlbumId === album.id" class="h-5 w-5 animate-spin" />
                <Check v-else class="h-5 w-5" />
              </div>
            </div>
            <div class="min-w-0 flex-1">
              <h4 class="truncate font-medium text-gray-900 dark:text-white">{{ album.title }}</h4>
              <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{{ album.count }} 个项目<span v-if="album.type === 'conditional'"> · 条件相册</span><span v-else-if="album.type === 'smart'"> · 智能相册</span></p>
            </div>
            <Check v-if="mode === 'select' && selectedAlbumId === album.id" class="h-5 w-5 shrink-0 text-primary-500" />
            <!-- Success Fade Overlay -->
            <div v-if="successAlbumId === album.id" class="absolute inset-0 bg-green-500/10 animate-in fade-in duration-300 pointer-events-none"></div>
          </button>
        </div>
      </div>
    </div>

  </div>
  <ResponsiveDialog v-model="showCreateDialog" title="新建相册" max-width="24rem"
    :before-close="() => !creatingAlbum">
    <form class="space-y-3" @submit.prevent="handleCreateAlbum">
      <label class="block space-y-2 text-sm font-medium">
        <span class="block">相册名称</span>
        <input v-model="newAlbumName" type="text" maxlength="100" required
          :disabled="creatingAlbum" class="ts-input w-full" placeholder="请输入相册名称" />
      </label>
      <div class="flex justify-end gap-2">
        <button type="button" class="ts-button ts-button-secondary" :disabled="creatingAlbum" @click="showCreateDialog = false">取消</button>
        <button type="submit" class="ts-button ts-button-primary" :disabled="!newAlbumName.trim() || creatingAlbum">
          <Loader2 v-if="creatingAlbum" class="h-4 w-4 animate-spin" aria-hidden="true" />
          {{ photoIds?.length ? '创建并加入' : '创建' }}
        </button>
      </div>
    </form>
  </ResponsiveDialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import { X, Loader2, Check, Folder, Plus, Search } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { useAlbumStore } from '@/stores/albumStore'
import { useOverlayStack } from '@/composables/useOverlayStack'
import { thumbnailUrl } from '@/utils/mediaUrl'
import type { ApiAlbum } from '@/types/album'

const props = withDefaults(defineProps<{
  visible: boolean
  photoIds?: string[]
  mode?: 'add' | 'select'
  selectionAlbums?: ApiAlbum[]
  selectedAlbumId?: string
  loading?: boolean
}>(), { mode: 'add' })

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'success', albumId: string): void
  (e: 'select', albumId: string): void
}>()

const albumStore = useAlbumStore()
const albums = computed(() => props.mode === 'select'
  ? (props.selectionAlbums || []).map(album => ({
      id: album.id,
      title: album.name,
      count: album.num_photos,
      type: album.type,
      coverUrl: album.cover?.id ? thumbnailUrl(album.cover.id, 'small', album.cover.owner_id) : '',
    }))
  : albumStore.allAlbums.map(album => ({
      id: album.id,
      title: album.title,
      count: album.count,
      type: album.type,
      coverUrl: album.cover.id ? album.cover.thumbnail : '',
    })))

const searchQuery = ref('')
const filteredAlbums = computed(() => {
  const query = searchQuery.value.toLowerCase().trim()
  return albums.value.filter(a => {
    if (props.mode !== 'select' && a.type !== 'user') return false
    if (!query) return true
    return a.title.toLowerCase().includes(query)
  })
})

const showCreateDialog = ref(false)
const newAlbumName = ref('')
const creatingAlbum = ref(false)

const openCreateDialog = () => {
  newAlbumName.value = ''
  showCreateDialog.value = true
}
const handleCreateAlbum = async () => {
  const name = newAlbumName.value.trim()
  if (!name || creatingAlbum.value) return

  creatingAlbum.value = true
  const photoIds = props.photoIds ?? []
  try {
    const albumId = await albumStore.createCustomAlbum(name, undefined, photoIds)
    showCreateDialog.value = false
    close()
    ElMessage.success(photoIds.length ? '已创建相册并加入所选照片' : '相册创建成功')
    emit('success', albumId)
  } catch {
    // The request layer shows the failure. Keep the name and selected photos for retry.
  } finally {
    creatingAlbum.value = false
  }
}

const loadingAlbumId = ref<string | null>(null)
const successAlbumId = ref<string | null>(null)
const errorAlbumId = ref<string | null>(null)

const close = () => {
  searchQuery.value = ''
  emit('update:visible', false)
}

useOverlayStack(computed(() => props.visible && !showCreateDialog.value), close)

const chooseAlbum = (albumId: string) => {
  if (props.mode === 'select') {
    emit('select', albumId)
    close()
  } else {
    confirmAddToAlbum(albumId)
  }
}

const confirmAddToAlbum = async (targetAlbumId: string) => {
  if (loadingAlbumId.value) return

  loadingAlbumId.value = targetAlbumId
  errorAlbumId.value = null
  try {
    await albumStore.addPhotosToAlbum(props.photoIds || [], 'add_to_album', targetAlbumId)

    loadingAlbumId.value = null
    successAlbumId.value = targetAlbumId

    // Play success animation (300ms)
    setTimeout(() => {
        close()
        ElMessage.success(`成功添加到相册`)
        successAlbumId.value = null
        emit('success', targetAlbumId)
    }, 300)
  } catch (error) {
    console.error('Batch add failed:', error)
    loadingAlbumId.value = null
    errorAlbumId.value = targetAlbumId
    
    // Reset error state after shake animation
    setTimeout(() => {
        errorAlbumId.value = null
    }, 500)
  }
}


</script>

<style scoped>
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-5px); }
  75% { transform: translateX(5px); }
}
.shake-animation {
  animation: shake 0.3s cubic-bezier(.36,.07,.19,.97) both;
}
</style>
