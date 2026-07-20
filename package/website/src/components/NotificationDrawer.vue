<template>
  <!-- 通知抽屉 + 设置弹窗。整个应用只挂载一份（在 MainLayout 里），由 store.drawerOpen 控制。 -->
  <el-drawer
    v-model="drawerVisible"
    title="通知"
    direction="rtl"
    size="380px"
    :with-header="true"
    class="notification-drawer"
  >
    <div class="flex items-center justify-between px-1 mb-2">
      <el-tabs v-model="activeTab" class="flex-1">
        <el-tab-pane :label="`通知 ${store.notifications.length || ''}`" name="notif" />
        <el-tab-pane :label="`任务 ${store.taskRunning.length || ''}`" name="task" />
      </el-tabs>
      <button
        v-if="activeTab === 'notif'"
        @click="onMarkAllRead"
        class="text-xs text-primary-500 hover:text-primary-600 dark:hover:text-primary-400 font-medium shrink-0 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none rounded"
      >全部已读</button>
      <button
        v-else
        @click="store.dismissAllTasks()"
        class="text-xs text-primary-500 hover:text-primary-600 dark:hover:text-primary-400 font-medium shrink-0 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none rounded"
      >清空</button>
    </div>

    <!-- 通知列表 -->
    <div v-if="activeTab === 'notif'" class="space-y-2 overflow-y-auto custom-scrollbar" style="max-height: calc(100vh - 220px)">
      <div
        v-for="n in store.notifications"
        :key="n.id"
        class="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-700/50"
      >
        <div class="flex items-start gap-2">
          <component :is="levelIcon(n.level)" class="w-4 h-4 mt-0.5 shrink-0" :class="levelColor(n.level)" />
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm font-medium text-slate-700 dark:text-slate-200 truncate">{{ n.title }}</span>
              <span class="text-[10px] text-slate-400 dark:text-slate-500 shrink-0">{{ typeLabel(n.type) }}</span>
            </div>
            <p v-if="n.body && bodyText(n.body)" class="text-xs text-slate-500 dark:text-slate-400 mt-1 break-words">{{ bodyText(n.body) }}</p>
            <div class="flex items-center justify-between mt-2">
              <span class="text-[10px] text-slate-400 dark:text-slate-500">{{ formatTime(n.created_at) }}</span>
              <button
                @click="onMarkRead(n.id)"
                class="text-xs text-primary-500 hover:text-primary-600 dark:hover:text-primary-400 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none rounded"
              >标为已读</button>
            </div>
          </div>
        </div>
      </div>
      <div v-if="store.notifications.length === 0" class="py-12 text-center text-sm text-slate-400 dark:text-slate-500">
        没有未读通知
      </div>
    </div>

    <!-- 任务 live 态 -->
    <div v-else class="space-y-3 overflow-y-auto custom-scrollbar" style="max-height: calc(100vh - 220px)">
      <!-- 进行中 -->
      <div v-if="store.taskRunning.length > 0">
        <div class="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1.5">进行中</div>
        <div
          v-for="t in store.taskRunning"
          :key="t.id"
          class="p-2.5 rounded-lg bg-primary-50/50 dark:bg-primary-900/10 border border-primary-100 dark:border-primary-900/30 flex items-center gap-2"
        >
          <Loader2 class="w-4 h-4 text-primary-500 animate-spin shrink-0" />
          <div class="flex-1 min-w-0">
            <div class="text-sm text-slate-700 dark:text-slate-200 truncate">{{ store.CATEGORY_NAME_MAP[t.type] || t.type }}</div>
            <div class="text-[10px] text-slate-400 dark:text-slate-500">{{ t.processed_items || 0 }} / {{ t.total_items || 0 }}</div>
          </div>
        </div>
      </div>

      <!-- 失败 -->
      <div v-if="store.taskFailed.length > 0">
        <div class="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1.5">失败</div>
        <div
          v-for="t in store.taskFailed"
          :key="t.id"
          class="p-2.5 rounded-lg bg-red-50/60 dark:bg-red-900/10 border border-red-100 dark:border-red-900/30 flex items-start gap-2"
        >
          <XCircle class="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
          <div class="flex-1 min-w-0">
            <div class="text-sm text-slate-700 dark:text-slate-200 truncate">{{ store.CATEGORY_NAME_MAP[t.type] || t.type }}</div>
            <div v-if="t.error" class="text-[10px] text-red-500 dark:text-red-400 mt-0.5 break-words">{{ t.error }}</div>
          </div>
          <button
            @click="store.ignoreFailed(t.id)"
            class="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 shrink-0 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none rounded"
          >忽略</button>
        </div>
      </div>

      <!-- 完成 -->
      <div v-if="store.taskCompleted.length > 0">
        <div class="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1.5">已完成</div>
        <div
          v-for="t in store.taskCompleted"
          :key="t.id"
          class="p-2.5 rounded-lg bg-emerald-50/50 dark:bg-emerald-900/10 border border-emerald-100 dark:border-emerald-900/30 flex items-center gap-2"
        >
          <CheckCircle2 class="w-4 h-4 text-emerald-500 shrink-0" />
          <div class="flex-1 min-w-0 text-sm text-slate-700 dark:text-slate-200 truncate">{{ store.CATEGORY_NAME_MAP[t.type] || t.type }}</div>
          <button
            @click="store.dismissTask(t.id)"
            class="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 shrink-0 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none rounded"
          >知道了</button>
        </div>
      </div>

      <div
        v-if="store.taskRunning.length === 0 && store.taskFailed.length === 0 && store.taskCompleted.length === 0"
        class="py-12 text-center text-sm text-slate-400 dark:text-slate-500"
      >没有任务通知</div>
    </div>

    <!-- 底部设置入口 -->
    <template #footer>
      <button
        @click="store.openPrefs()"
        class="w-full py-2 text-sm text-slate-600 dark:text-slate-300 hover:text-primary-600 dark:hover:text-primary-400 border-t border-slate-100 dark:border-slate-700/50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none rounded"
      >通知设置</button>
    </template>
  </el-drawer>

  <!-- 设置弹窗 -->
  <el-dialog v-model="prefsVisible" title="通知设置" width="360px" append-to-body>
    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <span class="text-sm text-slate-700 dark:text-slate-200">桌面通知</span>
        <el-button size="small" @click="store.requestDesktopPermission()" :disabled="store.desktopNotifications">
          {{ store.desktopNotifications ? '已开启' : '开启' }}
        </el-button>
      </div>
      <el-divider class="!my-2" />
      <div class="text-xs text-slate-500 dark:text-slate-400 mb-1">任务分类提醒</div>
      <div
        v-for="cat in TASK_CATEGORIES"
        :key="cat.key"
        class="flex items-center justify-between py-1"
      >
        <span class="text-sm text-slate-700 dark:text-slate-200">{{ cat.label }}</span>
        <el-switch
          :model-value="store.categoryEnabled(cat.key)"
          @update:model-value="(v: boolean) => store.setPref(cat.key, v)"
        />
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Loader2, CheckCircle2, XCircle, Info, AlertTriangle, AlertCircle } from 'lucide-vue-next';
import { ElMessage } from 'element-plus';
import { useNotificationStore, TASK_CATEGORIES } from '@/stores/notificationStore';
import type { AppNotification } from '@/api/notification';

