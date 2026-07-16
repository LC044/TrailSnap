<template>
  <div class="folder-browser flex h-[calc(100vh-150px)] gap-3 mt-2">
    <!-- 左侧目录树 -->
    <aside class="hidden md:flex flex-col w-56 lg:w-64 flex-shrink-0 rounded-2xl bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 overflow-hidden">
      <div class="px-3 py-3 border-b border-gray-100 dark:border-gray-800 flex items-center gap-2">
        <FolderTree2 class="w-5 h-5 text-primary-500" />
        <span class="font-bold text-gray-800 dark:text-white">文件夹</span>
      </div>
      <div class="flex-1 overflow-y-auto p-2">
        <div
          class="flex items-center gap-1 py-1.5 pr-2 pl-2 rounded-lg cursor-pointer transition-colors select-none"
          :class="currentParent === ''
            ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-600 dark:text-primary-300 font-medium'
            : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'"
          @click="navigateTo('')"
        >
          <HardDrive class="w-4 h-4 flex-shrink-0 text-primary-500" />
          <span class="text-sm">全部</span>
        </div>
        <FolderTree :parent-path="''" :current-path="currentParent" @navigate="navigateTo" />
      </div>
    </aside>

    <!-- 右侧内容区 -->
    <section class="flex-1 flex flex-col min-w-0 rounded-2xl bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 overflow-hidden">
      <!-- 工具栏 -->
      <div class="flex items-center gap-3 px-3 sm:px-4 py-2.5 border-b border-gray-100 dark:border-gray-800">
        <button @click="goBack" :disabled="breadcrumb.length === 0" class="p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed" title="返回上一层">
          <ArrowLeft class="w-5 h-5 text-gray-600 dark:text-gray-300" />
        </button>

        <!-- 面包屑 -->
        <nav class="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 flex-1 min-w-0 overflow-x-auto no-scrollbar">
          <button
            @click="navigateTo('')"
            class="hover:text-primary-500 transition-colors flex-shrink-0"
            :class="{ 'text-gray-800 dark:text-white font-medium': breadcrumb.length === 0 }"
          >
            全部
          </button>
          <template v-for="(crumb, idx) in breadcrumb" :key="crumb.path">
            <ChevronRight class="w-4 h-4 flex-shrink-0" />
            <button
              @click="navigateTo(crumb.path)"
              class="hover:text-primary-500 transition-colors truncate max-w-[160px] flex-shrink-0"
              :class="{ 'text-gray-800 dark:text-white font-medium': idx === breadcrumb.length - 1 }"
              :title="crumb.name"
            >
              {{ crumb.name }}
            </button>
          </template>
        </nav>

        <!-- 图标/列表切换 -->
        <div class="flex items-center bg-gray-100 dark:bg-gray-800 rounded-lg p-1 flex-shrink-0">
          <button
            @click="setViewMode('icon')"
            class="p-1.5 rounded-md transition-colors"
            :class="innerView === 'icon' ? 'bg-white dark:bg-gray-700 shadow-sm text-primary-500' : 'text-gray-500 dark:text-gray-400'"
            title="图标视图"
          >
            <LayoutGrid class="w-4 h-4" />
          </button>
          <button
            @click="setViewMode('list')"
            class="p-1.5 rounded-md transition-colors"
            :class="innerView === 'list' ? 'bg-white dark:bg-gray-700 shadow-sm text-primary-500' : 'text-gray-500 dark:text-gray-400'"
            title="列表视图"
          >
            <List class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- 内容滚动区 -->
      <div ref="scrollArea" class="flex-1 overflow-y-auto p-3 sm:p-4">
        <div v-if="foldersLoading" class="flex justify-center items-center py-16">
          <Loader2 class="w-8 h-8 text-primary-500 animate-spin" />
        </div>

        <template v-else>
          <div ref="gridContainer">
            <div v-if="children.length === 0 && photos.length === 0 && !photoLoading" class="flex flex-col items-center justify-center py-20 text-center">
              <FolderOpen class="w-16 h-16 text-gray-300 dark:text-gray-600 mb-4" />
              <p class="text-gray-500 dark:text-gray-400">此文件夹下暂无内容</p>
            </div>

            <!-- ===== 图标视图 ===== -->
            <template v-if="innerView === 'icon'">
              <div v-if="children.length" :class="['grid gap-3 mb-6', folderGridClass]">
                <button
                  v-for="folder in children"
                  :key="folder.path"
                  @click="navigateTo(folder.path)"
                  class="group flex flex-col items-center gap-2 p-3 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800 transition-all text-center"
                >
                  <Folder class="w-14 h-14 text-primary-400 group-hover:text-primary-500 transition-colors" fill="currentColor" fill-opacity="0.15" />
                  <div class="w-full min-w-0">
                    <div class="text-sm text-gray-800 dark:text-white truncate" :title="folder.name">{{ folder.name }}</div>
                    <div class="text-xs text-gray-400 dark:text-gray-500">{{ folder.count }} 项</div>
                  </div>
                </button>
              </div>

              <div v-if="photos.length" class="grid" :style="photoGridStyle">
                <button
                  v-for="(photo, idx) in photos"
                  :key="photo.id"
                  @click="openLightbox(idx)"
                  class="group relative aspect-square rounded-lg overflow-hidden bg-gray-100 dark:bg-gray-800"
                >
                  <img :src="photo.thumbnail" :alt="photo.filename" loading="lazy" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200" />
                  <span v-if="photo.file_type !== 'image'" class="absolute top-1 right-1 bg-black/50 text-white text-[10px] px-1 rounded">
                    {{ photo.file_type === 'live_photo' ? 'LIVE' : (photo.duration || '视频') }}
                  </span>
                </button>
              </div>
            </template>

            <!-- ===== 列表视图 ===== -->
            <template v-else>
              <div class="min-w-full">
                <div class="flex items-center gap-3 px-3 py-2 text-xs font-medium text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-800">
                  <span class="flex-1 min-w-0">名称</span>
                  <span class="w-40 hidden sm:block flex-shrink-0">修改时间</span>
                  <span class="w-24 text-right flex-shrink-0">大小</span>
                </div>

                <div
                  v-for="folder in children"
                  :key="folder.path"
                  @click="navigateTo(folder.path)"
                  class="flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                >
                  <Folder class="w-5 h-5 text-primary-400 flex-shrink-0" fill="currentColor" fill-opacity="0.15" />
                  <span class="flex-1 min-w-0 truncate text-sm text-gray-800 dark:text-white" :title="folder.name">{{ folder.name }}</span>
                  <span class="w-40 hidden sm:block flex-shrink-0 text-xs text-gray-400">—</span>
                  <span class="w-24 text-right flex-shrink-0 text-xs text-gray-400">{{ folder.count }} 项</span>
                </div>

                <div
                  v-for="(photo, idx) in photos"
                  :key="photo.id"
                  @click="openLightbox(idx)"
                  class="flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                >
                  <img :src="photo.thumbnail" :alt="photo.filename" loading="lazy" class="w-8 h-8 rounded object-cover flex-shrink-0 bg-gray-100 dark:bg-gray-800" />
                  <span class="flex-1 min-w-0 truncate text-sm text-gray-800 dark:text-white" :title="photo.filename">{{ photo.filename }}</span>
                  <span class="w-40 hidden sm:block flex-shrink-0 text-xs text-gray-400">{{ formatTime(photo.timestamp) }}</span>
                  <span class="w-24 text-right flex-shrink-0 text-xs text-gray-400">{{ formatSize(photo.size) }}</span>
                </div>
              </div>
            </template>

            <div ref="sentinel" class="h-10 flex items-center justify-center">
              <Loader2 v-if="photoLoading" class="w-5 h-5 text-primary-500 animate-spin" />
            </div>
          </div>
        </template>
      </div>
    </section>

    <!-- 查看器 -->
    <PhotoLightbox
      :visible="lightboxIndex >= 0"
      :image="lightboxImage"
      :has-prev="lightboxIndex > 0"
      :has-next="lightboxIndex >= 0 && lightboxIndex < photos.length - 1"
      delete-title="删除"
      @close="closeLightbox"
      @prev="lightboxIndex = Math.max(0, lightboxIndex - 1)"
      @next="lightboxIndex = Math.min(photos.length - 1, lightboxIndex + 1)"
      @delete="handleDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import {
  Folder, FolderOpen, FolderTree as FolderTree2, HardDrive, ChevronRight,
  ArrowLeft, LayoutGrid, List, Loader2
} from 'lucide-vue-next'
import { albumService } from '@/api/album'
import { mapPhotoToImage } from '@/stores/photoStore'
import { getPhotoColumns, getPhotoGap } from '@/utils/photoGridLayout'
import type { AlbumImage } from '@/types/album'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import FolderTree from './FolderTree.vue'
import { ElMessage } from 'element-plus'

