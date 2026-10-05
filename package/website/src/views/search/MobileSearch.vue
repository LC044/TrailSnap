<template>
  <div class="ts-page-background search-page h-full min-h-0 flex flex-col">
    <header class="ts-page-header shrink-0 px-[var(--ts-page-gutter)] py-2">
      <div class="mb-5 flex items-center gap-3">
        <BackButton label="返回" @click="goBack" />
        <h1 class="ts-page-title flex-1 text-gray-900 dark:text-white">搜索</h1>
        <button class="search-agent-button ts-liquid-glass flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-primary-600 dark:text-primary-400" aria-label="AI 助手" @click="uiStore.openAgent()"><Bot class="h-6 w-6" /></button>
      </div>
      <div class="relative min-w-0">
        <input ref="searchInputRef" v-model="searchText" type="search" aria-label="搜索照片" placeholder="搜索时间、地点、人物、类别…" class="ts-input search-input w-full rounded-full pl-10 pr-11" @input="onInput" @keydown.enter="handleSearch" />
        <Search class="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-500 dark:text-gray-400" />
        <button v-if="searchText" class="ts-icon-button ts-button-ghost absolute right-0 top-1/2 -translate-y-1/2" aria-label="清空搜索" @click="clearSearch"><X class="h-4 w-4" /></button>
      </div>
    </header>
    <!-- Suggestions Area -->
    <div class="flex-1 min-h-0 overflow-y-auto px-[var(--ts-page-gutter)] py-5">
      <div v-if="searchText" class="ts-surface flex flex-col overflow-hidden">
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
            <span class="text-xs text-gray-500 dark:text-gray-400">使用AI进行语义搜索</span>
          </div>
          <ChevronRight class="w-5 h-5 text-gray-300 dark:text-gray-400" />
        </div>

        <!-- Other Suggestions -->
        <div 
          v-for="(item, index) in suggestions" 
          :key="index" 
          @click="selectSuggestion(item)"
          class="px-4 py-4 flex items-center gap-3 bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800 active:bg-gray-100 dark:active:bg-gray-800 transition-colors"
        >
          <div class="w-10 h-10 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-gray-500 dark:text-gray-400">
            <component :is="getIcon(item.type)" class="w-5 h-5" />
          </div>
          <div class="flex flex-col flex-1">
            <span class="text-gray-900 dark:text-white font-medium">
              {{ item.type === 'ocr' ? item.label : item.value }}
            </span>
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ getLabel(item.type) }}</span>
          </div>
          <ChevronRight class="w-5 h-5 text-gray-300 dark:text-gray-400" />
        </div>
      </div>

      <div v-else class="space-y-8">
        <section v-if="showExamples" class="ts-surface rounded-3xl p-4">
          <div class="mb-2 flex items-center justify-between"><h2 class="ts-section-title text-gray-700 dark:text-gray-300">你可以这样搜</h2><IconButton label="隐藏搜索建议" @click="showExamples = false"><X class="h-4 w-4" /></IconButton></div>
          <button v-for="(example, index) in examples" :key="example" class="flex min-h-16 w-full items-center gap-3 text-left text-gray-900 dark:text-white" @click="runExample(example)">
            <div class="h-12 w-12 shrink-0 overflow-hidden rounded-xl bg-gray-100 dark:bg-gray-800">
              <img v-if="exampleCovers[index]?.photo_id" :src="thumbnailUrl(exampleCovers[index]!.photo_id!, 'small')" alt="" class="h-full w-full object-cover" />
              <Search v-else class="m-3 h-6 w-6 text-gray-400 dark:text-gray-500" />
            </div>
            <span class="text-base">{{ example }}</span>
          </button>
        </section>
        <section>
          <div class="mb-3 flex items-center justify-between"><h2 class="ts-section-title text-gray-900 dark:text-white">最近搜索</h2><IconButton v-if="searchStore.history.length" label="清空最近搜索" @click="searchStore.clearHistory()"><Trash2 class="h-5 w-5" /></IconButton></div>
          <div v-if="searchStore.history.length" class="flex flex-wrap gap-2"><button v-for="entry in searchStore.history" :key="entry" class="rounded-full bg-gray-200/70 px-4 py-2 text-sm text-gray-900 dark:bg-gray-800 dark:text-gray-100" @click="runExample(entry)">{{ entry }}</button></div>
          <p v-else class="text-sm text-gray-500 dark:text-gray-400">还没有搜索记录</p>
        </section>
        <section v-for="group in browseGroups" :key="group.id">
          <div class="mb-3 flex items-center justify-between"><h2 class="ts-section-title text-gray-900 dark:text-white">{{ group.title }}</h2><button class="flex min-h-11 items-center text-sm text-gray-500 dark:text-gray-400" :aria-label="`查看更多${group.title}`" @click="router.push(group.route)">更多<ChevronRight class="h-4 w-4" /></button></div>
          <div v-if="group.data?.representatives.length" class="search-cover-strip" @scroll.passive="onGroupScroll(group.id, $event)">
            <button v-for="item in group.data.representatives" :key="item.entity_id" class="search-cover-card text-left" @click="openRepresentative(group.id, group.route, item)">
              <div class="relative aspect-square overflow-hidden rounded-3xl bg-gray-100 dark:bg-gray-800">
                <SmartAlbumCover :type="group.id" :icon="group.icon" :data="{ item_count: 1, photo_count: item.photo_count, representatives: [item] }" :alt-prefix="item.name" />
                <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent px-3 pb-3 pt-8 text-white"><p class="text-xs">{{ item.photo_count }} 张</p><p class="truncate text-sm font-medium">{{ item.name || '未命名' }}</p></div>
              </div>
            </button>
            <button v-if="group.data.representatives.length < group.data.item_count" class="search-cover-card text-sm text-primary-500" :disabled="albumStore.sectionLoading[group.id]" @click="albumStore.loadMoreSection(group.id)">{{ albumStore.sectionLoading[group.id] ? '加载中…' : albumStore.sectionErrors[group.id] ? '加载失败，点击重试' : '加载更多' }}</button>
          </div>
          <p v-else class="text-sm text-gray-500 dark:text-gray-400">{{ overviewLoading ? '正在加载…' : overviewError ? '加载失败' : '暂无内容' }}<button v-if="overviewError" class="ml-3 min-h-11 text-primary-500" @click="loadOverview">重试</button></p>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import BackButton from '@/components/ui/BackButton.vue'
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { 
  Trash2,
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
  Bot } from 'lucide-vue-next'
