<template>
  <!-- PC端 Header (新版布局) -->
  <header v-if="!isMobile" class="h-14 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border-b border-slate-200 dark:border-slate-800 flex items-center justify-between px-4 shrink-0 z-30 transition-colors duration-300">
    <!-- 左侧搜索区 -->
    <div class="flex items-center flex-1 max-w-md">
      <div class="relative w-full flex items-center">
        <Search class="absolute left-3 w-4 h-4 text-slate-400" />
        
        <input
          ref="searchInputRef"
          v-model="searchText"
          @input="onInput"
          @keydown.enter="handleSearch"
          @blur="handleBlur"
          @focus="handleFocus"
          type="text"
          placeholder="画面内容/地点/人物/相册..."
          class="w-full pl-9 pr-7 py-1.5 text-sm bg-slate-100 dark:bg-slate-800 border border-transparent dark:border-slate-700 rounded-full focus:outline-none focus:border-primary-500 focus:bg-white dark:focus:bg-slate-900 text-slate-700 dark:text-slate-200 transition-colors"
        />
        
        <button 
          v-if="searchText"
          @click="clearSearch"
          class="absolute right-2 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
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
    </div>

    <!-- 右侧（筛选等其他操作） -->
    <div class="flex items-center space-x-3 ml-auto">
      <!-- 预留的筛选器/功能控件 -->
      <button class="bg-transparent p-2 text-slate-600 dark:text-slate-300 hover:text-primary-600 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors" title="筛选">
        <Filter class="w-4 h-4" />
      </button>
    </div>
  </header>

  <!-- 手机端 Header (旧版悬浮药丸布局) -->
  <header v-else class="z-[100] transition-colors duration-300 absolute top-0 left-0 right-0 h-[60px] flex flex-col justify-center px-4 pointer-events-none">
    <nav class="pointer-events-auto bg-white/80 dark:bg-slate-800/80 backdrop-blur-md shadow-md rounded-full px-4 py-1 flex justify-center items-center space-x-2 fixed left-1/2 transform -translate-x-1/2 transition-colors duration-300 w-[90vw] h-[40px] top-[10px]">
      <RouterLink
        v-for="(item, index) in navLinks"
        :key="index"
        :to="item.href"
        class="relative px-3 py-1.5 text-sm text-slate-700 dark:text-slate-200 hover:text-primary-500 dark:hover:text-primary-500 transition-colors flex items-center gap-1.5"
        active-class="font-medium text-primary-600 dark:text-primary-400"
      >
        {{ item.label }}
        <span
          v-if="$route.path === item.href || ($route.path.startsWith(item.href) && item.href !== '/')"
          class="absolute bottom-0 left-0 w-full h-0.5 bg-primary-500 rounded-full"
        ></span>
      </RouterLink>

      <div class="relative transition-all duration-300 ease-in-out" :class="[isSearchExpanded ? 'w-32' : 'w-8']">
        <button 
          @click="toggleSearch"
          class="absolute bg-transparent left-0 top-1/2 -translate-y-1/2 p-1.5 text-slate-700 dark:text-slate-200 hover:text-primary-500 transition-colors z-10 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800"
          :class="{'bg-transparent hover:bg-transparent dark:hover:bg-transparent': isSearchExpanded}"
          title="搜索"
        >
          <Search class="w-4 h-4" />
        </button>
        
        <input
          v-show="isSearchExpanded"
          ref="searchInputRef"
          v-model="searchText"
          @input="onInput"
          @keydown.enter="handleSearch"
          @blur="handleBlur"
          @focus="handleFocus"
          type="text"
          placeholder="搜索..."
          class="w-full pl-9 pr-7 py-1 text-sm bg-transparent border border-slate-300 dark:border-slate-600 rounded-full focus:outline-none focus:border-primary-500 text-slate-700 dark:text-slate-200"
        />
        
        <button 
          v-if="isSearchExpanded && searchText"
          @click="clearSearch"
          class="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-slate-400 dark:text-slate-200 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
        >
          <X class="w-3 h-3" />
        </button>
      </div>

      <!-- More Menu -->
      <div class="relative" ref="moreMenuRef">
        <button
          @click="showMoreMenu = !showMoreMenu"
          class="px-2 py-1 bg-transparent text-slate-700 dark:text-slate-200 hover:text-primary-500 transition-colors flex items-center gap-1 text-sm font-medium"
          :class="{ 'text-primary-500': showMoreMenu || moreLinks.some(l => $route.path.startsWith(l.href)) }"
        >
          更多 <ChevronDown class="w-3 h-3 transition-transform duration-200" :class="{ 'rotate-180': showMoreMenu }" />
        </button>

        <div
          v-if="showMoreMenu"
          class="absolute top-10 left-1/2 transform -translate-x-1/2 w-32 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl p-1 z-50 animate-in fade-in zoom-in-95 duration-200 overflow-hidden"
        >
          <RouterLink
            v-for="link in moreLinks"
            :key="link.href"
            :to="link.href"
            @click="showMoreMenu = false"
            class="block px-4 py-2 text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors text-center"
            active-class="bg-primary-50 text-primary-600 dark:bg-slate-700 dark:text-primary-400 font-medium"
          >
            {{ link.label }}
          </RouterLink>
        </div>
      </div>
    </nav>
  </header>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import {
  Image as ImageIcon, 
  Images, 
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
  Filter,
  ChevronDown
} from 'lucide-vue-next';
import { useRouter } from 'vue-router'
import { onClickOutside, useDebounceFn, useBreakpoints, breakpointsTailwind } from '@vueuse/core'
import { usePhotoStore } from '@/stores/photoStore'
import searchService, { type SearchSuggestion } from '@/api/search'

