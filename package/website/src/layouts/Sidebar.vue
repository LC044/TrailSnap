<template>
  <aside
    :class="[
      'flex flex-col transition-all duration-300 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 shrink-0 z-40',
      isCollapsed ? 'w-16' : 'w-64'
    ]"
  >
    <!-- 顶部 Logo 区域 (可折叠) -->
    <div class="h-14 flex items-center justify-between px-4 border-b border-slate-200 dark:border-slate-800 shrink-0">
      <div class="flex items-center overflow-hidden whitespace-nowrap">
        <img src="@/assets/logo.svg" alt="Logo" class="w-8 h-8 shrink-0" />
        <transition name="fade">
          <h1 v-if="!isCollapsed" class="ml-3 font-bold text-lg text-slate-800 dark:text-slate-100">
            行影集
          </h1>
        </transition>
      </div>
      <!-- 折叠按钮 (仅在非手机端显示？也可以手机端隐藏侧边栏) -->
      <button
        @click="toggleCollapse"
        :title="isCollapsed ? '展开侧边栏' : '折叠侧边栏'"
        class="bg-transparent p-1 rounded-md text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors hidden md:block"
      >
        <Menu v-if="isCollapsed" class="w-5 h-5" />
        <ChevronLeft v-else class="w-5 h-5" />
      </button>
    </div>

    <!-- 主要导航菜单 -->
    <nav class="flex-1 overflow-y-auto py-4 px-2 space-y-1 custom-scrollbar">
      <!-- 搜索功能 -->
      <div class="mb-2">
        <div v-if="!isCollapsed" class="relative">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            ref="searchInputRef"
            v-model="searchText"
            @input="onInput"
            @keydown.enter="handleSearch"
            @blur="handleBlur"
            @focus="handleFocus"
            type="text"
            placeholder="搜索或描述画面..."
            class="w-full pl-9 pr-7 py-2 text-sm bg-slate-100 dark:bg-slate-800 border border-transparent dark:border-slate-700 rounded-lg focus:outline-none focus:border-primary-500 focus:bg-white dark:focus:bg-slate-900 text-slate-700 dark:text-slate-200 transition-colors"
          />
          <button
            v-if="searchText"
            @click="clearSearch"
            class="absolute bg-transparent right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
          >
            <X class="w-3 h-3" />
          </button>
          <button
            v-else
            @click="searchInputRef?.focus()"
            class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-primary-500/50 hover:text-primary-500 transition-colors"
            title="AI 语义搜索"
          >
            <Sparkles class="w-3.5 h-3.5" />
          </button>

          <!-- 搜索建议下拉框 -->
          <div
            v-if="showDropdown"
            class="absolute top-full left-0 w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-lg mt-2 overflow-hidden z-50 max-h-60 overflow-y-auto custom-scrollbar"
          >
            <!-- 空输入时：AI 搜索提示 -->
            <div
              v-if="!searchText && suggestions.length === 0"
              class="px-4 py-3"
            >
              <div class="flex items-center gap-2 text-primary-500 mb-2">
                <Sparkles class="w-4 h-4" />
                <span class="text-sm font-medium">AI 语义搜索</span>
              </div>
              <p class="text-xs text-slate-500 dark:text-slate-400">描述画面内容，即可找到对应照片</p>
              <div class="flex flex-wrap gap-1.5 mt-2">
                <span
                  v-for="tag in searchHints"
                  :key="tag"
                  @mousedown.prevent="quickSearch(tag)"
                  class="px-2 py-0.5 text-xs bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-full cursor-pointer hover:bg-primary-50 hover:text-primary-600 dark:hover:bg-primary-900/20 dark:hover:text-primary-400 transition-colors"
                >{{ tag }}</span>
              </div>
            </div>

            <!-- 语义搜索选项 -->
            <div
              v-if="searchText"
              @mousedown.prevent="handleSearch"
              class="px-4 py-2 hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer text-sm border-b last:border-0 border-slate-100 dark:border-slate-700 flex items-center gap-2"
            >
              <Sparkles class="w-4 h-4 text-primary-500" />
              <div class="flex flex-col">
                <span class="text-slate-800 dark:text-slate-200 font-medium">画面识别: "{{ searchText }}"</span>
                <span class="text-xs text-slate-500">使用AI进行语义搜索</span>
              </div>
            </div>

            <!-- 其他建议 -->
            <div
              v-for="(item, index) in suggestions"
              :key="index"
              @mousedown.prevent="selectSuggestion(item)"
              class="px-4 py-2 hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer text-sm border-b last:border-0 border-slate-100 dark:border-slate-700 flex items-center gap-2"
            >
              <component :is="getIcon(item.type)" class="w-4 h-4 text-slate-500 dark:text-slate-400" />

              <div class="flex-1 min-w-0">
                 <div class="flex items-center justify-between">
                   <span class="text-slate-800 dark:text-slate-200 font-medium truncate">
                     {{ item.type === 'ocr' ? item.label : item.value }}
                   </span>
                   <span class="text-xs text-slate-500 dark:text-slate-400 ml-2 whitespace-nowrap bg-slate-100 dark:bg-slate-700 px-1.5 py-0.5 rounded">{{ getLabel(item.type) }}</span>
                 </div>
              </div>
            </div>
          </div>
        </div>
        <button
          v-else
          @click="openSearch"
          class="flex bg-transparent items-center px-3 py-2.5 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group relative w-full"
          title="搜索"
        >
          <Search class="w-5 h-5 shrink-0" />
        </button>
      </div>

      <RouterLink
        v-for="item in navLinks"
        :key="item.href"
        :to="item.href"
        :title="isCollapsed ? item.label : undefined"
        class="flex items-center px-3 py-2.5 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group relative"
        :class="{ 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 font-medium': isActiveRoute(item.href) }"
      >
        <component :is="item.icon" class="w-5 h-5 shrink-0" />
        <transition name="fade">
          <span v-if="!isCollapsed" class="ml-3 truncate">{{ item.label }}</span>
        </transition>
      </RouterLink>

      <div class="my-4 border-t border-slate-200 dark:border-slate-800"></div>

      <!-- 更多工具 -->
      <RouterLink
        v-for="item in moreLinks"
        :key="item.href"
        :to="item.href"
        :title="isCollapsed ? item.label : undefined"
        class="flex items-center px-3 py-2.5 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group"
        :class="{ 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 font-medium': isActiveRoute(item.href) }"
      >
        <component :is="item.icon" class="w-5 h-5 shrink-0" />
        <transition name="fade">
          <span v-if="!isCollapsed" class="ml-3 truncate">{{ item.label }}</span>
        </transition>
      </RouterLink>
      <div class="my-4 border-t border-slate-200 dark:border-slate-800"></div>
      <!-- 快捷访问 -->
      <div v-if="!isCollapsed" class="px-1">
        <div class="flex items-center justify-between px-2 mb-1">
          <span class="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">快捷访问</span>
          <button
            @click="openAddDialog"
            class="p-0.5 text-slate-400 hover:text-primary-500 transition-colors"
            title="添加快捷导航"
          >
            <Plus class="w-3.5 h-3.5" />
          </button>
        </div>
        <div v-if="navItemsList.length > 0" class="space-y-0.5">
          <div
            v-for="item in navItemsList"
            :key="`${item.entity_type}-${item.entity_id}`"
            class="flex items-center px-2 py-1.5 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors group cursor-pointer"
            :class="{ 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 font-medium': isActiveRoute(item.route_path) }"
            @click="router.push(item.route_path)"
          >
            <div class="w-7 h-7 rounded-md overflow-hidden shrink-0 bg-slate-200 dark:bg-slate-700 flex items-center justify-center">
              <img v-if="item.cover_photo_id" :src="getThumbnailUrl(item)" class="w-full h-full object-cover" loading="lazy" />
              <component v-else :is="getNavIcon(item.entity_type)" class="w-3.5 h-3.5 text-slate-400" />
            </div>
            <span class="ml-2 text-sm truncate flex-1">{{ item.name }}</span>
            <button
              @click.stop="removeNavItem(item.entity_type, item.entity_id)"
              class="opacity-0 group-hover:opacity-100 p-0.5 text-slate-400 hover:text-red-500 transition-all"
              title="移除"
            >
              <X class="w-3 h-3" />
            </button>
          </div>
        </div>
        <div v-else class="px-2 py-3 text-center">
          <button
            @click="openAddDialog"
            class="text-xs text-slate-400 hover:text-primary-500 transition-colors"
          >
            点击 + 添加常用项
          </button>
        </div>
      </div>
      <div v-else class="px-2 flex justify-center">
        <button
          @click="openAddDialogFromCollapsed"
          class="flex items-center justify-center w-full py-2.5 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title="快捷访问"
        >
          <Bookmark class="w-5 h-5" />
        </button>
      </div>
    </nav>

    <!-- 底部设置与回收站入口 -->
    <div class="p-2 border-t border-slate-200 dark:border-slate-800 shrink-0 flex flex-col space-y-1">
      <SidebarTaskManager :is-collapsed="isCollapsed" />

      <NotificationBell variant="row" :collapsed="isCollapsed" />

      <RouterLink
        to="/swipe-filter"
        :title="isCollapsed ? '断舍离' : undefined"
        class="flex items-center px-3 py-2.5 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group"
        :class="{ 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 font-medium': isActiveRoute('/swipe-filter') }"
      >
        <Layers class="w-5 h-5 shrink-0" />
        <transition name="fade">
          <span v-if="!isCollapsed" class="ml-3 truncate">断舍离</span>
        </transition>
      </RouterLink>

      <RouterLink
        to="/recycle-bin"
        :title="isCollapsed ? '回收站' : undefined"
        class="flex items-center px-3 py-2.5 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group"
        :class="{ 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 font-medium': isActiveRoute('/recycle-bin') }"
      >
        <Trash2 class="w-5 h-5 shrink-0" />
        <transition name="fade">
          <span v-if="!isCollapsed" class="ml-3 truncate">回收站</span>
        </transition>
      </RouterLink>
      
      <RouterLink
        to="/settings"
        :title="isCollapsed ? '设置' : undefined"
        class="flex items-center px-3 py-2.5 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group"
        :class="{ 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 font-medium': isActiveRoute('/settings') }"
      >
        <Settings class="w-5 h-5 shrink-0" />
        <transition name="fade">
          <span v-if="!isCollapsed" class="ml-3 truncate">设置</span>
        </transition>
      </RouterLink>
    </div>

    <!-- 添加快捷导航对话框 -->
    <NavAddDialog
      ref="addDialogRef"
      v-model:visible="showAddNavDialog"
    />
  </aside>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Home,
  Image as ImageIcon,
  Images,
  Ticket,
  Wrench,
  Settings,
  ChevronLeft,
  Menu,
  Trash2,
  Search,
  X,
  User,
  MapPin,
  Type,
  Folder,
  FileText,
  Tag,
  Mountain,
  Sparkles,
  Plus,
  Bookmark,
  Calendar,
  Layers
} from 'lucide-vue-next'
import { useDebounceFn } from '@vueuse/core'
import { usePhotoStore } from '@/stores/photoStore'
import searchService, { type SearchSuggestion } from '@/api/search'
import { injectNavItems, type ResolvedNavItem } from '@/composables/useNavItems'
import NavAddDialog from '@/components/NavAddDialog.vue'
import SidebarTaskManager from '@/components/SidebarTaskManager.vue'
import NotificationBell from '@/components/NotificationBell.vue'
import { parseDateRange } from '@/utils/date'

