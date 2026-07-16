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
          class="flex items-center gap-1 py-1.5 pr-2 pl-2 rounded-lg cursor-pointer transition-colors select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
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
      <div class="flex items-center gap-2 sm:gap-3 px-3 sm:px-4 py-2.5 border-b border-gray-100 dark:border-gray-800">
        <button @click="goBack" :disabled="breadcrumb.length === 0" class="p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" title="返回上一层">
          <ArrowLeft class="w-5 h-5 text-gray-600 dark:text-gray-300" />
        </button>

        <!-- 面包屑 -->
        <nav class="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 flex-1 min-w-0 overflow-x-auto no-scrollbar">
          <button
            @click="navigateTo('')"
            class="hover:text-primary-500 transition-colors flex-shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 rounded"
            :class="{ 'text-gray-800 dark:text-white font-medium': breadcrumb.length === 0 }"
          >
            全部
          </button>
          <template v-for="(crumb, idx) in breadcrumb" :key="crumb.path">
            <ChevronRight class="w-4 h-4 flex-shrink-0" />
            <button
              @click="navigateTo(crumb.path)"
              class="hover:text-primary-500 transition-colors truncate max-w-[160px] flex-shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 rounded"
              :class="{ 'text-gray-800 dark:text-white font-medium': idx === breadcrumb.length - 1 }"
              :title="crumb.name"
            >
              {{ crumb.name }}
            </button>
          </template>
        </nav>

        <!-- 排序 -->
        <el-dropdown trigger="click" placement="bottom-end" @command="onSortCommand">
          <button class="flex items-center gap-1 px-2 py-1.5 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors flex-shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" title="排序">
            <ArrowUpDown class="w-4 h-4" />
            <span class="hidden sm:inline text-xs">{{ sortLabel }}</span>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="opt in sortOptions"
                :key="opt.key"
                :command="opt.key"
                :class="{ 'text-primary-500': opt.key === sortKey }"
              >
                <div class="flex items-center gap-2">
                  <Check v-if="opt.key === sortKey" class="w-3.5 h-3.5" />
                  <span v-else class="w-3.5"></span>
                  <span>{{ opt.label }}</span>
                </div>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <!-- 视图切换：网格 / 列表 -->
        <div class="flex items-center bg-gray-100 dark:bg-gray-800 rounded-lg p-1 flex-shrink-0">
          <button
            @click="setViewMode('grid')"
            class="p-1.5 rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
            :class="viewMode === 'grid' ? 'bg-white dark:bg-gray-700 shadow-sm text-primary-500' : 'text-gray-500 dark:text-gray-400'"
            title="网格视图"
          >
            <LayoutGrid class="w-4 h-4" />
          </button>
          <button
            @click="setViewMode('list')"
            class="p-1.5 rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
            :class="viewMode === 'list' ? 'bg-white dark:bg-gray-700 shadow-sm text-primary-500' : 'text-gray-500 dark:text-gray-400'"
            title="列表视图"
          >
            <List class="w-4 h-4" />
          </button>
        </div>

        <!-- 图片大小：小 / 中 / 大（仅网格视图） -->
        <div v-if="viewMode === 'grid'" class="flex items-center bg-gray-100 dark:bg-gray-800 rounded-lg p-1 flex-shrink-0">
          <button
            v-for="size in (['sm', 'md', 'lg'] as const)"
            :key="size"
            @click="setViewSize(size)"
            class="p-1.5 rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
            :class="props.viewSize === size ? 'bg-white dark:bg-gray-700 shadow-sm text-primary-500' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
            :title="sizeTitleMap[size]"
          >
            <Grid3x3 v-if="size === 'sm'" class="w-4 h-4" />
            <Grid2x2 v-else-if="size === 'md'" class="w-4 h-4" />
            <Maximize v-else class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- 内容滚动区 -->
      <div ref="scrollArea" class="flex-1 overflow-y-auto p-3 sm:p-4">
        <div v-if="foldersLoading" class="flex justify-center items-center py-16">
          <Loader2 class="w-8 h-8 text-primary-500 animate-spin" />
        </div>

        <template v-else>
          <div v-if="sortedChildren.length === 0 && photos.length === 0 && !photoLoading" class="flex flex-col items-center justify-center py-20 text-center">
            <FolderOpen class="w-16 h-16 text-gray-300 dark:text-gray-600 mb-4" />
            <p class="text-gray-500 dark:text-gray-400">此文件夹下暂无内容</p>
          </div>

          <!-- ===== 网格视图 ===== -->
          <template v-if="viewMode === 'grid'">
            <!-- 文件夹卡片 -->
            <div v-if="sortedChildren.length" :class="['grid gap-3 mb-6', folderGridClass]">
              <button
                v-for="folder in sortedChildren"
                :key="folder.path"
                @click="navigateTo(folder.path)"
                class="group flex flex-col items-center gap-2 p-3 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800 transition-all text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
              >
                <Folder class="w-14 h-14 text-primary-400 group-hover:text-primary-500 transition-colors" fill="currentColor" fill-opacity="0.15" />
                <div class="w-full min-w-0">
                  <div class="text-sm text-gray-800 dark:text-white truncate" :title="folder.name">{{ folder.name }}</div>
                  <div class="text-xs text-gray-400 dark:text-gray-500">{{ folder.count }} 项</div>
                </div>
              </button>
            </div>

            <!-- 照片：复用 FlatPhotoGallery（含选择 + 底部功能条） -->
            <FlatPhotoGallery
              v-if="photos.length > 0 || photoLoading"
              ref="galleryRef"
              :photos="photos"
              :loading="photoLoading && photos.length === 0"
              :view-size="props.viewSize"
              :scroll-container="scrollArea"
              :show-action-bar="true"
              @click-photo="handleGalleryClick"
              @batch-delete="handleBatchDelete"
              @add-to-album="handleAddToAlbum"
            />
          </template>

          <!-- ===== 列表视图 ===== -->
          <template v-else>
            <div class="min-w-full">
              <!-- 列头 -->
              <div class="flex items-center gap-2 px-3 py-2 text-xs font-medium text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-800 select-none">
                <div class="w-6 flex-shrink-0"></div>
                <button @click="toggleSort('name')" class="flex items-center gap-1 flex-1 min-w-0 hover:text-gray-600 dark:hover:text-gray-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 rounded">
                  名称
                  <ArrowUp v-if="sortField === 'name' && sortDir === 'asc'" class="w-3 h-3 text-primary-500" />
                  <ArrowDown v-else-if="sortField === 'name' && sortDir === 'desc'" class="w-3 h-3 text-primary-500" />
                </button>
                <button @click="toggleSort('time')" class="w-40 hidden sm:flex items-center gap-1 flex-shrink-0 hover:text-gray-600 dark:hover:text-gray-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 rounded">
                  修改时间
                  <ArrowUp v-if="sortField === 'time' && sortDir === 'asc'" class="w-3 h-3 text-primary-500" />
                  <ArrowDown v-else-if="sortField === 'time' && sortDir === 'desc'" class="w-3 h-3 text-primary-500" />
                </button>
                <button @click="toggleSort('size')" class="w-24 text-right flex items-center justify-end gap-1 flex-shrink-0 hover:text-gray-600 dark:hover:text-gray-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 rounded">
                  大小
                  <ArrowUp v-if="sortField === 'size' && sortDir === 'asc'" class="w-3 h-3 text-primary-500" />
                  <ArrowDown v-else-if="sortField === 'size' && sortDir === 'desc'" class="w-3 h-3 text-primary-500" />
                </button>
                <span class="w-20 text-right flex-shrink-0">类型</span>
              </div>

              <!-- 文件夹行 -->
              <div
                v-for="folder in sortedChildren"
                :key="folder.path"
                @click="navigateTo(folder.path)"
                class="flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                <div class="w-6 flex-shrink-0"></div>
                <Folder class="w-5 h-5 text-primary-400 flex-shrink-0" fill="currentColor" fill-opacity="0.15" />
                <span class="flex-1 min-w-0 truncate text-sm text-gray-800 dark:text-white" :title="folder.name">{{ folder.name }}</span>
                <span class="w-40 hidden sm:block flex-shrink-0 text-xs text-gray-400 dark:text-gray-500">—</span>
                <span class="w-24 text-right flex-shrink-0 text-xs text-gray-400 dark:text-gray-500">{{ folder.count }} 项</span>
                <span class="w-20 text-right flex-shrink-0 text-xs text-gray-400 dark:text-gray-500">文件夹</span>
              </div>

              <!-- 照片行 -->
              <div
                v-for="(photo, idx) in photos"
                :key="photo.id"
                class="group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors"
                :class="selectedIds.has(photo.id) ? 'bg-primary-50 dark:bg-primary-900/20' : 'hover:bg-gray-50 dark:hover:bg-gray-800'"
                @click="openLightbox(idx)"
              >
                <div class="w-6 flex-shrink-0 flex items-center justify-center" @click.stop="togglePhotoSelection(photo.id)">
                  <div
                    class="w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all duration-200"
                    :class="selectedIds.has(photo.id)
                      ? 'bg-primary-500 border-primary-500'
                      : (isSelectionMode
                        ? 'bg-black/10 border-white/70 dark:border-gray-600'
                        : 'bg-black/10 border-white/70 dark:border-gray-600 opacity-0 group-hover:opacity-100')"
                  >
                    <Check v-if="selectedIds.has(photo.id)" class="w-3 h-3 text-white" />
                  </div>
                </div>
                <img :src="photo.thumbnail" :alt="photo.filename" loading="lazy" class="w-8 h-8 rounded object-cover flex-shrink-0 bg-gray-100 dark:bg-gray-800" />
                <span class="flex-1 min-w-0 truncate text-sm text-gray-800 dark:text-white" :title="photo.filename">{{ photo.filename }}</span>
                <span class="w-40 hidden sm:block flex-shrink-0 text-xs text-gray-400 dark:text-gray-500">{{ formatTime(photo.timestamp) }}</span>
                <span class="w-24 text-right flex-shrink-0 text-xs text-gray-400 dark:text-gray-500">{{ formatSize(photo.size) }}</span>
                <span class="w-20 text-right flex-shrink-0 text-xs text-gray-400 dark:text-gray-500">{{ typeLabel(photo) }}</span>
              </div>
            </div>
          </template>

          <div ref="sentinel" class="h-10 flex items-center justify-center">
            <Loader2 v-if="photoLoading" class="w-5 h-5 text-primary-500 animate-spin" />
          </div>
        </template>
      </div>
    </section>

    <!-- 列表视图底部功能条 -->
    <transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="transform -translate-y-full opacity-0"
      enter-to-class="transform translate-y-0 opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="transform translate-y-0 opacity-100"
      leave-to-class="transform -translate-y-full opacity-0"
    >
      <div v-if="viewMode === 'list' && isSelectionMode" class="fixed bottom-[20px] left-0 right-0 z-40 flex justify-center pointer-events-none px-4">
        <div class="bg-white/90 dark:bg-gray-900/90 backdrop-blur-md border border-gray-200 dark:border-gray-700 shadow-lg rounded-full px-3 py-1 flex items-center gap-2 sm:gap-6 pointer-events-auto min-w-fit max-w-full overflow-x-auto scrollbar-hide">
          <div class="flex items-center gap-1 md:gap-3 flex-shrink-0">
            <button @click="exitSelectionMode" class="p-1.5 sm:p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-colors text-gray-600 dark:text-gray-300" title="取消选择">
              <X class="w-5 h-5" />
            </button>
            <span class="font-medium text-gray-900 dark:text-white whitespace-nowrap text-sm sm:text-base">
              已选 {{ selectedIds.size }} 项
            </span>
          </div>

          <div class="h-6 w-px bg-gray-300 dark:bg-gray-600 flex-shrink-0"></div>

          <div class="flex items-center gap-1 sm:gap-2 flex-nowrap">
            <button @click="toggleSelectAllList" class="p-2 sm:px-3 sm:py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors" :title="isAllSelectedList ? '取消全选' : '全选'">
              <span class="hidden sm:inline">{{ isAllSelectedList ? '取消全选' : '全选' }}</span>
              <CheckSquare class="w-5 h-5 sm:hidden" />
            </button>

            <button
              @click="handleListAddToAlbum"
              :disabled="selectedIds.size === 0"
              class="flex items-center gap-2 p-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="添加到相册"
            >
              <ImagePlusIcon class="w-5 h-5" />
            </button>

            <button
              @click="handleListDownload"
              :disabled="selectedIds.size === 0 || isDownloading"
              class="p-2 text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="保存到本地"
            >
              <Loader2 v-if="isDownloading" class="w-5 h-5 animate-spin" />
              <Download v-else class="w-5 h-5" />
            </button>

            <button
              @click="handleListDelete"
              :disabled="selectedIds.size === 0"
              class="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="删除"
            >
              <Trash2 class="w-5 h-5" />
            </button>

            <el-dropdown trigger="click" placement="top-end">
              <button class="p-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
                <MoreHorizontal class="w-5 h-5" />
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    :disabled="selectedIds.size === 0"
                    @click="showPersonSelector = true"
                  >
                    <div class="flex items-center gap-2">
                      <UserPlus class="w-4 h-4" />
                      <span>添加到人物</span>
                    </div>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </div>
    </transition>

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

    <!-- 添加到相册弹窗 -->
    <AlbumSelector
      v-model:visible="showAlbumSelectModal"
      :photo-ids="tempSelectedIds"
      @success="closeAlbumSelectModal"
    />

    <!-- 添加到人物弹窗 -->
    <PersonSelector
      v-model:visible="showPersonSelector"
      :submitting="isAddingPerson"
      @select="handlePersonSelected"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import {
  Folder, FolderOpen, FolderTree as FolderTree2, HardDrive, ChevronRight,
  ArrowLeft, Loader2, Grid3x3, Grid2x2, Maximize, LayoutGrid, List,
  ArrowUpDown, ArrowUp, ArrowDown, Check, X, Download, Trash2, ImagePlusIcon,
  MoreHorizontal, UserPlus, CheckSquare
} from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { albumService } from '@/api/album'
import { photoApi } from '@/api/photo'
import { faceApi } from '@/api/face'
import { mapPhotoToImage } from '@/stores/photoStore'
import { useSelection } from '@/composables/useSelection'
import type { AlbumImage } from '@/types/album'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import FlatPhotoGallery from '@/components/FlatPhotoGallery.vue'
import AlbumSelector from '@/components/AlbumSelector.vue'
import PersonSelector from '@/components/PersonSelector.vue'
import FolderTree from './FolderTree.vue'

