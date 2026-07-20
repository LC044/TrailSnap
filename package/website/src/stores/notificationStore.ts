import { defineStore } from 'pinia';
import { ref, computed, watch } from 'vue';
import { notificationsApi, type AppNotification } from '@/api/notification';
import type { Task } from '@/api/tasks';

const PREFS_KEY = 'trailsnap:task-notify-prefs';

// The 12 task categories (kept in sync with the backend TaskType enum).
export const TASK_CATEGORIES: { key: string; label: string }[] = [
  { key: 'RECOGNIZE_FACE', label: '人脸识别' },
  { key: 'OCR', label: '文字识别' },
  { key: 'IMAGE_EMBEDDING', label: '图片特征提取' },
  { key: 'GENERATE_THUMBNAIL', label: '生成缩略图' },
  { key: 'RECOGNIZE_TICKET', label: '车票识别' },
  { key: 'FIND_DUPLICATE_PHOTOS', label: '重复照片' },
  { key: 'SIMILAR_PHOTO_CLUSTERING', label: '相似照片' },
  { key: 'CLASSIFY_IMAGE', label: '场景识别' },
  { key: 'EXTRACT_METADATA', label: '元数据提取' },
  { key: 'PROCESS_BASIC', label: '基本处理' },
  { key: 'ORGANIZE_PHOTOS', label: '文件整理' },
  { key: 'BATCH_RENAME', label: '批量重命名' }
];

const CATEGORY_NAME_MAP: Record<string, string> = Object.fromEntries(
  TASK_CATEGORIES.map(c => [c.key, c.label])
);

const DEFAULT_PREFS: Record<string, boolean> = Object.fromEntries(
  TASK_CATEGORIES.map(c => [c.key, true])
);