const navLinks = [
  { label: '首页', href: '/' },
  { label: '照片', href: '/photos' },
  { label: '相册', href: '/album'},
]

const moreLinks = [
  { label: '车票', href: '/ticket' },
  { label: '工具箱', href: '/toolbox' },
  { label: '设置', href: '/settings' },
]

const showMoreMenu = ref(false);
const moreMenuRef = ref(null);

onClickOutside(moreMenuRef, () => {
  showMoreMenu.value = false;
});

const router = useRouter();
const store = usePhotoStore();
const breakpoints = useBreakpoints(breakpointsTailwind);
const isMobile = breakpoints.smaller('md');

const searchText = ref('');
const isSearchExpanded = ref(false);
const showDropdown = ref(false);
const searchInputRef = ref<HTMLInputElement | null>(null);
const suggestions = ref<SearchSuggestion[]>([]);

watch(() => store.currentContext, (ctx) => {
  if (ctx.type === 'search' && ctx.id) {
    searchText.value = ctx.id;
    isSearchExpanded.value = true;
  } else if (ctx.type !== 'search') {
    searchText.value = '';
    isSearchExpanded.value = false;
    suggestions.value = [];
  }
});

const toggleSearch = () => {
  if (isMobile.value) {
    router.push('/mobile-search');
    return;
  }
  if (isSearchExpanded.value && searchText.value) {
    handleSearch();
  } else {
    isSearchExpanded.value = !isSearchExpanded.value;
    if (isSearchExpanded.value) {
      nextTick(() => {
        // Find the correct input element
        if (Array.isArray(searchInputRef.value)) {
          searchInputRef.value[0]?.focus();
        } else {
          searchInputRef.value?.focus();
        }
      });
    } else {
      suggestions.value = [];
    }
  }
};

const handleBlur = () => {
  setTimeout(() => {
    showDropdown.value = false;
    if (!searchText.value) {
      isSearchExpanded.value = false;
    }
    suggestions.value = [];
  }, 200);
};

const handleFocus = () => {
  showDropdown.value = true;
  if (searchText.value) {
    fetchSuggestions(searchText.value);
  }
}

const handleSearch = () => {
  if (searchText.value.trim()) {
    showDropdown.value = false;
    suggestions.value = [];
    router.push({ path: '/search', query: { q: searchText.value } });
    if (Array.isArray(searchInputRef.value)) {
      searchInputRef.value[0]?.blur();
    } else {
      searchInputRef.value?.blur();
    }
  }
};

const clearSearch = () => {
  searchText.value = '';
  suggestions.value = [];
  store.loadPhotos(true);
  if (Array.isArray(searchInputRef.value)) {
    searchInputRef.value[0]?.focus();
  } else {
    searchInputRef.value?.focus();
  }
};

const fetchSuggestions = useDebounceFn(async (q: string) => {
  if (!q.trim()) {
    suggestions.value = [];
    return;
  }
  try {
    const res = await searchService.getSuggestions(q);
    const processedSuggestions: SearchSuggestion[] = [];
    let hasOcr = false;
    
    for (const item of res) {
      if (item.type === 'ocr') {
        hasOcr = true;
      } else {
        processedSuggestions.push(item);
      }
    }
    
    if (hasOcr) {
      processedSuggestions.push({
        type: 'ocr',
        value: q,
        label: `图片中包含文字：${q}`
      } as SearchSuggestion);
    }
    
    suggestions.value = processedSuggestions;
  } catch (e) {
    console.error("Failed to fetch suggestions", e);
  }
}, 300);

const onInput = () => {
  showDropdown.value = true;
  fetchSuggestions(searchText.value);
}

const selectSuggestion = (item: SearchSuggestion) => {
  searchText.value = item.value;
  showDropdown.value = false;
  suggestions.value = [];
  router.push({ 
    path: '/search', 
    query: { 
      q: item.value, 
      type: item.type 
    } 
  });
  if (Array.isArray(searchInputRef.value)) {
    searchInputRef.value[0]?.blur();
  } else {
    searchInputRef.value?.blur();
  }
};

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
    'scene': Mountain
  };
  return map[type] || Search;
}
</script>

<style scoped>
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