interface FolderChild {
  name: string
  path: string
  count: number
  has_children: boolean
}

// viewSize 由父级「照片」视图设置的「图片大小」统一控制（小/中/大），保证与其它布局口径一致
const props = withDefaults(defineProps<{ viewSize?: 'sm' | 'md' | 'lg' }>(), {
  viewSize: 'md'
})

const PAGE_SIZE = 100
const VIEW_KEY = 'trailsnap:folderViewMode'

// 当前所在的相对父路径（组件内部状态，不依赖路由）
const currentParent = ref('')

const children = ref<FolderChild[]>([])
const breadcrumb = ref<{ name: string; path: string }[]>([])
const ownCount = ref(0)
const foldersLoading = ref(true)

const photos = ref<AlbumImage[]>([])
const photoLoading = ref(false)
const hasMorePhotos = computed(() => photos.value.length < ownCount.value)

// 图标 / 列表（文件夹专有），记忆到 localStorage
const innerView = ref<'icon' | 'list'>((localStorage.getItem(VIEW_KEY) as 'icon' | 'list') || 'icon')
const setViewMode = (m: 'icon' | 'list') => {
  innerView.value = m
  localStorage.setItem(VIEW_KEY, m)
}

// 内容区实测宽度（像素级对齐照片页尺寸口径）
const gridContainer = ref<HTMLElement | null>(null)
const contentWidth = ref(0)
let resizeOb: ResizeObserver | null = null

const photoGridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${getPhotoColumns(contentWidth.value, props.viewSize)}, minmax(0, 1fr))`,
  gap: `${getPhotoGap(props.viewSize)}px`
}))

const folderGridClass = computed(() => ({
  sm: 'grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8',
  md: 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6',
  lg: 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4'
}[props.viewSize]))

// 查看器
const lightboxIndex = ref(-1)
const lightboxImage = computed(() => (lightboxIndex.value >= 0 ? photos.value[lightboxIndex.value] : null))
const openLightbox = (idx: number) => { lightboxIndex.value = idx }
const closeLightbox = () => { lightboxIndex.value = -1 }

const scrollArea = ref<HTMLElement | null>(null)
const sentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

const fetchLevel = async (parent: string) => {
  foldersLoading.value = true
  try {
    const data = await albumService.getFolders(parent)
    children.value = data.children || []
    breadcrumb.value = data.breadcrumb || []
    ownCount.value = data.own_count || 0
  } catch (e) {
    console.error(e)
    ElMessage.error('获取文件夹列表失败')
  } finally {
    foldersLoading.value = false
  }
}

const loadPhotoPage = async () => {
  if (photoLoading.value || !hasMorePhotos.value) return
  photoLoading.value = true
  try {
    const data = await albumService.getAllPhotos(photos.value.length, PAGE_SIZE, {
      folder: currentParent.value,
      folder_direct: true,
      order_by: 'photo_time'
    })
    photos.value.push(...data.map(mapPhotoToImage))
  } catch (e) {
    console.error(e)
  } finally {
    photoLoading.value = false
  }
}

const loadLevel = async (parent: string) => {
  photos.value = []
  ownCount.value = 0
  lightboxIndex.value = -1
  await fetchLevel(parent)
  await loadPhotoPage()
  await nextTick()
  checkFillViewport()
}

const checkFillViewport = async () => {
  let guard = 0
  while (hasMorePhotos.value && scrollArea.value && guard < 20) {
    if (scrollArea.value.scrollHeight <= scrollArea.value.clientHeight + 50) {
      await loadPhotoPage()
      await nextTick()
      guard++
    } else break
  }
}

const navigateTo = (parent: string) => {
  if (parent === currentParent.value) return
  currentParent.value = parent
  loadLevel(parent)
}

const goBack = () => {
  if (breadcrumb.value.length > 0) {
    const parentPath = breadcrumb.value.length > 1 ? breadcrumb.value[breadcrumb.value.length - 2].path : ''
    navigateTo(parentPath)
  }
}

const handleDelete = async (id: string) => {
  try {
    await albumService.batchUpdatePhotos({ photo_ids: [id], action: 'delete' })
    const removedIdx = photos.value.findIndex(p => p.id === id)
    photos.value = photos.value.filter(p => p.id !== id)
    ownCount.value = Math.max(0, ownCount.value - 1)
    if (photos.value.length === 0) {
      closeLightbox()
    } else if (removedIdx >= 0) {
      lightboxIndex.value = Math.min(removedIdx, photos.value.length - 1)
    }
    ElMessage.success('已删除')
  } catch (e) {
    console.error(e)
    ElMessage.error('删除失败')
  }
}

const formatTime = (ts: number) => {
  if (!ts) return '—'
  const d = new Date(ts)
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
const formatSize = (bytes: number) => {
  if (!bytes) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let n = bytes, i = 0
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${units[i]}`
}

watch(sentinel, (el) => {
  if (el && observer) observer.observe(el)
})

watch(gridContainer, (el) => {
  if (el && resizeOb) {
    resizeOb.disconnect()
    resizeOb.observe(el)
    contentWidth.value = el.clientWidth
  }
})

onMounted(() => {
  observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) loadPhotoPage()
  }, { root: scrollArea.value, rootMargin: '200px' })
  if (sentinel.value) observer.observe(sentinel.value)

  resizeOb = new ResizeObserver((entries) => {
    const w = entries[0]?.contentRect?.width
    if (w) contentWidth.value = w
  })
  if (gridContainer.value) {
    resizeOb.observe(gridContainer.value)
    contentWidth.value = gridContainer.value.clientWidth
  }

  loadLevel('')
})

onUnmounted(() => {
  observer?.disconnect()
  resizeOb?.disconnect()
})
</script>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
