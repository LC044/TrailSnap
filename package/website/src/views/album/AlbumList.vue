<template>
  <div class="container mx-auto px-4 py-6">
    <!-- Header -->
    <div class="mb-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <h1 class="text-2xl font-bold text-gray-800 dark:text-white">我的相册</h1>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="flex items-center gap-2 rounded-lg border border-primary-500 px-3 py-2 text-sm text-primary-600 transition-colors hover:bg-primary-500/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="startTravelAlbum">
          <WandSparkles class="h-4 w-4" /><span>AI 整理旅行</span>
        </button>
        <button type="button" class="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800" @click="startAlbumDoctor">
          <Stethoscope class="h-4 w-4" /><span>AI 相册体检</span>
        </button>
        <button type="button" class="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800" @click="router.push('/agent/actions')">
          <History class="h-4 w-4" /><span>操作记录</span>
        </button>
        <el-dropdown trigger="click" @command="openCreateModal">
        <button 
          class="bg-primary-500 hover:bg-primary-600 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors shadow-lg shadow-primary-500/20 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
        >
          <Plus class="w-5 h-5" />
          <span>新建相册</span>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="user">普通相册</el-dropdown-item>
            <el-dropdown-item command="conditional">条件相册</el-dropdown-item>
            <el-dropdown-item command="smart">智能相册</el-dropdown-item>
          </el-dropdown-menu>
        </template>
        </el-dropdown>
      </div>
    </div>

    <!-- Smart Albums Section -->
    <div class="mb-10">
      <h2 class="text-lg font-semibold text-gray-700 dark:text-gray-200 mb-4 flex items-center gap-2">
        <Sparkles class="w-5 h-5 text-yellow-500" />
        智能相册
      </h2>
      <div class="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-5 lg:gap-6">
        <div 
          v-for="album in smartAlbums" 
          :key="album.id"
          class="group cursor-pointer relative rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
          role="button"
          tabindex="0"
          @click="navigateToSmartAlbum(album)"
          @keydown.enter="navigateToSmartAlbum(album)"
        >
          <!-- Cover -->
          <div class="aspect-square rounded-xl overflow-hidden bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-800 dark:to-gray-900 relative shadow-sm group-hover:shadow-md transition-all duration-300 mb-3 border border-gray-100 dark:border-gray-800 flex items-center justify-center">
             <!-- Icon/Cover Content -->
             <component :is="album.icon" class="w-12 h-12 text-gray-400 group-hover:text-primary-500 transition-colors duration-300" stroke-width="1.5" />
             
             <!-- Overlay -->
             <div class="absolute inset-0 bg-black/0 group-hover:bg-black/5 transition-colors"></div>
          </div>
          <!-- Info -->
          <div class="mt-2">
             <h3 class="font-bold text-gray-900 dark:text-white truncate">{{ album.title }}</h3>
             <p class="text-xs text-gray-500 dark:text-gray-400">{{ album.description }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Custom Albums Section -->
    <div>
      <h2 class="text-lg font-semibold text-gray-700 dark:text-gray-200 mb-4 flex items-center gap-2">
        <FolderHeart class="w-5 h-5 text-primary-500" />
        自定义相册
      </h2>
      
      <div v-if="store.allAlbums.length > 0" class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-5 lg:gap-6">
        <div
          v-for="album in store.allAlbums"
          :key="album.id"
          class="group cursor-pointer animate-in fade-in slide-in-from-bottom-4 duration-500 relative rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
          role="button"
          tabindex="0"
          @click="navigateToAlbum(album.id)"
          @keydown.enter="navigateToAlbum(album.id)"
        >
          <!-- Cover -->
          <div class="aspect-square rounded-xl overflow-hidden bg-gray-100 dark:bg-gray-800 relative shadow-sm group-hover:shadow-md transition-all duration-300 mb-3 border border-gray-100 dark:border-gray-800">
            <img
              :src="album.cover.thumbnail"
              class="w-full h-full object-cover transform group-hover:scale-105 transition-transform duration-500"
              loading="lazy"
            />
            <!-- Overlay -->
            <div class="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors"></div>
            <!-- Type Badge -->
            <div class="absolute top-2 right-2 flex gap-1">
               <span v-if="album.type === 'smart'" class="bg-primary-600/90 backdrop-blur-sm text-white text-xs px-2 py-0.5 rounded-full flex items-center gap-1">
                 <Sparkles class="w-3 h-3 text-white" /> 智能
               </span>
               <span v-if="album.type === 'conditional'" class="bg-primary-500/90 backdrop-blur-sm text-white text-xs px-2 py-0.5 rounded-full flex items-center gap-1">
                 <Filter class="w-3 h-3 text-white" /> 条件
               </span>
            </div>

            <!-- Actions (Only for User Albums) -->
            <div class="absolute top-2 right-2 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10" v-if="album.type !== 'system'">
              <button
                @click.stop="openEditModal(album)"
                class="p-1.5 bg-white/90 dark:bg-gray-800/90 rounded-full text-gray-600 dark:text-gray-300 hover:text-primary-500 shadow-sm backdrop-blur-sm"
                title="编辑"
              >
                <Edit2 class="w-4 h-4" />
              </button>
              <button
                @click.stop="confirmDelete(album)"
                class="p-1.5 bg-white/90 dark:bg-gray-800/90 rounded-full text-gray-600 dark:text-gray-300 hover:text-red-500 shadow-sm backdrop-blur-sm"
                title="删除"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>
          <!-- Info -->
          <div class="mt-2">
            <h3 class="font-bold text-gray-900 dark:text-white truncate">{{ album.title }}</h3>
            <div class="flex justify-between items-center mt-1">
              <p class="text-xs text-gray-500 dark:text-gray-400">{{ album.count }} 个项目</p>
              <!-- <p class="text-xs text-gray-400">{{ formatDate(album.createdAt) }}</p> -->
            </div>
          </div>
        </div>
      </div>
      
      <!-- Empty State for Custom Albums -->
      <div v-else class="flex flex-col items-center justify-center py-20 text-gray-400 bg-gray-50 dark:bg-gray-800/50 rounded-xl border-dashed border-2 border-gray-200 dark:border-gray-800">
        <div class="w-16 h-16 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center mb-4">
          <FolderOpen class="w-8 h-8 text-gray-300 dark:text-gray-600" />
        </div>
        <p>暂无自定义相册</p>
        <button @click="openCreateModal('user')" class="mt-4 text-primary-500 hover:underline">创建一个？</button>
      </div>
    </div>

    <!-- Create/Edit Modal -->
    <el-dialog
      v-model="showModal"
      :title="isEditing ? '编辑相册' : '新建相册'"
      :width="dialogWidth"
      class="rounded-xl"
      destroy-on-close
    >
      <div class="space-y-4">
        <!-- Name -->
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">相册名称</label>
          <input 
            v-model="form.name"
            type="text" 
            class="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 outline-none transition-all"
            placeholder="请输入相册名称"
          />
        </div>

        <!-- Description (Smart Album or User Album or Conditional Album) -->
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {{ form.type === 'smart' ? '智能描述 (AI 自动匹配)' : '描述 (可选)' }}
          </label>
          <textarea 
            v-model="form.description"
            rows="3"
            class="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 outline-none transition-all resize-none"
            :placeholder="form.type === 'smart' ? '例如：去年夏天的海边旅行，有沙滩和大海...' : '相册描述...'"
          ></textarea>
        </div>

        <!-- Smart Album Threshold -->
        <div v-if="form.type === 'smart'">
          <div class="flex justify-between items-center mb-1">
             <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">匹配阈值</label>
             <span class="text-xs text-gray-500 dark:text-gray-400">{{ (form.threshold * 100).toFixed(0) }}%</span>
          </div>
          <el-slider
            v-model="form.threshold"
            :min="0.15"
            :max="0.5"
            :step="0.01"
            :format-tooltip="(val: number) => (val * 100).toFixed(0) + '%'"
          />
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">阈值越高匹配越严格，建议值 0.25</p>
        </div>

        <!-- Conditional Album Fields -->
        <div v-if="form.type === 'conditional'" class="space-y-4 border-t border-gray-100 dark:border-gray-800 pt-4">
            <h4 class="font-medium text-gray-900 dark:text-white">筛选条件</h4>

            <!-- Folders -->
            <div>
                <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">文件夹</label>
                <el-tree-select
                    v-model="form.folders"
                    :props="folderTreeProps"
                    :load="loadFolderOptions"
                    :cache-data="selectedFolderCache"
                    node-key="path"
                    multiple
                    show-checkbox
                    check-strictly
                    lazy
                    filterable
                    clearable
                    collapse-tags
                    collapse-tags-tooltip
                    placeholder="选择文件夹"
                    class="w-full"
                />
                <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">包含所选文件夹及其全部子文件夹中的照片</p>
            </div>
            
            <!-- Time Range -->
            <div>
                <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">时间范围</label>
                <!-- Desktop Date Range -->
                <el-date-picker
                    v-if="!isMobile"
                    v-model="form.timeRange"
                    type="daterange"
                    range-separator="至"
                    start-placeholder="开始日期"
                    end-placeholder="结束日期"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    class="w-full"
                    style="width: 100%"
                />
                <!-- Mobile Date Range -->
                <div v-else class="flex items-center gap-2">
                    <el-date-picker
                        v-model="timeRangeStart"
                        type="date"
                        placeholder="开始日期"
                        value-format="YYYY-MM-DDTHH:mm:ss"
                        class="flex-1 !w-full"
                    />
                    <span class="text-gray-500 dark:text-gray-400 text-xs">至</span>
                    <el-date-picker
                        v-model="timeRangeEnd"
                        type="date"
                        placeholder="结束日期"
                        value-format="YYYY-MM-DDTHH:mm:ss"
                        class="flex-1 !w-full"
                    />
                </div>
            </div>
            
            <!-- Locations -->
            <div>
                <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">地点</label>
                <el-select
                    v-model="form.locations"
                    multiple
                    filterable
                    remote
                    reserve-keyword
                    placeholder="请输入地点关键词搜索"
                    :remote-method="searchLocation"
                    :loading="locationLoading"
                    value-key="_id"
                    class="w-full"
                >
                    <el-option
                        v-for="item in locationOptions"
                        :key="item.label"
                        :label="item.label"
                        :value="item.value"
                    />
                </el-select>
                <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">支持搜索省、市、区</p>
            </div>

            <!-- People -->
            <div>
                <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">人物</label>
                <el-select
                    v-model="form.people"
                    multiple
                    placeholder="选择人物"
                    class="w-full"
                    filterable
                >
                    <!-- 如果为空，显示提示 -->
                    <div v-if="form.people.length === 0" class="text-xs text-gray-400 dark:text-gray-500 italic">暂无人物条件</div>
                    <!-- 否则，显示人物条件 -->
                    <el-option
                        v-for="face in faces"
                        :key="face.id"
                        :label="face.identity_name || '未知'"
                        :value="face.id"
                    />
                </el-select>
            </div>
        </div>

      </div>
      <template #footer>
        <div class="flex justify-end gap-3">
          <button 
            @click="closeModal" 
            class="px-4 py-2 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          >
            取消
          </button>
          <button 
            @click="submitForm" 
            class="px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg shadow-lg shadow-primary-500/20 transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="!form.name.trim() || loading"
          >
            {{ loading ? '保存中...' : '保存' }}
          </button>
        </div>
      </template>
    </el-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAlbumStore } from '@/stores/albumStore'