function loadPrefs(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return { ...DEFAULT_PREFS };
    const parsed = JSON.parse(raw);
    return { ...DEFAULT_PREFS, ...parsed };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

export interface NotifyTask extends Task {
  notifiedAt?: string;
}

export const useNotificationStore = defineStore('notification', () => {
  // ---- 通知收件箱（服务端持久化，未读）----
  const notifications = ref<AppNotification[]>([]);

  // ---- 任务 live 态（内存，不落库）----
  const taskRunning = ref<NotifyTask[]>([]);
  const taskCompleted = ref<NotifyTask[]>([]);   // 未读完成
  const taskFailed = ref<NotifyTask[]>([]);      // 未读失败
  const taskIgnored = ref<NotifyTask[]>([]);     // 已忽略失败

  // ---- UI 状态 ----
  const drawerOpen = ref(false);
  const prefsDialogOpen = ref(false);
  const prefs = ref<Record<string, boolean>>(loadPrefs());
  const desktopNotifications = ref<boolean>(
    typeof Notification !== 'undefined' && Notification.permission === 'granted'
  );
  const lastEventAt = ref<string | null>(null);
  const trackedIds = ref<Set<string>>(new Set());

  // ---- 持久化 prefs ----
  watch(prefs, (val) => {
    try { localStorage.setItem(PREFS_KEY, JSON.stringify(val)) } catch { /* ignore */ }
  }, { deep: true });

  // ---- 计数 ----
  // 铃铛未读 = 持久化通知未读 + 内存任务完成/失败未读
  const unreadCount = computed(() =>
    notifications.value.length + taskCompleted.value.length + taskFailed.value.length
  );

  const categoryEnabled = (type: string) => {
    if (prefs.value[type] === undefined) return true;
    return !!prefs.value[type];
  };

  // ---- 任务 live 态 helpers ----
  const indexById = (list: NotifyTask[], id: string) =>
    list.findIndex(t => t.id === id);

  const upsertRunning = (task: NotifyTask) => {
    const idx = indexById(taskRunning.value, task.id);
    if (idx === -1) taskRunning.value.unshift(task);
    else taskRunning.value[idx] = { ...taskRunning.value[idx], ...task };
    if (taskRunning.value.length > 50) taskRunning.value = taskRunning.value.slice(0, 50);
  };

  const removeFromRunning = (id: string) => {
    taskRunning.value = taskRunning.value.filter(t => t.id !== id);
  };

  // ---- 桌面通知 ----
  const fireDesktop = (title: string, body?: string) => {
    if (!desktopNotifications.value || typeof Notification === 'undefined') return;
    try { new Notification(title, body ? { body } : undefined) } catch { /* ignore */ }
  };

  // ---- 事件分发 ----
  const handleTaskEvent = (event: string, task: Task) => {
    if (!task || !task.id) return;
    lastEventAt.value = task.updated_at || new Date().toISOString();
    const status = (task.status || '').toLowerCase();
    const type = task.type;
    const enabled = !type || categoryEnabled(type);

    if (status === 'processing' || status === 'pending' || event === 'task.created') {
      upsertRunning({ ...task, notifiedAt: new Date().toISOString() } as NotifyTask);
      return;
    }
    if (status === 'completed') {
      removeFromRunning(task.id);
      if (enabled) {
        const exists = indexById(taskCompleted.value, task.id);
        if (exists === -1) {
          const item: NotifyTask = { ...task, notifiedAt: new Date().toISOString() };
          taskCompleted.value.unshift(item);
          if (taskCompleted.value.length > 50) taskCompleted.value = taskCompleted.value.slice(0, 50);
          if (trackedIds.value.has(task.id)) fireDesktop('任务完成', task.type);
        }
      }
      return;
    }
    if (status === 'failed') {
      removeFromRunning(task.id);
      if (enabled) {
        const exists = indexById(taskFailed.value, task.id);
        if (exists === -1) {
          const item: NotifyTask = { ...task, notifiedAt: new Date().toISOString() };
          taskFailed.value.unshift(item);
          if (taskFailed.value.length > 50) taskFailed.value = taskFailed.value.slice(0, 50);
          if (trackedIds.value.has(task.id)) fireDesktop('任务失败', task.error || task.type);
        }
      }
      return;
    }
    if (status === 'cancelled') {
      removeFromRunning(task.id);
    }
  };

  const handleNotificationEvent = (event: string, data: AppNotification) => {
    if (!data || !data.id) return;
    lastEventAt.value = data.created_at || new Date().toISOString();
    if (event === 'notification.read') {
      notifications.value = notifications.value.filter(n => n.id !== data.id);
      return;
    }
    // notification.created
    const exists = indexById(notifications.value as any, data.id);
    if (exists === -1) {
      notifications.value.unshift(data);
      fireDesktop(data.title, typeof data.body === 'string' ? data.body : undefined);
    }
  };

  const handleEvent = (event: string, data: any) => {
    if (event.startsWith('task.')) {
      handleTaskEvent(event, data as Task);
    } else if (event.startsWith('notification.')) {
      handleNotificationEvent(event, data as AppNotification);
    }
  };

  // ---- 通知 actions ----
  const fetchUnread = async () => {
    try {
      const rows = await notificationsApi.list({ unread: true, limit: 100 });
      if (Array.isArray(rows)) notifications.value = rows;
    } catch { /* ignore */ }
  };

  const markRead = async (id: string) => {
    const res = await notificationsApi.markRead(id);
    notifications.value = notifications.value.filter(n => n.id !== id);
    return res;
  };

  const markAllRead = async () => {
    await notificationsApi.markAllRead();
    notifications.value = [];
  };

  // ---- 任务 actions ----
  const dismissTask = (id: string) => {
    taskCompleted.value = taskCompleted.value.filter(t => t.id !== id);
    taskFailed.value = taskFailed.value.filter(t => t.id !== id);
  };

  const dismissAllTasks = () => {
    taskCompleted.value = [];
    taskFailed.value = [];
  };

  const ignoreFailed = (id: string) => {
    const idx = indexById(taskFailed.value, id);
    if (idx === -1) return;
    const [item] = taskFailed.value.splice(idx, 1);
    taskIgnored.value.unshift(item);
  };

  const openDrawer = () => { drawerOpen.value = true };
  const closeDrawer = () => { drawerOpen.value = false };
  const openPrefs = () => { prefsDialogOpen.value = true };
  const closePrefs = () => { prefsDialogOpen.value = false };

  const setPref = (key: string, value: boolean) => {
    prefs.value = { ...prefs.value, [key]: value };
  };

  const requestDesktopPermission = async () => {
    if (typeof Notification === 'undefined') return;
    if (Notification.permission === 'granted') {
      desktopNotifications.value = true;
      return;
    }
    if (Notification.permission === 'denied') return;
    const result = await Notification.requestPermission();
    desktopNotifications.value = result === 'granted';
  };

  const track = (taskId: string) => { trackedIds.value.add(taskId) };
  const untrack = (taskId: string) => { trackedIds.value.delete(taskId) };

  return {
    // state
    notifications,
    taskRunning,
    taskCompleted,
    taskFailed,
    taskIgnored,
    drawerOpen,
    prefsDialogOpen,
    prefs,
    desktopNotifications,
    lastEventAt,
    // computed
    unreadCount,
    // helpers
    categoryEnabled,
    CATEGORY_NAME_MAP,
    // event dispatch
    handleEvent,
    // notification actions
    fetchUnread,
    markRead,
    markAllRead,
    // task actions
    dismissTask,
    dismissAllTasks,
    ignoreFailed,
    // ui
    openDrawer,
    closeDrawer,
    openPrefs,
    closePrefs,
    setPref,
    requestDesktopPermission,
    track,
    untrack,
  };
});
