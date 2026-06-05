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
            placeholder="搜索..."
            class="w-full pl-9 pr-7 py-2 text-sm bg-slate-100 dark:bg-slate-800 border border-transparent dark:border-slate-700 rounded-lg focus:outline-none focus:border-primary-500 focus:bg-white dark:focus:bg-slate-900 text-slate-700 dark:text-slate-200 transition-colors"
          />
          <button 
            v-if="searchText"
            @click="clearSearch"
            class="absolute bg-transparent right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
          >
            <X class="w-3 h-3" />
          </button>

          <!-- 搜索建议下拉框 -->
          <div 
            v-if="showDropdown && (suggestions.length > 0 || searchText)" 
            class="absolute top-full left-0 w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-lg mt-2 overflow-hidden z-50 max-h-60 overflow-y-auto custom-scrollbar"
          >
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
      <!-- 预留的自定义选项区块占位 -->
      <div v-if="!isCollapsed" class="mt-8 px-3">
        <div class="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-2">
          自定义
        </div>
        <div class="p-3 border border-dashed border-slate-300 dark:border-slate-700 rounded-lg text-center text-sm text-slate-500">
          自定义选项区(占位)
        </div>
      </div>
    </nav>

    <!-- 底部设置与回收站入口 -->
    <div class="p-2 border-t border-slate-200 dark:border-slate-800 shrink-0 space-y-1">
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
  Sparkles
} from 'lucide-vue-next'
import { useDebounceFn } from '@vueuse/core'
import { usePhotoStore } from '@/stores/photoStore'
import searchService, { type SearchSuggestion } from '@/api/search'

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
  if (searchText.value) {
    fetchSuggestions(searchText.value)
  }
}

const handleSearch = () => {
  if (searchText.value.trim()) {
    showDropdown.value = false
    suggestions.value = []
    router.push({ path: '/search', query: { q: searchText.value } })
    searchInputRef.value?.blur()
  }
}

const clearSearch = () => {
  searchText.value = ''
  suggestions.value = []
  store.loadPhotos(true)
  searchInputRef.value?.focus()
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
    'scene': '景区'
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
    'scene': Mountain
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
