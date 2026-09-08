<template>
  <div class="mx-auto w-full max-w-[1600px] px-3 pb-6 pt-4 sm:px-5 sm:py-6 lg:px-8">
    <!-- Header -->
    <div class="mb-5 flex items-center justify-between gap-3 sm:mb-8">
      <div class="min-w-0">
        <h1 class="text-2xl font-bold tracking-tight text-gray-900 dark:text-white">我的相册</h1>
        <p class="mt-0.5 text-sm text-gray-500 dark:text-gray-400 md:hidden">整理照片，重温每段回忆</p>
      </div>
      <div class="hidden flex-wrap justify-end gap-2 md:flex">
        <button type="button" class="flex items-center gap-2 rounded-lg border border-primary-500 px-3 py-2 text-sm text-primary-600 transition-colors hover:bg-primary-500/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="startTravelAlbum">
          <WandSparkles class="h-4 w-4" /><span>AI 整理旅行</span>
        </button>
        <button type="button" class="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800" @click="startAlbumDoctor">
          <Stethoscope class="h-4 w-4" /><span>AI 相册体检</span>
        </button>
        <button type="button" class="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800" @click="startMemoryDetective">
          <SearchCheck class="h-4 w-4" /><span>回忆侦探</span>
        </button>
        <button type="button" class="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800" @click="router.push('/agent/actions')">
          <History class="h-4 w-4" /><span>操作记录</span>
        </button>
      </div>
      <el-dropdown trigger="click" @command="openCreateModal">
        <button 
          type="button"
          class="flex shrink-0 items-center gap-1.5 rounded-xl bg-primary-500 px-3 py-2.5 text-sm font-medium text-white shadow-lg shadow-primary-500/20 transition-colors hover:bg-primary-600 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 sm:px-4"
        >
          <Plus class="h-4 w-4 sm:h-5 sm:w-5" />
          <span class="hidden sm:inline">新建相册</span>
          <span class="sm:hidden">新建</span>
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

    <!-- Mobile quick actions -->
    <div class="-mx-3 mb-7 snap-x snap-mandatory overflow-x-auto px-3 pb-1 md:hidden" aria-label="相册快捷工具">
      <div class="flex w-max min-w-full gap-2.5">
        <button type="button" class="mobile-tool-card" @click="startTravelAlbum">
          <span class="mobile-tool-icon bg-primary-500/10 text-primary-600 dark:text-primary-400"><WandSparkles class="h-5 w-5" /></span>
          <span><span class="mobile-tool-title">AI 整理旅行</span><span class="mobile-tool-subtitle">发现旅行故事</span></span>
        </button>
        <button type="button" class="mobile-tool-card" @click="startAlbumDoctor">
          <span class="mobile-tool-icon bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"><Stethoscope class="h-5 w-5" /></span>
          <span><span class="mobile-tool-title">相册体检</span><span class="mobile-tool-subtitle">检查照片状态</span></span>
        </button>
        <button type="button" class="mobile-tool-card" @click="startMemoryDetective">
          <span class="mobile-tool-icon bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"><SearchCheck class="h-5 w-5" /></span>
          <span><span class="mobile-tool-title">回忆侦探</span><span class="mobile-tool-subtitle">找回模糊记忆</span></span>
        </button>
        <button type="button" class="mobile-tool-card" @click="router.push('/agent/actions')">
          <span class="mobile-tool-icon bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"><History class="h-5 w-5" /></span>
          <span><span class="mobile-tool-title">操作记录</span><span class="mobile-tool-subtitle">查看整理历史</span></span>
        </button>
      </div>
    </div>

    <!-- Smart Albums Section -->
    <section class="mb-8 sm:mb-10">
      <h2 class="mb-3 flex items-center gap-2 text-base font-semibold text-gray-800 dark:text-gray-100 sm:mb-4 sm:text-lg">
        <Sparkles class="w-5 h-5 text-yellow-500" />
        智能相册
      </h2>
      <div class="grid grid-cols-1 gap-2.5 sm:grid-cols-3 sm:gap-5 lg:grid-cols-6 lg:gap-6">
        <div 
          v-for="album in smartAlbums" 
          :key="album.id"
          class="group relative flex cursor-pointer items-center gap-3 rounded-2xl border border-gray-200 bg-white p-3 shadow-sm transition-all duration-300 hover:border-gray-300 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-gray-800 dark:bg-gray-900 dark:hover:border-gray-700 sm:block sm:border-0 sm:bg-transparent sm:p-0 sm:shadow-none sm:dark:bg-transparent"
          role="button"
          tabindex="0"
          :aria-label="`打开${album.title}`"
          @click="navigateToSmartAlbum(album)"
          @keydown.enter="navigateToSmartAlbum(album)"
          @keydown.space.prevent="navigateToSmartAlbum(album)"
        >
          <!-- Cover -->
          <div class="relative flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-gray-100 bg-gradient-to-br from-gray-100 to-gray-200 shadow-sm transition-all duration-300 group-hover:shadow-md dark:border-gray-800 dark:from-gray-800 dark:to-gray-900 sm:mb-3 sm:aspect-square sm:h-auto sm:w-full">
             <!-- Icon/Cover Content -->
             <component :is="album.icon" class="h-6 w-6 text-gray-400 transition-colors duration-300 group-hover:text-primary-500 sm:h-12 sm:w-12" stroke-width="1.5" />
             
             <!-- Overlay -->
             <div class="absolute inset-0 bg-black/0 group-hover:bg-black/5 transition-colors"></div>
          </div>
          <!-- Info -->
          <div class="min-w-0 flex-1 sm:mt-2">
             <h3 class="truncate font-semibold text-gray-900 dark:text-white sm:font-bold">{{ album.title }}</h3>
             <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{{ album.description }}</p>
          </div>
          <ChevronRight class="h-5 w-5 shrink-0 text-gray-300 dark:text-gray-600 sm:hidden" />
        </div>
      </div>
    </section>

    <!-- Custom Albums Section -->
    <section>
      <h2 class="mb-3 flex items-center gap-2 text-base font-semibold text-gray-800 dark:text-gray-100 sm:mb-4 sm:text-lg">
        <FolderHeart class="w-5 h-5 text-primary-500" />
        自定义相册
      </h2>
      
      <div v-if="store.allAlbums.length > 0" class="grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-4 sm:gap-5 lg:grid-cols-6 lg:gap-6 xl:grid-cols-8">
        <div
          v-for="album in store.allAlbums"
          :key="album.id"
          class="group relative cursor-pointer animate-in rounded-2xl fade-in slide-in-from-bottom-4 duration-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
          role="button"
          tabindex="0"
          :aria-label="`打开相册 ${album.title}`"
          @click="navigateToAlbum(album.id)"
          @keydown.enter="navigateToAlbum(album.id)"
          @keydown.space.prevent="navigateToAlbum(album.id)"
        >
          <!-- Cover -->
          <div class="relative mb-2.5 aspect-square overflow-hidden rounded-2xl border border-gray-100 bg-gray-100 shadow-sm transition-all duration-300 group-hover:shadow-md dark:border-gray-800 dark:bg-gray-800 sm:mb-3 sm:rounded-xl">
            <img
              :src="album.cover.thumbnail"
              :alt="`${album.title}的封面`"
              class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
              loading="lazy"
            />
            <!-- Overlay -->
            <div class="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors"></div>
            <!-- Type Badge -->
            <div class="absolute left-2 top-2 flex gap-1">
               <span v-if="album.type === 'smart'" class="bg-primary-600/90 backdrop-blur-sm text-white text-xs px-2 py-0.5 rounded-full flex items-center gap-1">
                 <Sparkles class="w-3 h-3 text-white" /> 智能
               </span>
               <span v-if="album.type === 'conditional'" class="bg-primary-500/90 backdrop-blur-sm text-white text-xs px-2 py-0.5 rounded-full flex items-center gap-1">
                 <Filter class="w-3 h-3 text-white" /> 条件
               </span>
            </div>

            <!-- Actions (Only for User Albums) -->
            <div v-if="album.type !== 'system'" class="absolute right-2 top-2 z-10 flex gap-1.5 opacity-100 transition-opacity duration-200 md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100">
              <button
                type="button"
                @click.stop="openEditModal(album)"
                class="flex h-9 w-9 items-center justify-center rounded-full bg-white/90 text-gray-600 shadow-sm backdrop-blur-sm hover:text-primary-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:bg-gray-800/90 dark:text-gray-300"
                title="编辑"
                :aria-label="`编辑相册 ${album.title}`"
              >
                <Edit2 class="w-4 h-4" />
              </button>
              <button
                type="button"
                @click.stop="confirmDelete(album)"
                class="flex h-9 w-9 items-center justify-center rounded-full bg-white/90 text-gray-600 shadow-sm backdrop-blur-sm hover:text-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:bg-gray-800/90 dark:text-gray-300"
                title="删除"
                :aria-label="`删除相册 ${album.title}`"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>
          <!-- Info -->
          <div class="px-0.5">
            <h3 class="truncate text-sm font-semibold text-gray-900 dark:text-white sm:text-base sm:font-bold">{{ album.title }}</h3>
            <div class="flex justify-between items-center mt-1">
              <p class="text-xs text-gray-500 dark:text-gray-400">{{ album.count }} 个项目</p>
              <!-- <p class="text-xs text-gray-400">{{ formatDate(album.createdAt) }}</p> -->
            </div>
          </div>
        </div>
      </div>
      
      <!-- Empty State for Custom Albums -->
      <div v-else class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-gray-200 bg-gray-50 px-4 py-12 text-center text-gray-400 dark:border-gray-800 dark:bg-gray-800/50 sm:py-20">
        <div class="w-16 h-16 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center mb-4">
          <FolderOpen class="w-8 h-8 text-gray-300 dark:text-gray-600" />
        </div>
        <p>暂无自定义相册</p>
        <button type="button" @click="openCreateModal('user')" class="mt-4 rounded-lg px-3 py-2 text-primary-600 hover:bg-primary-500/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2">创建第一个相册</button>
      </div>
    </section>

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
import { Plus, Sparkles, Edit2, Trash2, Users, MapPin, FolderHeart, FolderOpen, Tag, Filter, History, SearchCheck, Stethoscope, WandSparkles, ChevronRight } from 'lucide-vue-next'
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
  uiStore.openAgentWithPrompt('请加载 album-doctor Skill，对我的整个照片库做一次只读体检。按严重程度总结缺少时间、地点、AI 描述、文件指纹、未归档照片、完全重复照片和相册结构异常；只展示少量证据样本与建议。对于计数和封面问题可生成结构修复计划；对于缺失 AI 描述或文件指纹可生成带进度的后台计划；对于满足保守证据规则的缺失时间或地点，可展示逐张证据并生成可撤销计划。都先等待我表达修复意图，不要删除、移动或重命名原始照片，也不要替我确认或执行任何计划。', true)
}