const route = useRoute()
const router = useRouter()
const store = usePhotoStore()

// 路由激活状态判断：完全匹配，避免首页（/）一直处于激活状态
const isActiveRoute = (path: string) => {
  if (path === '/') {
    return route.path === '/'
  }
  return route.path.startsWith(path)
}

const isCollapsed = ref(false)

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

const navLinks = [
  { label: '首页', href: '/', icon: Home },
  { label: '照片', href: '/photos', icon: ImageIcon },
  { label: '相册', href: '/album', icon: Images },
]

const moreLinks = [
  { label: '车票', href: '/ticket', icon: Ticket },
  { label: '工具箱', href: '/toolbox', icon: Wrench },
]

// 搜索相关状态和逻辑
const searchText = ref('')
const showDropdown = ref(false)
const searchInputRef = ref<HTMLInputElement | null>(null)
const suggestions = ref<SearchSuggestion[]>([])
const searchHints = ['海边日落', '猫咪', '雪景', '花园', '城市夜景']

// AI 微服务预热标记（会话级，仅触发一次，避免后续真正搜索时模型冷启动延迟）
let aiWarmupTriggered = false
const triggerAiWarmup = () => {
  if (aiWarmupTriggered) return
  aiWarmupTriggered = true
  // fire-and-forget：发送一次极简语义搜索请求，激活后端的 embedding 调用链以预热 AI 微服务
  searchService
    .searchByText({ text: 'warmup', limit: 1 })
    .catch((e) => {
      // 预热失败不影响后续使用，重置标记以便下次 focus 再试一次
      aiWarmupTriggered = false
      console.warn('AI warmup failed:', e)
    })
}

