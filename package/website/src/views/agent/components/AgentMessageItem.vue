<template>
  <div class="flex w-full group relative">
    <!-- Checkbox for selection mode -->
    <div v-if="isSelectionMode" class="flex-shrink-0 w-8 flex justify-center pb-2 items-end">
      <el-checkbox 
        :model-value="isSelected" 
        @change="emit('toggle-select', msg.id)" 
        :disabled="msg.id === undefined" 
      />
    </div>

    <div class="message-wrapper flex-1" :class="msg.role === 'user' ? 'justify-end' : 'justify-start'">
      <div v-if="msg.role === 'assistant'" class="message-avatar assistant">
        <Bot class="w-4 h-4" />
      </div>

      <div class="flex flex-col gap-1 max-w-[85%]" :class="msg.role === 'user' ? 'items-end' : 'items-start'">
        <div class="message-bubble" :class="[msg.role, { 'opacity-60': isSelectionMode && !isSelected }]">
          <div v-if="msg.role === 'assistant' && msg.reasoning" class="reasoning-container mb-2 text-sm text-slate-500 bg-slate-50 dark:bg-slate-800/50 rounded-md border border-slate-200 dark:border-slate-700 overflow-hidden">
            <div class="flex items-center justify-between p-2 cursor-pointer select-none bg-slate-100/50 dark:bg-slate-800" @click="emit('toggle-reasoning')">
              <div class="flex items-center gap-2">
                <Brain class="w-4 h-4 text-slate-400" />
                <span class="font-medium">思考过程</span>
              </div>
              <ChevronDown class="w-4 h-4 text-slate-400 transition-transform" :class="{ 'rotate-180': msg.isReasoningExpanded }" />
            </div>
            <div v-show="msg.isReasoningExpanded" class="p-3 whitespace-pre-wrap break-words border-t border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 text-xs">
              {{ msg.reasoning }}
            </div>
          </div>
          <div v-if="msg.isMarkdown" class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
          <div v-else class="whitespace-pre-wrap break-words">{{ msg.content }}</div>
        </div>
        
        <!-- Message Actions Space Placeholder -->
        <div v-if="!isSelectionMode" class="h-7 w-full flex items-center gap-1 text-slate-400 dark:text-slate-500 mt-0.5 px-1" :class="msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'">
          <!-- Message Actions -->
          <div class="message-actions items-center gap-1 transition-opacity duration-200" 
               :class="[
                 msg.role === 'user' ? 'flex-row-reverse' : 'flex-row',
                 isDropdownActive ? 'flex opacity-100' : 'hidden group-hover:flex opacity-0 group-hover:opacity-100'
               ]">
            <button @click="emit('copy', msg.content)" class="bg-transparent hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors p-1 rounded-md" title="复制">
              <Copy class="w-4 h-4"/>
            </button>
            
            <!-- 重新生成按钮：只在最后一条助手消息显示 -->
            <button v-if="msg.role === 'assistant' && isLastAssistant" @click="emit('regenerate', msg, index)" class="bg-transparent hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors p-1 rounded-md" title="重新生成">
              <RefreshCw class="w-4 h-4"/>
            </button>
            
            <!-- 编辑按钮：只在最后一条用户消息显示 -->
            <button v-if="msg.role === 'user' && isLastUser" @click="emit('edit', msg, index)" class="bg-transparent hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors p-1 rounded-md" title="编辑">
              <Edit2 class="w-4 h-4"/>
            </button>

            <div @click.stop>
              <el-dropdown trigger="click" @command="(cmd: string) => emit('command', cmd, msg, index)" @visible-change="(visible: boolean) => emit('dropdown-visible', visible, index)">
                <button class="bg-transparent hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors p-1 rounded-md" title="更多">
                  <MoreHorizontal class="w-4 h-4"/>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="delete" class="text-red-500">
                      <Trash2 class="w-4 h-4 mr-2" />
                      删除消息
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </div>
      </div>

      <div v-if="msg.role === 'user'" class="message-avatar user">
        <img v-if="userStore.userInfo?.avatar" :src="userStore.userInfo.avatar" alt="我" class="w-full h-full object-cover rounded-full" />
        <User v-else class="w-4 h-4" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Bot, User, Copy, RefreshCw, Edit2, MoreHorizontal, Trash2, Brain, ChevronDown } from 'lucide-vue-next';
import { useUserStore } from '@/stores/user';

const userStore = useUserStore();

interface MessageItem {
  id?: number;
  role: 'user' | 'assistant';
  content: string;
  isMarkdown?: boolean;
  reasoning?: string;
  isReasoningExpanded?: boolean;
}

const props = defineProps<{
  msg: MessageItem;
  index: number;
  isSelectionMode: boolean;
  isSelected: boolean;
  isLastAssistant: boolean;
  isLastUser: boolean;
  isDropdownActive: boolean;
  renderMarkdown: (content: string) => string;
}>();

const emit = defineEmits<{
  (e: 'toggle-select', id?: number): void;
  (e: 'copy', content: string): void;
  (e: 'regenerate', msg: MessageItem, index: number): void;
  (e: 'edit', msg: MessageItem, index: number): void;
  (e: 'command', command: string, msg: MessageItem, index: number): void;
  (e: 'dropdown-visible', visible: boolean, index: number): void;
  (e: 'toggle-reasoning'): void;
}>();
</script>

<style scoped>
.message-wrapper {
  @apply flex items-end gap-2 w-full;
}

.message-avatar {
  @apply w-7 h-7 rounded-full flex items-center justify-center shrink-0 mb-1;
}

.message-avatar.assistant {
  @apply bg-indigo-100 text-indigo-600 dark:bg-indigo-900/50 dark:text-indigo-400;
}

.message-avatar.user {
  @apply bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400;
}

.message-bubble {
  @apply rounded-2xl px-4 py-2.5 text-sm shadow-sm transition-opacity duration-200;
}

.message-bubble.user {
  @apply bg-indigo-600 text-white rounded-br-sm;
}

.message-bubble.assistant {
  @apply bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-100 dark:border-slate-700 rounded-bl-sm;
}
</style>