import type { Album, FaceIdentity, CreateAlbumDto } from '@/types/album'
import { Plus, Sparkles, Edit2, Trash2, Clock, Users, MapPin, FolderHeart, FolderOpen, Tag, Filter, History, Stethoscope, WandSparkles } from 'lucide-vue-next'
import { albumService } from '@/api/album'
import { locationService } from '@/api/location'
import { faceApi } from '@/api/face'
import { ElMessage, ElMessageBox } from 'element-plus'
import { format } from 'date-fns'
import { useWindowSize } from '@vueuse/core'
import { useUiStore } from '@/stores/uiStore'

const router = useRouter()
const store = useAlbumStore()
const uiStore = useUiStore()

const startTravelAlbum = () => {
  uiStore.openAgentWithPrompt('请加载 travel-album Skill，帮我自动发现最近值得整理的一段旅行。先展示少量旅行候选让我确认日期和地点；确认后挑选代表照片，生成旅行日志、个性化 HTML 和需要我确认的正式相册计划。不要替我执行相册计划。', true)
}

const startAlbumDoctor = () => {
  uiStore.openAgentWithPrompt('请加载 album-doctor Skill，对我的整个照片库做一次只读体检。按严重程度总结缺少时间、地点、AI 描述、文件指纹、未归档照片、完全重复照片和相册结构异常；只展示少量证据样本与建议，不要删除、修改照片，也不要替我执行任何计划。', true)
}