// 自定义导航项
const { items: navItemsList, removeItem: removeNavItem, addItem: addNavItem } = injectNavItems()
const showAddNavDialog = ref(false)
const addDialogRef = ref<InstanceType<typeof NavAddDialog> | null>(null)

const openAddDialog = () => {
  showAddNavDialog.value = true
  nextTick(() => {
    addDialogRef.value?.fetchData()
  })
}

const openAddDialogFromCollapsed = () => {
  isCollapsed.value = false
  nextTick(() => {
    openAddDialog()
  })
}

const getNavIcon = (entityType: string) => {
  const map: Record<string, any> = {
    'album': Images,
    'person': User,
    'location': MapPin,
    'classification': Tag
  }
  return map[entityType] || Bookmark
}

const getThumbnailUrl = (item: ResolvedNavItem) => {
  if (item.entity_type === 'person' && item.cover_photo_id) {
    return `/api/medias/${item.cover_photo_id}/thumbnail?size=medium`
  }
  if (item.cover_photo_id) {
    return `/api/medias/${item.cover_photo_id}/thumbnail`
  }
  return ''
}

watch(() => store.currentContext, (ctx) => {
  if (ctx.type === 'search' && ctx.id) {
    searchText.value = ctx.id
  } else if (ctx.type !== 'search') {
    searchText.value = ''
    suggestions.value = []
  }
})