interface FolderChild {
  name: string
  path: string
  count: number
  has_children: boolean
}

type ViewSize = 'sm' | 'md' | 'lg'
type ViewMode = 'grid' | 'list'
type SortField = 'name' | 'time' | 'size'
type SortDir = 'asc' | 'desc'

// viewSize 由父级「照片」视图统一控制（小/中/大），通过 v-model:view-size 双向同步
const props = withDefaults(defineProps<{ viewSize?: ViewSize }>(), {
  viewSize: 'md'
})
const emit = defineEmits<{ (e: 'update:viewSize', v: ViewSize): void }>()

const sizeTitleMap: Record<ViewSize, string> = { sm: '小', md: '中', lg: '大' }
const setViewSize = (size: ViewSize) => emit('update:viewSize', size)

const PAGE_SIZE = 100
const VIEW_MODE_KEY = 'trailsnap:folderViewMode'
const SORT_KEY = 'trailsnap:folderSort'

// 视图模式（网格 / 列表）
const viewMode = ref<ViewMode>((localStorage.getItem(VIEW_MODE_KEY) as ViewMode) || 'grid')
const setViewMode = (m: ViewMode) => {
  if (viewMode.value === m) return
  viewMode.value = m
  localStorage.setItem(VIEW_MODE_KEY, m)
  // 切换视图时退出各自的选择模式
  galleryRef.value?.exitSelectionMode()
  exitSelectionMode()
}