const { width } = useWindowSize()
const dialogWidth = computed(() => width.value < 640 ? '90%' : '500px')
const isMobile = computed(() => width.value < 640)

const formatDate = (timestamp: number) => {
  return format(new Date(timestamp), 'yyyy-MM-dd')
}

// Smart Albums Configuration
const smartAlbums = [
  {
    id: 'people',
    title: '人物相册',
    description: '智能人脸识别',
    icon: Users,
    route: '/album/people'
  },
  {
    id: 'location',
    title: '位置相册',
    description: '按地点分类',
    icon: MapPin,
    route: '/album/location'
  },
  {
    id: 'classification',
    title: '智能分类',
    description: 'AI自动分类',
    icon: Tag,
    route: '/album/classification'
  }
]

const navigateToSmartAlbum = (album: any) => {
  if (album.route) {
    router.push(album.route)
  } else {
    ElMessage.info('功能开发中，敬请期待')
  }
}

const navigateToAlbum = (id: string) => {
  router.push(`/album/${id}`)
}

// Modal Logic
const showModal = ref(false)
const isEditing = ref(false)
const loading = ref(false)
const currentAlbumId = ref<string | null>(null)
const faces = ref<FaceIdentity[]>([])

interface LocationForm {
    province: string;
    city: string;
    district: string;
    _id?: string;
}