const startMemoryDetective = () => {
  uiStore.openAgentWithPrompt('请加载 memory-detective Skill，作为回忆侦探帮我找回一段记不清的经历。先问我一个最有区分度的问题，引导我提供大概时间、地点、同行人、看到的文字或画面等线索；然后融合这些证据给出少量候选事件和照片，不要把推断当成事实，也不要修改任何照片。', true)
}

const { width } = useWindowSize()
const dialogWidth = computed(() => width.value < 640 ? 'calc(100% - 24px)' : '500px')
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

<style scoped>
.mobile-tool-card {
  @apply flex min-w-[174px] snap-start items-center gap-3 rounded-2xl border border-gray-200 bg-white px-3 py-3 text-left shadow-sm transition-colors hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-900 dark:hover:bg-gray-800;
}

.mobile-tool-card:hover {
  border-color: rgba(var(--theme-rgb), 0.35);
}

.mobile-tool-card:focus-visible {
  outline: 2px solid var(--theme-primary);
  outline-offset: 2px;
}

.mobile-tool-icon {
  @apply flex h-10 w-10 shrink-0 items-center justify-center rounded-xl;
}

.mobile-tool-title {
  @apply block whitespace-nowrap text-sm font-semibold text-gray-800 dark:text-gray-100;
}

.mobile-tool-subtitle {
  @apply mt-0.5 block whitespace-nowrap text-[11px] text-gray-500 dark:text-gray-400;
}
</style>