// 排序：默认按时间倒序（与服务端默认一致）
const defaultSortDir: Record<SortField, SortDir> = { name: 'asc', time: 'desc', size: 'desc' }
const sortField = ref<SortField>('time')
const sortDir = ref<SortDir>('desc')
const loadSortFromStorage = () => {
  try {
    const raw = localStorage.getItem(SORT_KEY)
    if (raw) {
      const obj = JSON.parse(raw)
      if (['name', 'time', 'size'].includes(obj.field)) sortField.value = obj.field
      if (['asc', 'desc'].includes(obj.dir)) sortDir.value = obj.dir
    }
  } catch { /* ignore */ }
}
loadSortFromStorage()
const persistSort = () => localStorage.setItem(SORT_KEY, JSON.stringify({ field: sortField.value, dir: sortDir.value }))

const sortKey = computed(() => `${sortField.value}:${sortDir.value}`)
const sortLabel = computed(() => {
  const f = { name: '名称', time: '时间', size: '大小' }[sortField.value]
  const d = sortDir.value === 'asc' ? '↑' : '↓'
  return `${f}${d}`
})
const sortOptions = [
  { key: 'name:asc', label: '名称 A→Z' },
  { key: 'name:desc', label: '名称 Z→A' },
  { key: 'time:desc', label: '时间 新→旧' },
  { key: 'time:asc', label: '时间 旧→新' },
  { key: 'size:desc', label: '大小 大→小' },
  { key: 'size:asc', label: '大小 小→大' }
] as const