const locationOptions = ref<{ label: string; value: LocationForm }[]>([])
const locationLoading = ref(false)

interface FolderOption {
  name: string
  path: string
  isLeaf: boolean
}

const folderTreeProps = {
  label: 'name',
  children: 'children',
  isLeaf: 'isLeaf'
}

const toFolderOptions = (children: { name: string; path: string; has_children: boolean }[]): FolderOption[] =>
  children.map(folder => ({
    name: folder.name,
    path: folder.path,
    isLeaf: !folder.has_children
  }))

const loadFolderOptions = async (node: any, resolve: (options: FolderOption[]) => void) => {
  try {
    const parent = node.level === 0 ? '' : node.data.path
    const data = await albumService.getFolders(parent)
    const options = toFolderOptions(data.children || [])
    resolve(options)
  } catch (error) {
    console.error('Failed to load folders', error)
    resolve([])
  }
}

const searchLocation = async (query: string) => {
  if (query) {
    locationLoading.value = true
    try {
        const res = await locationService.searchLocations(query)
        const newOptions = res.map(item => ({
            label: item.label,
            value: {
                province: item.value.province || '',
                city: item.value.city || '',
                district: item.value.district || '',
                _id: item.label
            }
        }))
        
        // Merge with existing selected items to keep them visible
        const selectedIds = new Set(form.locations.map(l => l._id))
        const existingOptions = locationOptions.value.filter(o => selectedIds.has(o.value._id))
        
        // Filter out duplicates from new options
        const existingIds = new Set(existingOptions.map(o => o.value._id))
        const filteredNew = newOptions.filter(o => !existingIds.has(o.value._id))
        
        locationOptions.value = [...existingOptions, ...filteredNew]
    } catch (e) {
        console.error(e)
    } finally {
        locationLoading.value = false
    }
  } else {
     // Keep selected options
     const selectedIds = new Set(form.locations.map((l: any) => l._id))
     locationOptions.value = locationOptions.value.filter(o => selectedIds.has(o.value._id))
  }
}

const form = reactive({
  name: '',
  description: '',
  type: 'user', // user, smart, conditional
  timeRange: [] as string[],
  locations: [] as LocationForm[],
  people: [] as string[],
  folders: [] as string[],
  threshold: 0.25
})

const selectedFolderCache = computed(() => form.folders.map(path => ({
  name: path.split('/').filter(Boolean).pop() || path,
  path,
  isLeaf: false
})))

const timeRangeStart = computed({
  get: () => form.timeRange[0] || '',
  set: (val) => {
    form.timeRange[0] = val || ''
    if (!form.timeRange[0] && !form.timeRange[1]) form.timeRange = []
  }
})

