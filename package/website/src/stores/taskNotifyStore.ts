import { defineStore } from 'pinia'
import { ref, computed, watch, onUnmounted } from 'vue'
import { CheckCircle2, XCircle, AlertTriangle, Inbox, Cog } from 'lucide-vue-next'
import { tasksApi, type Task } from '@/api/tasks'

const PREFS_KEY = 'trailsnap:task-notify-prefs'
const UNREAD_KEY = 'trailsnap:task-notify-unread'

// The 12 categories enumerated in the spec, plus an "other" bucket for any
// task type that is not on this list. Keep this in sync with the backend
// TaskType enum.
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
]

const CATEGORY_NAME_MAP: Record<string, string> = Object.fromEntries(
  TASK_CATEGORIES.map(c => [c.key, c.label])
)

const DEFAULT_PREFS: Record<string, boolean> = Object.fromEntries(
  TASK_CATEGORIES.map(c => [c.key, true])
)

function loadPrefs(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(PREFS_KEY)
    if (!raw) return { ...DEFAULT_PREFS }
    const parsed = JSON.parse(raw)
    return { ...DEFAULT_PREFS, ...parsed }
  } catch {
    return { ...DEFAULT_PREFS }
  }
}

function loadUnread(): { ids: string[] } {
  try {
    const raw = localStorage.getItem(UNREAD_KEY)
    if (!raw) return { ids: [] }
    return JSON.parse(raw) || { ids: [] }
  } catch {
    return { ids: [] }
  }
}

function persistUnread(ids: string[]) {
  try {
    localStorage.setItem(UNREAD_KEY, JSON.stringify({ ids }))
  } catch { /* quota */ }
}

export interface NotifyTask extends Task {
  notifiedAt?: string
}

export const useTaskNotifyStore = defineStore('taskNotify', () => {
  // ---- State ----
  const running = ref<NotifyTask[]>([])
  const completed = ref<NotifyTask[]>([])  // unread
  const failed = ref<NotifyTask[]>([])     // unread
  const ignored = ref<NotifyTask[]>([])    // dismissed failed
  const drawerOpen = ref(false)
  const prefsDialogOpen = ref(false)
  const prefs = ref<Record<string, boolean>>(loadPrefs())
  const desktopNotifications = ref<boolean>(
    typeof Notification !== 'undefined' && Notification.permission === 'granted'
  )
  const lastEventAt = ref<string | null>(null)
  // Tasks tracked by ID that are not yet present in `running` (e.g. from
  // agent-initiated calls). When the SSE brings them in we attach them to
  // the right group.
  const trackedIds = ref<Set<string>>(new Set())

  // ---- Persistence ----
  watch(prefs, (val) => {
    try { localStorage.setItem(PREFS_KEY, JSON.stringify(val)) } catch { /* ignore */ }
  }, { deep: true })

  // ---- Computed ----
  const unreadCount = computed(() => completed.value.length + failed.value.length)

  const categoryEnabled = (type: string) => {
    if (prefs.value[type] === undefined) return true
    return !!prefs.value[type]
  }

  // ---- Helpers ----
  const indexById = (list: NotifyTask[], id: string) =>
    list.findIndex(t => t.id === id)

  const upsertRunning = (task: NotifyTask) => {
    const idx = indexById(running.value, task.id)
    if (idx === -1) running.value.unshift(task)
    else running.value[idx] = { ...running.value[idx], ...task }
    // Cap to last 50
    if (running.value.length > 50) running.value = running.value.slice(0, 50)
  }

  const removeFromRunning = (id: string) => {
    running.value = running.value.filter(t => t.id !== id)
  }

  const handleEvent = (event: string, task: Task) => {
    if (!task || !task.id) return
    lastEventAt.value = task.updated_at || new Date().toISOString()
    const status = (task.status || '').toLowerCase()
    const type = task.type

    if (status === 'processing' || status === 'pending' || event === 'task.created') {
      upsertRunning({ ...task, notifiedAt: new Date().toISOString() } as NotifyTask)
      return
    }

    if (status === 'completed') {
      removeFromRunning(task.id)
      const exists = indexById(completed.value, task.id)
      if (exists === -1) {
        const item: NotifyTask = { ...task, notifiedAt: new Date().toISOString() }
        completed.value.unshift(item)
        if (completed.value.length > 50) completed.value = completed.value.slice(0, 50)
      }
      return
    }

    if (status === 'failed') {
      removeFromRunning(task.id)
      const exists = indexById(failed.value, task.id)
      if (exists === -1) {
        const item: NotifyTask = { ...task, notifiedAt: new Date().toISOString() }
        failed.value.unshift(item)
        if (failed.value.length > 50) failed.value = failed.value.slice(0, 50)
      }
      return
    }

    if (status === 'cancelled') {
      removeFromRunning(task.id)
    }
  }

  const markAsRead = (id: string) => {
    completed.value = completed.value.filter(t => t.id !== id)
    failed.value = failed.value.filter(t => t.id !== id)
    persistUnread([...completed.value, ...failed.value].map(t => t.id))
  }

  const markAllAsRead = () => {
    completed.value = []
    failed.value = []
    persistUnread([])
  }

  const ignoreFailed = (id: string) => {
    const idx = indexById(failed.value, id)
    if (idx === -1) return
    const [item] = failed.value.splice(idx, 1)
    ignored.value.unshift(item)
  }

  const openDrawer = () => { drawerOpen.value = true }
  const closeDrawer = () => { drawerOpen.value = false }
  const openPrefs = () => { prefsDialogOpen.value = true }
  const closePrefs = () => { prefsDialogOpen.value = false }

  const setPref = (key: string, value: boolean) => {
    prefs.value = { ...prefs.value, [key]: value }
  }

  const requestDesktopPermission = async () => {
    if (typeof Notification === 'undefined') return
    if (Notification.permission === 'granted') {
      desktopNotifications.value = true
      return
    }
    if (Notification.permission === 'denied') return
    const result = await Notification.requestPermission()
    desktopNotifications.value = result === 'granted'
  }

  /**
   * Track a task by id. The task will contribute to the bell unread count
   * (toast / native notification) when it eventually completes or fails.
   * The TaskManagement page and the agent use this to opt a task into
   * the "user-cares-about-it" set.
   */
  const track = (taskId: string) => {
    trackedIds.value.add(taskId)
  }

  const untrack = (taskId: string) => {
    trackedIds.value.delete(taskId)
  }

  return {
    // state
    running,
    completed,
    failed,
    ignored,
    drawerOpen,
    prefsDialogOpen,
    prefs,
    desktopNotifications,
    lastEventAt,
    // computed
    unreadCount,
    // actions
    handleEvent,
    markAsRead,
    markAllAsRead,
    ignoreFailed,
    openDrawer,
    closeDrawer,
    openPrefs,
    closePrefs,
    setPref,
    requestDesktopPermission,
    track,
    untrack,
  }
})

function formatDuration(ms: number): string {
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec} 秒`
  const min = Math.floor(sec / 60)
  const rem = sec % 60
  if (min < 60) return `${min} 分 ${rem} 秒`
  const hr = Math.floor(min / 60)
  const remMin = min % 60
  return `${hr} 小时 ${remMin} 分`
}