const onSortCommand = (key: string) => {
  const [field, dir] = key.split(':') as [SortField, SortDir]
  sortField.value = field
  sortDir.value = dir
  persistSort()
  reloadPhotos()
}

const toggleSort = (field: SortField) => {
  if (sortField.value === field) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortDir.value = defaultSortDir[field]
  }
  persistSort()
  reloadPhotos()
}

// 排序 → 服务端参数
const sortParam = computed(() => ({
  order_by: { name: 'filename', time: 'photo_time', size: 'size' }[sortField.value],
  order_dir: sortDir.value
}))

// 当前所在的相对父路径（组件内部状态，不依赖路由）
const currentParent = ref('')

const children = ref<FolderChild[]>([])
const breadcrumb = ref<{ name: string; path: string }[]>([])
const ownCount = ref(0)
const foldersLoading = ref(true)

const photos = ref<AlbumImage[]>([])
const photoLoading = ref(false)
const hasMorePhotos = computed(() => photos.value.length < ownCount.value)

// 文件夹客户端排序（仅按名称，方向跟随当前排序）
const sortedChildren = computed(() => {
  const arr = [...children.value]
  arr.sort((a, b) => {
    const r = a.name.localeCompare(b.name, 'zh')
    return sortDir.value === 'asc' ? r : -r
  })
  return arr
})

