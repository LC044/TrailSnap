<template>
  <div class="agent-chat-header">
    <div class="flex items-center gap-3">
      <button @click="emit('toggle-sidebar')" class="text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors dark:bg-slate-800 p-1 rounded-md">
        <Menu class="w-5 h-5" />
      </button>
      <div class="w-8 h-8 rounded-full bg-indigo-100 dark:bg-indigo-900/50 flex items-center justify-center hidden sm:flex">
        <Bot class="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
      </div>
      <div class="flex min-w-0 flex-col">
        <div class="flex min-w-0 items-center gap-2">
          <h3 class="font-semibold text-slate-800 dark:text-white text-sm m-0">TrailSnap</h3>
          <el-select
            :model-value="modelValue"
            @update:model-value="(val: string) => emit('update:modelValue', val)"
            size="small"
            class="agent-model-select"
            placeholder="选择模型"
            v-if="availableModels.length > 0 || isModelsLoading"
            :loading="isModelsLoading"
          >
            <el-option
              v-for="m in availableModels"
              :key="m.conn_id + '|' + m.model"
              :label="m.model"
              :value="m.conn_id + '|' + m.model"
            >
              <span>{{ m.label }}</span>
            </el-option>
          </el-select>
        </div>
        <p class="text-xs text-slate-500 dark:text-slate-400 m-0 hidden sm:block">您的智能相册管家</p>
      </div>
    </div>
    <div class="flex items-center gap-2">
      <!-- 批量删除状态下显示的操作按钮 -->
      <template v-if="isSelectionMode">
        <button v-if="selectedCount > 0" @click="emit('delete-selection')" class="text-red-500 hover:text-red-600 dark:text-red-400 dark:hover:text-red-300 text-sm font-medium ml-1 transition-colors">
          删除 ({{ selectedCount }})
        </button>
        <button @click="emit('cancel-selection')" class="text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 text-sm ml-2 transition-colors">
          取消
        </button>
      </template>
      
      <div class="w-px h-4 bg-slate-200 dark:bg-slate-700 mx-1"></div>

      <button @click="emit('toggle-fullscreen')" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors dark:bg-slate-800 p-1 rounded-md" :title="isFullscreen ? '退出全屏' : '全屏'">
        <Minimize2 v-if="isFullscreen" class="w-5 h-5" />
        <Maximize2 v-else class="w-5 h-5" />
      </button>
      <button @click="emit('close')" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors dark:bg-slate-800 p-1 rounded-md">
        <X class="w-5 h-5" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Bot, Menu, Maximize2, Minimize2, X } from 'lucide-vue-next';

defineProps<{
  isFullscreen: boolean;
  isSelectionMode: boolean;
  selectedCount: number;
  availableModels: Array<{ conn_id: string, model: string, label: string }>;
  modelValue: string;
  isModelsLoading: boolean;
}>();

const emit = defineEmits<{
  (e: 'toggle-sidebar'): void;
  (e: 'toggle-fullscreen'): void;
  (e: 'close'): void;
  (e: 'cancel-selection'): void;
  (e: 'delete-selection'): void;
  (e: 'update:modelValue', value: string): void;
}>();
</script>

<style scoped>
.agent-chat-header {
  @apply px-4 py-3 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center bg-white/80 dark:bg-slate-900/80 backdrop-blur-md z-10;
}

.agent-model-select {
  width: clamp(7rem, 22vw, 11rem);
  flex-shrink: 0;
}
</style>
