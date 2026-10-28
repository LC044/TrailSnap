<template>
  <div class="agent-chat-header">
    <div class="agent-header-title flex min-w-0 flex-1 items-center gap-3">
      <button @click="emit('toggle-sidebar')" class="ts-icon-button ts-button-ghost" aria-label="会话列表">
        <Menu class="w-5 h-5" />
      </button>
      <div class="agent-header-icon w-8 h-8 shrink-0 rounded-full bg-primary-500/10 flex items-center justify-center">
        <Bot class="w-5 h-5 text-primary-600 dark:text-primary-500" />
      </div>
      <div class="flex min-w-0 flex-col">
        <div class="flex min-w-0 items-center gap-2">
          <h3 class="truncate font-semibold text-slate-800 dark:text-white text-sm m-0">{{ searchMode ? '大模型搜索' : 'TrailSnap' }}</h3>
        </div>
        <p class="agent-header-subtitle truncate text-xs text-slate-500 dark:text-slate-400 m-0">{{ searchMode ? '理解搜索条件，查找完整照片结果' : '您的智能相册管家' }}</p>
      </div>
    </div>
    <div class="agent-header-actions flex shrink-0 items-center gap-2">
      <button v-if="searchMode && !isSelectionMode" type="button" :disabled="isGenerating" class="agent-header-switch ts-button ts-button-ghost ts-button-sm text-xs" @click="emit('switch-mode')"><span class="agent-header-switch-prefix">转到</span> AI 助手</button>
      <!-- 批量删除状态下显示的操作按钮 -->
      <template v-if="isSelectionMode">
        <button v-if="selectedCount > 0" @click="emit('delete-selection')" class="text-red-500 hover:text-red-600 dark:text-red-400 dark:hover:text-red-300 text-sm font-medium ml-1 transition-colors">
          删除 ({{ selectedCount }})
        </button>
        <button @click="emit('cancel-selection')" class="text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 text-sm ml-2 transition-colors">
          取消
        </button>
      </template>
      
      <div v-if="!searchMode" class="w-px h-4 bg-slate-200 dark:bg-slate-700 mx-1"></div>

      <button v-if="!isSelectionMode" @click="emit('toggle-fullscreen')" class="ts-icon-button ts-button-ghost" :aria-label="isFullscreen ? '退出全屏' : '全屏'" :title="isFullscreen ? '退出全屏' : '全屏'">
        <Minimize2 v-if="isFullscreen" class="w-5 h-5" />
        <Maximize2 v-else class="w-5 h-5" />
      </button>
      <button @click="emit('close')" class="ts-icon-button ts-button-ghost" aria-label="关闭 AI 助手">
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
  searchMode?: boolean;
  isGenerating?: boolean;
}>();

const emit = defineEmits<{
  (e: 'toggle-sidebar'): void;
  (e: 'toggle-fullscreen'): void;
  (e: 'close'): void;
  (e: 'cancel-selection'): void;
  (e: 'delete-selection'): void;
  (e: 'switch-mode'): void;
}>();
</script>

<style scoped>
.agent-chat-header {
  @apply px-3 py-2 border-b flex justify-between items-center z-10;
  container-type: inline-size;
  min-height: var(--ts-header-height);
  flex-shrink: 0;
  border-color: var(--ts-color-divider);
  background: var(--ts-glass-bg);
  backdrop-filter: blur(var(--ts-glass-blur));
}

@container (max-width: 540px) {
  .agent-header-icon, .agent-header-subtitle, .agent-header-switch-prefix { display: none; }
  .agent-header-title { gap: 0.25rem; }
  .agent-header-actions { gap: 0; }
  .agent-header-switch { white-space: nowrap; }
}

</style>
