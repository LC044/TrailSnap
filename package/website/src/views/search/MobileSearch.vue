<template>
  <div class="h-full bg-white dark:bg-gray-950 flex flex-col animate-in slide-in-from-bottom duration-300">
    <div class="flex items-center gap-3 border-b border-gray-100 p-3 dark:border-gray-800">
      <IconButton label="返回" @click="goBack">
        <ArrowLeft class="w-6 h-6" />
      </IconButton>
      <div class="grid flex-1 grid-cols-2 rounded-xl bg-gray-100 p-1 dark:bg-gray-900" aria-label="搜索模式">
        <button
          v-for="mode in modes"
          :key="mode.value"
          type="button"
          class="flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          :class="activeMode === mode.value ? 'bg-white text-primary-600 shadow-sm dark:bg-gray-800 dark:text-primary-400' : 'text-gray-500 dark:text-gray-400'"
          @click="activeMode = mode.value"
        >
          <component :is="mode.icon" class="h-4 w-4" />{{ mode.label }}
        </button>
      </div>
    </div>

    <template v-if="activeMode === 'search'">
    <!-- Header with Search Input -->
    <div class="flex items-center gap-2 p-4 border-b border-gray-100 dark:border-gray-800">
      <div class="flex-1 relative">
        <input
          ref="searchInputRef"
          v-model="searchText"
          @input="onInput"
          @keydown.enter="handleSearch"
          type="text"
          placeholder="搜索照片、地点、人物..."
          class="w-full pl-10 pr-10 py-2.5 text-base bg-gray-100 dark:bg-gray-900 border-none rounded-xl focus:ring-2 focus:ring-primary-500 text-gray-900 dark:text-white"
        />
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
        <button 
          v-if="searchText"
          @click="clearSearch"
          class="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-gray-400"
        >
          <X class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- Suggestions Area -->
    <div class="flex-1 overflow-y-auto bg-gray-50/50 dark:bg-gray-950/50">
      <div v-if="searchText && suggestions.length === 0" class="p-8 text-center">
        <div 
          @click="handleSearch"
          class="inline-flex flex-col items-center gap-2 text-primary-500 cursor-pointer"
        >
          <Sparkles class="w-8 h-8" />
          <span class="text-sm font-medium">使用AI进行语义搜索: "{{ searchText }}"</span>
        </div>
      </div>

      <div v-if="searchText" class="flex flex-col pb-20">
        <!-- Semantic Search Option -->
        <div 
          @click="handleSearch"
          class="px-4 py-4 flex items-center gap-3 bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800 active:bg-gray-100 dark:active:bg-gray-800 transition-colors"
        >
          <div class="w-10 h-10 rounded-full bg-primary-50 dark:bg-primary-900/30 flex items-center justify-center text-primary-500">
            <Sparkles class="w-5 h-5" />
          </div>
          <div class="flex flex-col flex-1">
            <span class="text-gray-900 dark:text-white font-medium">画面识别: "{{ searchText }}"</span>
            <span class="text-xs text-gray-500">使用AI进行语义搜索</span>
          </div>
          <ChevronRight class="w-5 h-5 text-gray-300" />
        </div>

        <!-- Other Suggestions -->
        <div 
          v-for="(item, index) in suggestions" 
          :key="index" 
          @click="selectSuggestion(item)"
          class="px-4 py-4 flex items-center gap-3 bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800 active:bg-gray-100 dark:active:bg-gray-800 transition-colors"
        >
          <div class="w-10 h-10 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-gray-500">
            <component :is="getIcon(item.type)" class="w-5 h-5" />
          </div>
          <div class="flex flex-col flex-1">
            <span class="text-gray-900 dark:text-white font-medium">
              {{ item.type === 'ocr' ? item.label : item.value }}
            </span>
            <span class="text-xs text-gray-500">{{ getLabel(item.type) }}</span>
          </div>
          <ChevronRight class="w-5 h-5 text-gray-300" />
        </div>
      </div>

      <!-- Recent Searches or Empty State could go here -->
      <div v-else class="p-12 flex flex-col items-center justify-center text-gray-400">
        <Search class="w-16 h-16 opacity-10 mb-4" />
        <p class="text-sm">开始搜索您的精彩瞬间</p>
      </div>
    </div>
    </template>

    <div v-else class="flex flex-1 flex-col items-center justify-center px-8 pb-20 text-center">
      <div class="mb-5 flex h-20 w-20 items-center justify-center rounded-3xl bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400">
        <Bot class="h-10 w-10" />
      </div>
      <h1 class="text-xl font-bold text-gray-900 dark:text-white">AI 照片助手</h1>
      <p class="mt-2 max-w-sm text-sm leading-6 text-gray-500 dark:text-gray-400">用自然语言查找照片、整理相册，或询问旅程与拍摄统计。</p>
      <button
        type="button"
        class="mt-6 rounded-xl bg-primary-600 px-6 py-3 font-medium text-white shadow-lg shadow-primary-500/20 transition hover:bg-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
        @click="uiStore.openAgent()"
      >
        打开 AI 助手
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { 
  ArrowLeft, 
  Search, 
  X, 
  User, 
  MapPin, 
  Type, 
  Images, 
  Folder, 
  FileText, 
  Tag, 
  Mountain,
  Sparkles,
  ChevronRight,
  Calendar,
  Bot,
} from 'lucide-vue-next'
import { useDebounceFn } from '@vueuse/core'
import searchService, { type SearchSuggestion } from '@/api/search'
import { parseDateRange } from '@/utils/date'
import IconButton from '@/components/ui/IconButton.vue'
import { useAppBack } from '@/composables/useAppBack'
import { useUiStore } from '@/stores/uiStore'

const router = useRouter()
const searchText = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)
const suggestions = ref<SearchSuggestion[]>([])
const uiStore = useUiStore()
const activeMode = ref<'search' | 'agent'>('search')
const modes = [
  { value: 'search' as const, label: '照片搜索', icon: Search },
  { value: 'agent' as const, label: 'AI 助手', icon: Bot },
]

onMounted(() => {
  searchInputRef.value?.focus()
})

const goBack = useAppBack('/')

const clearSearch = () => {
  searchText.value = ''
  suggestions.value = []
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
}, 300);

const onInput = () => {
  fetchSuggestions(searchText.value)
}

const handleSearch = () => {
  if (searchText.value.trim()) {
    const dateRange = parseDateRange(searchText.value)
    if (dateRange) {
      router.push({ path: '/search', query: { q: searchText.value, type: 'date' } })
    } else {
      router.push({ path: '/search', query: { q: searchText.value } })
    }
  }
}

const selectSuggestion = (item: SearchSuggestion) => {
  router.replace({ 
    path: '/search', 
    query: { 
      q: item.value, 
      type: item.type 
    } 
  });
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
  };
  return map[type] || type;
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
  };
  return map[type] || Search;
}
</script>

<style scoped>
.animate-in {
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    transform: translateY(20px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}
</style>
