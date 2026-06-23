<template>
  <div class="fixed inset-0 bg-white dark:bg-gray-950 z-[1000] flex flex-col animate-in slide-in-from-bottom duration-300">
    <!-- Header with Search Input -->
    <div class="flex items-center gap-2 p-4 border-b border-gray-100 dark:border-gray-800">
      <button 
        @click="goBack" 
        class="p-2 -ml-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 dark:text-gray-300 dark:bg-gray-800"
      >
        <ArrowLeft class="w-6 h-6" />
      </button>
      
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
  Calendar
} from 'lucide-vue-next'
import { useDebounceFn } from '@vueuse/core'
import searchService, { type SearchSuggestion } from '@/api/search'
import { parseDateRange } from '@/utils/date'

const router = useRouter()
const searchText = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)
const suggestions = ref<SearchSuggestion[]>([])

onMounted(() => {
  searchInputRef.value?.focus()
})

const goBack = () => {
  router.back()
}

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