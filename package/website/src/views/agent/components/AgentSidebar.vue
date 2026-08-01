<template>
  <div v-if="isOpen" class="agent-sidebar">
    <div class="sidebar-header">
      <span class="font-semibold text-slate-800 dark:text-white text-sm">历史会话</span>
      <div class="flex items-center gap-1">
        <button @click="emit('create')" class="text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300 dark:bg-slate-800 p-1 rounded-md focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" title="新建会话">
          <Plus class="w-5 h-5" />
        </button>
        <!-- 移动端关闭按钮：抽屉模式下侧边栏会遮住 Header 的菜单按钮，提供一个显式关闭入口 -->
        <button @click="emit('close')" class="sm:hidden text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 dark:bg-slate-800 p-1 rounded-md focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" title="关闭侧边栏" aria-label="关闭侧边栏">
          <X class="w-5 h-5" />
        </button>
      </div>
    </div>
    <div class="sidebar-content">
      <div
        v-for="session in sortedSessions"
        :key="session.id"
        @click="emit('switch', session)"
        :class="['session-item group', { 'active': currentSessionId === session.id }]"
      >
        <MessageSquare class="w-4 h-4 mr-2 text-slate-400 shrink-0" />
        <div class="flex-1 truncate text-sm text-slate-700 dark:text-slate-300 p-1 rounded-md">{{ session.title || '新会话' }}</div>
        <div class="session-actions hidden group-hover:flex items-center">
          <div @click.stop>
            <el-dropdown trigger="click" @command="(cmd: string) => emit('command', cmd, session)">
              <button class="text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 dark:bg-slate-800 p-1 rounded-md transition-colors" title="更多操作">
                <MoreHorizontal class="w-4 h-4" />
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="pin">
                    <Pin class="w-4 h-4 mr-2" />
                    {{ session.is_pinned ? '取消置顶' : '置顶会话' }}
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" class="text-red-500">
                    <Trash2 class="w-4 h-4 mr-2" />
                    删除会话
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
        <Pin v-if="session.is_pinned" class="w-4 h-4 text-yellow-500 ml-auto shrink-0 group-hover:hidden" />
      </div>
      <div v-if="sessions.length === 0" class="text-center text-slate-400 text-sm mt-4">
        暂无历史会话
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Plus, Trash2, Pin, MessageSquare, MoreHorizontal, X } from 'lucide-vue-next';
import type { AgentSession } from '@/api/agent';

const props = defineProps<{
  isOpen: boolean;
  sessions: AgentSession[];
  currentSessionId?: string;
}>();

const emit = defineEmits<{
  (e: 'create'): void;
  (e: 'close'): void;
  (e: 'switch', session: AgentSession): void;
  (e: 'command', command: string, session: AgentSession): void;
}>();

const sortedSessions = computed(() => {
  return [...props.sessions].sort((a, b) => {
    if (a.is_pinned && !b.is_pinned) return -1;
    if (!a.is_pinned && b.is_pinned) return 1;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });
});
</script>

<style scoped>
.agent-sidebar {
  @apply absolute sm:relative z-20 w-64 h-full border-r border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 flex flex-col shrink-0 shadow-xl sm:shadow-none;
}

.sidebar-header {
  @apply px-4 py-3 flex justify-between items-center border-b border-slate-200 dark:border-slate-800;
}

.sidebar-content {
  @apply flex-1 overflow-y-auto p-2 space-y-1;
}

.session-item {
  @apply flex items-center px-3 py-2.5 rounded-lg cursor-pointer transition-colors;
}

.session-item:hover {
  @apply bg-slate-200/50 dark:bg-slate-800;
}

.session-item.active {
  @apply bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400;
}
</style>
