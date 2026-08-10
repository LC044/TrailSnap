<template>
  <div v-if="visible" class="z-[1000] fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" @click.self="close">
    <div class="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
      <div class="p-4 border-b border-gray-100 dark:border-gray-700 flex justify-between items-center">
        <h3 class="text-lg font-bold text-gray-900 dark:text-white">选择相册</h3>
        <button @click="close" class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full transition-colors bg-transparent">
          <X class="w-5 h-5 text-gray-500" />
        </button>
      </div>

      <!-- Search & Add Album -->
      <div class="p-4 pb-0 flex gap-2">
        <div class="relative flex-1">
          <input 
            v-model="searchQuery" 
            type="text" 
            placeholder="搜索相册..." 
            class="w-full pl-9 pr-4 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 transition-all"
          />
          <Search class="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
        </div>
        <button 
          @click="showCreateDialog = true"
          class="p-2 bg-primary-50 text-primary-600 hover:bg-primary-100 dark:bg-primary-900/30 dark:text-primary-400 dark:hover:bg-primary-900/50 rounded-lg transition-colors flex items-center justify-center"
          title="新建相册"
        >
          <Plus class="w-5 h-5" />
        </button>
      </div>

      <div class="p-4 max-h-[60vh] overflow-y-auto">
        <div v-if="filteredAlbums.length === 0" class="text-center py-8 text-gray-500">
          {{ searchQuery ? '未找到相关相册' : '暂无普通相册' }}
        </div>
        <div v-else class="space-y-2">
          <button
            v-for="album in filteredAlbums"
            :key="album.id"
            @click="confirmAddToAlbum(album.id)"
            class="w-full flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-900/80 backdrop-blur-md rounded-xl hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors text-left group relative overflow-hidden"
            :class="{ 'shake-animation border border-red-500': errorAlbumId === album.id }"
          >
            <div class="w-10 h-10 rounded-lg bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center text-primary-500 group-hover:scale-110 transition-transform">
              <Loader2 v-if="loadingAlbumId === album.id" class="w-5 h-5 animate-spin" />
              <Check v-else-if="successAlbumId === album.id" class="w-5 h-5 animate-in zoom-in duration-300" />
              <Folder v-else class="w-5 h-5" />
            </div>
            <div>
              <h4 class="font-medium text-gray-900 dark:text-white">{{ album.title }}</h4>
              <p class="text-xs text-gray-500">{{ album.count }} 张照片</p>
            </div>
            <!-- Success Fade Overlay -->
            <div v-if="successAlbumId === album.id" class="absolute inset-0 bg-green-500/10 animate-in fade-in duration-300 pointer-events-none"></div>
          </button>
        </div>
      </div>
    </div>

    <!-- Create Album Dialog Overlay -->
    <div v-if="showCreateDialog" class="absolute inset-0 z-[60] flex items-center justify-center p-4 bg-black/20 backdrop-blur-[1px] animate-in fade-in duration-200" @click.self="showCreateDialog = false">
      <div class="bg-white dark:bg-gray-800 rounded-xl w-full max-w-sm shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200 border border-gray-100 dark:border-gray-700">
        <div class="p-4 border-b border-gray-100 dark:border-gray-700 flex justify-between items-center">
          <h3 class="text-base font-bold text-gray-900 dark:text-white">新建相册</h3>
          <button @click="showCreateDialog = false" class="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full transition-colors text-gray-500">
            <X class="w-4 h-4" />
          </button>
        </div>
        <div class="p-4 space-y-4">
          <div>
            <label class="block text-xs font-medium text-gray-500 mb-1">相册名称</label>
            <input 
              v-model="newAlbumName" 
              type="text" 
              placeholder="请输入相册名称" 
              class="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 transition-all text-gray-900 dark:text-white"
              @keyup.enter="handleCreateAlbum"
            />
          </div>
          <div class="flex justify-end gap-2">
            <button 
              @click="showCreateDialog = false"
              class="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              取消
            </button>
            <button 
              @click="handleCreateAlbum"
              :disabled="!newAlbumName.trim() || creatingAlbum"
              class="px-3 py-1.5 text-sm bg-primary-500 hover:bg-primary-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              <Loader2 v-if="creatingAlbum" class="w-3 h-3 animate-spin" />
              创建
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { X, Loader2, Check, Folder, Plus, Search } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { useAlbumStore } from '@/stores/albumStore'
import { useOverlayStack } from '@/composables/useOverlayStack'

const props = defineProps<{
  visible: boolean
  photoIds: string[]
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'success', albumId: string): void
}>()

const albumStore = useAlbumStore()
const albums = computed(() => albumStore.allAlbums)

const searchQuery = ref('')
const filteredAlbums = computed(() => {
  const query = searchQuery.value.toLowerCase().trim()
  return albums.value.filter(a => {
    if (a.type !== 'user') return false
    if (!query) return true
    return a.title.toLowerCase().includes(query)
  })
})

const showCreateDialog = ref(false)
const newAlbumName = ref('')
const creatingAlbum = ref(false)

const handleCreateAlbum = async () => {
  if (!newAlbumName.value.trim()) return
  
  creatingAlbum.value = true
  try {
    const newAlbumId = await albumStore.createCustomAlbum(newAlbumName.value.trim())
    ElMessage.success('相册创建成功')
    newAlbumName.value = ''
    showCreateDialog.value = false
    // Optionally auto-select or just refresh list (store updates automatically)
  } catch (error) {
    console.error('Failed to create album:', error)
    ElMessage.error('创建相册失败')
  } finally {
    creatingAlbum.value = false
  }
}

const loadingAlbumId = ref<string | null>(null)
const successAlbumId = ref<string | null>(null)
const errorAlbumId = ref<string | null>(null)

const close = () => {
  emit('update:visible', false)
}

useOverlayStack(computed(() => props.visible), close)

const confirmAddToAlbum = async (targetAlbumId: string) => {
  if (loadingAlbumId.value) return

  loadingAlbumId.value = targetAlbumId
  errorAlbumId.value = null
  try {
    await albumStore.addPhotosToAlbum(props.photoIds, 'add_to_album', targetAlbumId)

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