const folderGridClass = computed(() => ({
  sm: 'grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8',
  md: 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6',
  lg: 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4'
}[props.viewSize]))

// 画廊 ref（网格视图，用于退出选择模式等）
const galleryRef = ref<InstanceType<typeof FlatPhotoGallery> | null>(null)

// 列表视图选择
const {
  isSelectionMode,
  selectedIds,
  enterSelectionMode,
  exitSelectionMode,
  toggleSelect,
  selectAll
} = useSelection()

const togglePhotoSelection = (id: string) => {
  toggleSelect(id)
  if (selectedIds.size > 0) enterSelectionMode()
  else exitSelectionMode()
}
const isAllSelectedList = computed(() => photos.value.length > 0 && photos.value.every(p => selectedIds.has(p.id)))
const toggleSelectAllList = () => {
  if (isAllSelectedList.value) {
    exitSelectionMode()
  } else {
    selectAll(photos.value.map(p => p.id))
    enterSelectionMode()
  }
}

// 查看器
const lightboxIndex = ref(-1)
const lightboxImage = computed(() => (lightboxIndex.value >= 0 ? photos.value[lightboxIndex.value] : null))
const openLightbox = (idx: number) => { lightboxIndex.value = idx }
const closeLightbox = () => { lightboxIndex.value = -1 }

