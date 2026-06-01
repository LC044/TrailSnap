<template>
  <nav class="sticky top-0 z-30 shadow-sm h-14 transition-colors duration-300 bg-slate-50/90 dark:bg-slate-900/90 backdrop-blur-md">
    <div class="mx-auto px-4 h-full flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg flex items-center justify-center border border-primary-500 bg-primary-50 dark:bg-slate-700/50 transition-colors">
          <TrainFront class="w-5 h-5 text-primary-600 dark:text-primary-400" />
        </div>
        <span class="text-lg font-medium tracking-wide text-slate-800 dark:text-white hidden sm:block">车票管理</span>
      </div>

      <div class="flex-1 max-w-md mx-4 hidden md:block">
        <div class="relative group">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 group-focus-within:text-primary-500 transition-colors" />
          <input
            :value="searchQuery"
            @input="handleSearchInput"
            type="text"
            placeholder="搜索车次 / 地点 / 乘车人"
            class="w-full pl-9 pr-4 py-1.5 bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-full focus:outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-200 dark:focus:ring-primary-900 transition-all text-sm dark:text-white dark:placeholder-slate-400"
          />
        </div>
      </div>

      <div class="flex items-center gap-2">
        <button
          @click="$emit('go-to-statistics')"
          class="p-2 text-slate-500 hover:text-primary-600 hover:bg-primary-50 dark:hover:bg-slate-700 dark:bg-slate-800 rounded-full transition-colors"
          title="统计报表"
        >
          <BarChart2 class="w-5 h-5" />
        </button>
        <div class="flex items-center gap-1 border-l border-slate-200 dark:border-slate-700 ml-1 pl-2">
          <button
            @click="triggerImport"
            class="p-2 text-slate-500 hover:text-primary-600 hover:bg-primary-50 dark:hover:bg-slate-700 dark:bg-slate-800 rounded-full transition-colors"
            title="导入数据"
          >
            <Upload class="w-5 h-5" />
          </button>
          <button
            @click="$emit('handle-export')"
            class="p-2 text-slate-500 hover:text-primary-600 hover:bg-primary-50 dark:hover:bg-slate-700 dark:bg-slate-800 rounded-full transition-colors"
            title="导出数据"
          >
            <Download class="w-5 h-5" />
          </button>
        </div>

        <button
          @click="$emit('open-ticket-modal')"
          class="flex items-center gap-1.5 bg-primary-600 hover:bg-primary-700 text-white px-3 py-1.5 rounded-full transition-all active:scale-95 shadow-md shadow-primary-200 dark:shadow-none ml-2"
        >
          <Plus class="w-4 h-4" />
          <span class="text-sm font-medium">新增</span>
        </button>
        
        <input 
          type="file" 
          ref="fileInput" 
          class="hidden" 
          accept=".json,.csv" 
          @change="handleFileImport" 
        />
      </div>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { 
  TrainFront, Search, BarChart2, Upload, Download, Plus 
} from 'lucide-vue-next';

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