const store = useNotificationStore();

const drawerVisible = computed({
  get: () => store.drawerOpen,
  set: (v: boolean) => (v ? store.openDrawer() : store.closeDrawer()),
});
const prefsVisible = computed({
  get: () => store.prefsDialogOpen,
  set: (v: boolean) => (v ? store.openPrefs() : store.closePrefs()),
});

const activeTab = ref<'notif' | 'task'>('notif');

// 打开抽屉时，默认切到「通知」并优先拉一次未读
watch(drawerVisible, (v) => {
  if (v) {
    activeTab.value = 'notif';
    store.fetchUnread();
  }
});

const onMarkRead = async (id: string) => {
  try {
    await store.markRead(id);
  } catch {
    ElMessage.error('标记已读失败');
  }
};

const onMarkAllRead = async () => {
  try {
    await store.markAllRead();
    ElMessage.success('已全部标记为已读');
  } catch {
    ElMessage.error('操作失败');
  }
};

const levelIcon = (level: string) => {
  switch (level) {
    case 'success': return CheckCircle2;
    case 'warning': return AlertTriangle;
    case 'error': return AlertCircle;
    default: return Info;
  }
};
const levelColor = (level: string) => {
  switch (level) {
    case 'success': return 'text-emerald-500';
    case 'warning': return 'text-amber-500';
    case 'error': return 'text-red-500';
    default: return 'text-primary-500';
  }
};
const typeLabel = (type: string) => {
  switch (type) {
    case 'UPDATE': return '更新';
    case 'SYSTEM': return '系统';
    case 'TASK': return '任务';
    default: return type;
  }
};
const bodyText = (body: any): string => {
  if (!body) return '';
  if (typeof body === 'string') return body;
  if (typeof body === 'object' && body.text) return String(body.text);
  return '';
};
const formatTime = (iso?: string | null) => {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const now = new Date();
  const diff = (now.getTime() - d.getTime()) / 1000;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return d.toLocaleDateString();
};
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