// 弹窗
const showAlbumSelectModal = ref(false)
const tempSelectedIds = ref<string[]>([])
const showPersonSelector = ref(false)
const isAddingPerson = ref(false)
const isDownloading = ref(false)

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
      ...sortParam.value
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
  galleryRef.value?.exitSelectionMode()
  exitSelectionMode()
  await fetchLevel(parent)
  await loadPhotoPage()
  await nextTick()
  checkFillViewport()
}

// 排序变更后重载照片（ownCount 与排序无关，不重新拉文件夹）
const reloadPhotos = async () => {
  photos.value = []
  lightboxIndex.value = -1
  galleryRef.value?.exitSelectionMode()
  exitSelectionMode()
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

// 点击照片 → 打开查看器
const handleGalleryClick = (photo: AlbumImage) => {
  const idx = photos.value.findIndex(p => p.id === photo.id)
  if (idx !== -1) openLightbox(idx)
}

// 批量删除（网格 / 列表共用）
const handleBatchDelete = async (ids: string[]) => {
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`确定要删除选中的 ${ids.length} 张照片吗？`, '批量删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await albumService.batchUpdatePhotos({ photo_ids: ids, action: 'delete' })
    photos.value = photos.value.filter(p => !ids.includes(p.id))
    ownCount.value = Math.max(0, ownCount.value - ids.length)
    galleryRef.value?.exitSelectionMode()
    exitSelectionMode()
    ElMessage.success('批量删除成功')
  } catch (e) {
    if (e !== 'cancel') {
      console.error(e)
      ElMessage.error('删除失败')
    }
  }
}
const handleListDelete = () => handleBatchDelete(Array.from(selectedIds))

// 添加到相册（网格 / 列表共用）
const handleAddToAlbum = (ids: string[]) => {
  if (!ids.length) return
  tempSelectedIds.value = ids
  showAlbumSelectModal.value = true
}
const handleListAddToAlbum = () => handleAddToAlbum(Array.from(selectedIds))

const closeAlbumSelectModal = () => {
  showAlbumSelectModal.value = false
  tempSelectedIds.value = []
  galleryRef.value?.exitSelectionMode()
  exitSelectionMode()
}

// 列表视图下载
const handleListDownload = async () => {
  const ids = Array.from(selectedIds)
  if (!ids.length) return
  isDownloading.value = true
  try {
    await photoApi.batchDownload(ids)
  } catch (e) {
    console.error(e)
    ElMessage.error('下载失败')
  } finally {
    isDownloading.value = false
  }
}

// 添加到人物（列表视图）
const handlePersonSelected = async (person: any) => {
  if (selectedIds.size === 0) return
  isAddingPerson.value = true
  try {
    const ids = Array.from(selectedIds)
    const res = await faceApi.addPhotosToIdentity(person.id, ids)
    ElMessage.success(`成功添加 ${res.count} 张照片到 ${person.identity_name}`)
    showPersonSelector.value = false
    exitSelectionMode()
  } catch (e) {
    console.error(e)
    ElMessage.error('添加失败')
  } finally {
    isAddingPerson.value = false
  }
}

// 查看器内单张删除
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

// 格式化
const formatTime = (ts: number) => {
  if (!ts) return '—'
  const d = new Date(ts)
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
const formatSize = (bytes?: number) => {
  if (!bytes) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let n = bytes, i = 0
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${units[i]}`
}
const typeLabel = (photo: AlbumImage) => {
  if (photo.file_type === 'video') return '视频'
  if (photo.file_type === 'live_photo') return 'LIVE'
  return '图片'
}

watch(sentinel, (el) => {
  if (el && observer) observer.observe(el)
})

onMounted(() => {
  observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) loadPhotoPage()
  }, { root: scrollArea.value, rootMargin: '200px' })
  if (sentinel.value) observer.observe(sentinel.value)

  loadLevel('')
})

onUnmounted(() => {
  observer?.disconnect()
})
</script>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }

/* FlatPhotoGallery 默认 min-h-screen，在文件夹内部滚动区里会撑出多余空白，这里复位 */
:deep(.photo-gallery) {
  min-height: 0 !important;
}
</style>
