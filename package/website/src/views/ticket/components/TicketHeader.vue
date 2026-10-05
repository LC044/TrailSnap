<template>
  <header class="ts-page-header sticky top-0 z-30 border-b">
    <div class="mx-auto flex min-h-[var(--ts-header-height)] items-center justify-between gap-3 px-[var(--ts-page-gutter)] py-2">
      <h1 class="ts-page-title min-w-0 truncate"><span class="sm:hidden">车票</span><span class="hidden sm:inline">车票管理</span></h1>
      <div class="relative mx-4 hidden min-w-0 max-w-md flex-1 lg:block">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--ts-color-text-tertiary)]" />
        <input :value="searchQuery" @input="handleSearchInput" type="search" aria-label="搜索车票" placeholder="搜索车次 / 地点 / 乘车人" class="ts-input w-full pl-9" />
      </div>
      <div class="ts-liquid-glass ts-glass-toolbar flex shrink-0 items-center">
        <button class="ts-glass-button lg:hidden" aria-label="搜索车票" :aria-expanded="showSearch" @click="showSearch = !showSearch"><Search class="h-5 w-5" /></button>
        <button class="ts-glass-button hidden md:inline-flex" aria-label="统计报表" @click="emit('go-to-statistics')"><BarChart2 class="h-5 w-5" /></button>
        <button class="ts-glass-button hidden md:inline-flex" aria-label="导入车票" @click="triggerImport"><Upload class="h-5 w-5" /></button>
        <button class="ts-glass-button hidden md:inline-flex" aria-label="导出车票" @click="emit('handle-export')"><Download class="h-5 w-5" /></button>
        <button class="ts-glass-button md:hidden" aria-label="更多车票操作" @click="showActions = true"><MoreHorizontal class="h-5 w-5" /></button>
        <button class="ts-glass-button text-primary-600 dark:text-primary-400" aria-label="新增车票" @click="emit('open-ticket-modal')"><Plus class="h-5 w-5" /></button>
      </div>
    </div>
    <div v-if="showSearch" class="px-[var(--ts-page-gutter)] pb-3 lg:hidden">
      <input :value="searchQuery" @input="handleSearchInput" type="search" aria-label="搜索车票" placeholder="搜索车次 / 地点 / 乘车人" class="ts-input w-full" />
    </div>
    <input type="file" ref="fileInput" class="hidden" accept=".json,.csv" @change="handleFileImport" />
  </header>
  <ResponsiveDialog v-model="showActions" title="车票操作">
    <button class="ts-action-row" @click="showActions = false; emit('go-to-statistics')"><BarChart2 />统计报表</button>
    <button class="ts-action-row" @click="showActions = false; triggerImport()"><Upload />导入车票</button>
    <button class="ts-action-row" @click="showActions = false; emit('handle-export')"><Download />导出车票</button>
  </ResponsiveDialog>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { 
  Search, BarChart2, Upload, Download, Plus, MoreHorizontal
} from 'lucide-vue-next';
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue';

defineProps<{
  searchQuery: string;
}>();

const emit = defineEmits<{
  (e: 'update:searchQuery', value: string): void;
  (e: 'go-to-statistics'): void;
  (e: 'handle-export'): void;
  (e: 'open-ticket-modal'): void;
  (e: 'handle-file-import', event: Event): void;
}>();

const showActions = ref(false);
const showSearch = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

const handleSearchInput = (event: Event) => {
  const target = event.target as HTMLInputElement;
  emit('update:searchQuery', target.value);
};

const triggerImport = () => {
  fileInput.value?.click();
};

const handleFileImport = (event: Event) => {
  emit('handle-file-import', event);
  // Reset input value to allow selecting the same file again if needed
  if (fileInput.value) fileInput.value.value = '';
};
</script>