const timeRangeEnd = computed({
  get: () => form.timeRange[1] || '',
  set: (val) => {
    if (!form.timeRange[0]) form.timeRange[0] = ''
    form.timeRange[1] = val || ''
    if (!form.timeRange[0] && !form.timeRange[1]) form.timeRange = []
  }
})

const fetchFaces = async () => {
    try {
        const data = await faceApi.listIdentities(1, 1000); // Fetch all/many faces
        // Filter out faces with no identity_name
        faces.value = data.filter((face: FaceIdentity) => face.identity_name !== '未命名');
    } catch (e) {
        console.error("Failed to fetch faces", e);
    }
}

const openCreateModal = async (type: string = 'user') => {
  isEditing.value = false
  currentAlbumId.value = null
  form.name = ''
  form.description = ''
  form.type = type
  form.timeRange = []
  form.locations = []
  locationOptions.value = []
  form.people = []
  form.folders = []
  form.threshold = 0.25
  
  if (type === 'conditional') {
      await fetchFaces()
  }
  
  showModal.value = true
}

const openEditModal = async (album: any) => {
  isEditing.value = true
  currentAlbumId.value = album.id
  form.name = album.title || album.name
  form.description = album.description || ''
  form.type = album.type || 'user'
  form.threshold = album.threshold !== undefined ? album.threshold : 0.25
  
  // Reset fields
  form.timeRange = []
  form.locations = []
  locationOptions.value = []
  form.people = []
  form.folders = []
  if (form.type === 'conditional' && album.condition) {

      await fetchFaces()
      // Populate condition fields
      if (album.condition.time_range) {
          form.timeRange = [
              album.condition.time_range.start || '',
              album.condition.time_range.end || ''
          ]
      }
      if (album.condition.locations) {
          form.locations = album.condition.locations.map((l: any) => {
             const parts = [l.province, l.city, l.district].filter(Boolean)
             const label = parts.join('')
             return {
                 province: l.province || '',
                 city: l.city || '',
                 district: l.district || '',
                 _id: label
             }
          })
          // Pre-populate options
          locationOptions.value = form.locations.map(l => ({
              label: l._id!,
              value: l
          }))
      }
      if (album.condition.people) {
          form.people = album.condition.people
      }
      if (album.condition.folders) {
          form.folders = album.condition.folders
      }
  }

  showModal.value = true
}

const closeModal = () => {
  showModal.value = false
}

const submitForm = async () => {
  if (!form.name.trim()) return
  loading.value = true
  try {
    const payload: CreateAlbumDto = {
        name: form.name,
        description: form.description,
        type: form.type,
        threshold: form.type === 'smart' ? form.threshold : undefined
    }

    if (form.type === 'conditional') {
        payload.condition = {
            time_range: form.timeRange && form.timeRange.length === 2 && (form.timeRange[0] || form.timeRange[1]) ? {
                start: form.timeRange[0] || undefined,
                end: form.timeRange[1] || undefined
            } : undefined,
            locations: form.locations.filter(l => l.province || l.city || l.district).map(l => ({
                province: l.province || undefined,
                city: l.city || undefined,
                district: l.district || undefined
            })),
            people: form.people.length > 0 ? form.people : undefined,
            folders: form.folders.length > 0 ? form.folders : undefined
        }
    }

    if (isEditing.value && currentAlbumId.value) {
      await albumService.updateAlbum(currentAlbumId.value, payload)
    } else {
      await albumService.createAlbum(payload)
    }
    
    await store.fetchAlbums()
    closeModal()
    ElMessage.success(isEditing.value ? '相册更新成功' : '相册创建成功')
    // 500ms 之后再次查询数据
    setTimeout(() => {
      store.fetchAlbums()
    }, 500)
  } catch (error) {
    console.error("Operation failed", error)
    ElMessage.error("操作失败")
  } finally {
    loading.value = false
  }
}

const confirmDelete = async (album: Album) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除相册 "${album.title}" 吗？`,
      '删除相册',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    await store.deleteAlbum(album.id)
    ElMessage.success('相册已删除')
  } catch (error) {
    if (error !== 'cancel') {
      console.error("Delete failed", error)
      ElMessage.error("删除失败")
    }
  }
}

onMounted(async () => {
  await store.fetchAlbums()
})

</script>