import { useDebounceFn } from '@vueuse/core'
import searchService, { type SearchSuggestion } from '@/api/search'
import { parseDateRange } from '@/utils/date'
import IconButton from '@/components/ui/IconButton.vue'
import { useAppBack } from '@/composables/useAppBack'
import { useUiStore } from '@/stores/uiStore'
import { useSearchStore } from '@/stores/searchStore'
import { useAlbumStore } from '@/stores/albumStore'
import type { SmartAlbumOverview, SmartAlbumRepresentative } from '@/api/album'
import { thumbnailUrl } from '@/utils/mediaUrl'
import SmartAlbumCover from '@/components/SmartAlbumCover.vue'

const router = useRouter()
const searchText = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)
const suggestions = ref<SearchSuggestion[]>([])
const uiStore = useUiStore()
const searchStore = useSearchStore()
const albumStore = useAlbumStore()
const showExamples = ref(true)
const overviewLoading = ref(false)
const overviewError = ref(false)
const examples = ['春天的旅行', '夏天', '冬天的冰雪']
const browseGroups = computed(() => [
  { id: 'people' as const, title: '人物', icon: User, route: '/album/people', data: albumStore.smartAlbumOverview?.people },
  { id: 'location' as const, title: '地点', icon: MapPin, route: '/album/location', data: albumStore.smartAlbumOverview?.location },
  { id: 'classification' as const, title: '智能分类', icon: Tag, route: '/album/classification', data: albumStore.smartAlbumOverview?.classification },
])
const exampleCovers = computed(() => albumStore.smartAlbumOverview?.location.representatives.slice(0, 3) ?? [])
const loadOverview = async () => {
  overviewLoading.value = true
  overviewError.value = false
  try { await albumStore.fetchSmartAlbumOverview() }
  catch { overviewError.value = true }
  finally { overviewLoading.value = false }
}
onMounted(loadOverview)
const onGroupScroll = (id: keyof SmartAlbumOverview, event: Event) => {
  const element = event.target as HTMLElement
  if (element.scrollWidth - element.scrollLeft - element.clientWidth < 180) void albumStore.loadMoreSection(id)
}
const openRepresentative = (id: keyof SmartAlbumOverview, route: string, item: SmartAlbumRepresentative) => {
  router.push(`${route}/${encodeURIComponent(id === 'classification' ? item.name : item.entity_id)}`)
}
const runExample = (value: string) => { searchText.value = value; handleSearch() }

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
    
    if (q === searchText.value) suggestions.value = processedSuggestions
  } catch (e) {
    console.error("Failed to fetch suggestions", e)
  }
}, 300);

const onInput = () => {
  fetchSuggestions(searchText.value)
}

const handleSearch = () => {
  if (searchText.value.trim()) {
    searchStore.remember(searchText.value)
    const dateRange = parseDateRange(searchText.value)
    if (dateRange) {
      router.push({ path: '/search', query: { q: searchText.value, type: 'date' } })
    } else {
      router.push({ path: '/search', query: { q: searchText.value } })
    }
  }
}

const selectSuggestion = (item: SearchSuggestion) => {
  searchStore.remember(searchText.value)
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
.search-page input { padding-left: 40px; padding-right: 44px; }
.search-page { max-width: 720px; margin-inline: auto; }
.search-input { min-height: 52px; border-radius: 999px; }
.search-cover-strip { display: flex; gap: 12px; overflow-x: auto; scrollbar-width: none; scroll-snap-type: x proximity; padding-bottom: 4px; }
.search-cover-strip::-webkit-scrollbar { display: none; }
.search-cover-card { flex: 0 0 32%; min-width: 112px; scroll-snap-align: start; }
.search-agent-button:focus-visible { outline: 2px solid var(--accent-color); outline-offset: 2px; }
input[type=search]::-webkit-search-cancel-button { display: none; }
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