const openSearch = () => {
  isCollapsed.value = false
  nextTick(() => {
    if (searchInputRef.value) {
      searchInputRef.value.focus()
    }
  })
}

const handleBlur = () => {
  setTimeout(() => {
    showDropdown.value = false
    suggestions.value = []
  }, 200)
}

const handleFocus = () => {
  showDropdown.value = true
  // 点击搜索框时预热 AI 微服务，避免后续真正搜索时模型冷启动造成卡顿
  triggerAiWarmup()
  if (searchText.value) {
    fetchSuggestions(searchText.value)
  }
}

const handleSearch = () => {
  if (searchText.value.trim()) {
    showDropdown.value = false
    suggestions.value = []
    
    const dateRange = parseDateRange(searchText.value)
    if (dateRange) {
      router.push({ path: '/search', query: { q: searchText.value, type: 'date' } })
    } else {
      router.push({ path: '/search', query: { q: searchText.value } })
    }
    
    searchInputRef.value?.blur()
  }
}

const clearSearch = () => {
  searchText.value = ''
  suggestions.value = []
  store.loadPhotos(true)
  searchInputRef.value?.focus()
}

const quickSearch = (text: string) => {
  searchText.value = text
  handleSearch()
}

const fetchSuggestions = useDebounceFn(async (q: string) => {
  if (!q.trim()) {
    suggestions.value = []
    return
  }
  try {
    const res = await searchService.getSuggestions(q)
    const processedSuggestions: SearchSuggestion[] = []
    let hasOcr = false
    
    for (const item of res) {
      if (item.type === 'ocr') {
        hasOcr = true
      } else {
        processedSuggestions.push(item)
      }
    }
    
    if (hasOcr) {
      processedSuggestions.push({
        type: 'ocr',
        value: q,
        label: `图片中包含文字：${q}`
      } as SearchSuggestion)
    }

    const dateRange = parseDateRange(q)
    if (dateRange) {
      processedSuggestions.unshift({
        type: 'date',
        value: q,
        label: `按日期搜索：${dateRange.label}`
      } as SearchSuggestion)
    }
    
    suggestions.value = processedSuggestions
  } catch (e) {
    console.error("Failed to fetch suggestions", e)
  }
}, 300)

const onInput = () => {
  showDropdown.value = true
  fetchSuggestions(searchText.value)
}

const selectSuggestion = (item: SearchSuggestion) => {
  searchText.value = item.value
  showDropdown.value = false
  suggestions.value = []
  router.push({ 
    path: '/search', 
    query: { 
      q: item.value, 
      type: item.type 
    } 
  })
  searchInputRef.value?.blur()
}

const getLabel = (type: string) => {
  const map: Record<string, string> = {
    'person': '人物',
    'location': '地点',
    'ocr': '文字',
    'album': '相册',
    'folder': '文件夹',
    'filename': '文件',
    'tag': '标签',
    'scene': '景区',
    'date': '日期'
  }
  return map[type] || type
}

const getIcon = (type: string) => {
  const map: Record<string, any> = {
    'person': User,
    'location': MapPin,
    'ocr': Type,
    'album': Images,
    'folder': Folder,
    'filename': FileText,
    'tag': Tag,
    'scene': Mountain,
    'date': Calendar
  }
  return map[type] || Search
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, width 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  width: 0;
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: #cbd5e1;
  border-radius: 4px;
}
.dark .custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: #475569;
}
</style>
