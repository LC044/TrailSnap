<template>
  <div v-if="shouldShow" class="task-status">
    <el-popover
      v-model:visible="expanded"
      trigger="click"
      placement="right-end"
      popper-class="ts-liquid-glass"
      :width="320"
      :offset="14"
      :show-arrow="false"
      :disabled="isCollapsed"
      :popper-style="{ maxWidth: 'calc(100vw - 24px)' }"
      @after-leave="focusTrigger"
    >
      <template #reference>
        <button
          ref="triggerRef"
          type="button"
          class="task-status-trigger"
          :class="{ 'is-collapsed': isCollapsed, 'is-open': expanded }"
          :aria-expanded="!isCollapsed && expanded"
          :aria-haspopup="isCollapsed ? undefined : 'dialog'"
          :aria-label="`后台任务，${formatCount(totalPending)} 项待处理${totalFailed ? `，${formatCount(totalFailed)} 项失败` : ''}`"
          :title="isCollapsed ? '后台任务 · 查看任务管理' : undefined"
          @click="isCollapsed && toggleExpand()"
          @keydown.esc.stop="closePanel"
        >
          <span class="task-status-icon">
            <Loader2 v-if="hasPending" class="h-5 w-5 text-primary-500 motion-safe:animate-spin" />
            <AlertCircle v-else-if="totalFailed > 0" class="h-5 w-5 task-danger" />
            <CheckCircle2 v-else class="h-5 w-5 text-primary-500" />
            <span v-if="isCollapsed && hasPending && totalFailed > 0" class="task-failure-dot" />
          </span>
          <span v-if="!isCollapsed" class="task-status-copy">
            <span class="task-status-heading">
              <span>后台任务</span>
              <ChevronRight class="h-4 w-4 task-muted" />
            </span>
            <span class="task-status-summary">
              <span class="task-muted">{{ hasPending ? `${compactCount(totalPending)} 项待处理` : totalFailed ? '需要处理' : '处理完成' }}</span>
              <span v-if="totalFailed > 0" class="task-danger inline-flex items-center gap-1">
                <AlertCircle class="h-3 w-3" />{{ compactCount(totalFailed) }} 项失败
              </span>
            </span>
          </span>
        </button>
      </template>

      <section class="task-panel" role="dialog" aria-label="后台任务详情" @keydown.esc.stop="closePanel">
        <header class="task-panel-header">
          <h2 class="text-sm font-semibold">后台任务</h2>
          <button type="button" class="task-panel-close" aria-label="关闭任务详情" @click="closePanel"><X class="h-4 w-4" /></button>
        </header>
        <div class="task-panel-list">
          <div v-for="cat in detailCategories" :key="cat.category" class="task-category">
            <div class="flex items-center justify-between gap-3">
              <span class="text-sm font-medium min-w-0 break-words">{{ shortTaskName(cat.task_name) }}</span>
              <span class="task-muted text-xs shrink-0">{{ cat.status === 'paused' ? '已暂停' : cat.waiting_reason ? '等待中' : cat.pending > 0 ? '处理中' : '待处理失败' }}</span>
            </div>
            <div class="task-muted mt-1 text-xs tabular-nums">{{ formatCount(cat.pending) }} 项待处理<span v-if="cat.failed > 0" class="task-danger"> · {{ formatCount(cat.failed) }} 项失败</span></div>
            <p v-if="cat.waiting_reason" class="task-muted mt-1 text-xs break-words">{{ cat.waiting_reason }}</p>
          </div>
          <p v-if="detailCategories.length === 0" class="task-muted py-4 text-center text-sm">所有后台任务已处理完成</p>
        </div>
        <footer class="task-panel-footer">
          <button v-if="totalFailed > 0" type="button" class="task-manage task-danger" @click="goToTasks">查看并处理 {{ formatCount(totalFailed) }} 项失败<ArrowUpRight class="h-4 w-4" /></button>
          <button v-else type="button" class="task-manage text-primary-500" @click="goToTasks">查看全部任务<ArrowUpRight class="h-4 w-4" /></button>
        </footer>
      </section>
    </el-popover>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Loader2, ChevronRight, CheckCircle2, AlertCircle, ArrowUpRight, X } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { createTaskRefresh } from '@/utils/taskRefresh'
import { tasksApi } from '@/api/tasks'
import { useNotificationStore } from '@/stores/notificationStore'

interface TaskCategoryStatus {
  category: string
  task_name: string
  pending: number
  failed: number
  status: 'active' | 'paused'
  waiting_reason?: string
}

const props = defineProps<{
  isCollapsed: boolean
}>()

const router = useRouter()
const store = useNotificationStore()

const triggerRef = ref<HTMLButtonElement | null>(null)
let returnFocus = false
const focusTrigger = () => {
  if (returnFocus) triggerRef.value?.focus()
  returnFocus = false
}
const closePanel = () => {
  returnFocus = true
  expanded.value = false
}
const expanded = ref(false)
const groupedStatus = ref<TaskCategoryStatus[]>([])
// 拉取在途标记：防止 SSE 事件在请求中途触发并发刷新
let fetchInFlight = false
let pendingRefresh = false

const activeCategories = computed(() => {
  return groupedStatus.value.filter(cat => cat.status !== 'paused' && cat.pending > 0)
})

const detailCategories = computed(() => groupedStatus.value.filter(cat => cat.pending > 0 || cat.failed > 0))
const formatCount = (count: number) => count.toLocaleString('zh-CN')
const compactCount = (count: number) => count >= 10000
  ? `${(count / 10000).toFixed(1).replace(/\.0$/, '')} 万`
  : formatCount(count)
const shortTaskName = (name: string) => name === '大模型智能分析' ? '智能分析' : name

const totalPending = computed(() => {
  return activeCategories.value.reduce((sum, cat) => sum + cat.pending, 0)
})

const totalFailed = computed(() => {
  return groupedStatus.value.reduce((sum, cat) => sum + cat.failed, 0)
})

const hasPending = computed(() => totalPending.value > 0)
const wasPending = ref(false)
const showSuccess = ref(false)
let successTimer: number | null = null
const shouldShow = computed(() => hasPending.value || totalFailed.value > 0 || showSuccess.value)

const fetchStatus = async () => {
  try {
    const data = await tasksApi.getGroupedStatus()
    const previousFailed = totalFailed.value
    groupedStatus.value = data
    if (totalFailed.value > previousFailed) {
      ElMessage.warning(`${totalFailed.value} 个后台任务失败，可在任务管理查看原因并重试`)
      showSuccess.value = false
    }

    if (totalPending.value > 0) {
      wasPending.value = true
      showSuccess.value = false
      if (successTimer) {
        window.clearTimeout(successTimer)
        successTimer = null
      }
    } else if (wasPending.value && totalPending.value === 0) {
      // 从有任务过渡到全部完成
      wasPending.value = false
      if (successTimer) window.clearTimeout(successTimer)
      successTimer = null
      if (totalFailed.value === 0 && groupedStatus.value.every(cat => cat.pending === 0)) {
        ElMessage.success('所有后台任务已处理完成')
        showSuccess.value = true
        successTimer = window.setTimeout(() => {
          showSuccess.value = false
        }, 3000)
      } else {
        showSuccess.value = false
      }
    }
  } catch {
    // Ignore
  }
}

const goToTasks = () => {
  expanded.value = false
  router.push({ path: '/settings', query: { tab: 'tasks' } })
}

const refresh = async () => {
  if (fetchInFlight) {
    pendingRefresh = true
    return
  }
  fetchInFlight = true
  try {
    await fetchStatus()
  } finally {
    fetchInFlight = false
  }
  if (pendingRefresh) {
    pendingRefresh = false
    refresh()
  }
}

const toggleExpand = () => {
  if (props.isCollapsed) {
    goToTasks()
    return
  }
  expanded.value = !expanded.value
}

// Refresh at most once per four seconds, even during a continuous event stream.
const taskRefresh = createTaskRefresh(() => { void refresh() })
watch(() => store.taskRevision, taskRefresh.schedule)
let fallbackTimer: number | undefined

onMounted(() => {
  taskRefresh.schedule()
  fallbackTimer = window.setInterval(taskRefresh.schedule, 60000)
})

onUnmounted(() => {
  taskRefresh.cancel()
  window.clearInterval(fallbackTimer)
  if (successTimer !== null) window.clearTimeout(successTimer)
})
</script>

<style scoped>
.task-status { color: var(--ts-color-text); }
.task-muted { color: var(--ts-color-text-secondary); }
.task-danger { color: var(--ts-color-danger); }
.task-status-trigger {
  display: flex; align-items: center; gap: 12px; width: 100%; padding: 10px;
  border-radius: var(--ts-radius-control); text-align: left;
  transition: background-color var(--ts-motion-fast) ease;
}
.task-status-trigger:hover, .task-status-trigger.is-open { background: var(--ts-color-surface-muted); }
.task-status-trigger:focus-visible, .task-panel button:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 2px; }
.task-status-icon { position: relative; display: flex; align-items: center; justify-content: center; flex-shrink: 0; width: 24px; height: 24px; }
.task-failure-dot { position: absolute; top: -1px; right: -1px; width: 7px; height: 7px; border-radius: 50%; background: var(--ts-color-danger); box-shadow: 0 0 0 2px var(--ts-color-surface); }
.task-status-copy { flex: 1; min-width: 0; }
.task-status-heading { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }
.task-status-summary { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 2px 8px; margin-top: 4px; font-size: 11px; font-variant-numeric: tabular-nums; }
.task-status-trigger.is-collapsed { justify-content: center; }
.task-panel { color: var(--ts-color-text); }
.task-panel-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-bottom: 8px; }
.task-panel-close { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 8px; color: var(--ts-color-text-secondary); }
.task-panel-close:hover { background: var(--ts-color-surface-muted); }
.task-panel-list { max-height: min(360px, 50vh); overflow-y: auto; overscroll-behavior: contain; }
.task-category { padding: 12px 0; }
.task-category + .task-category { border-top: 1px solid var(--ts-color-divider); }
.task-panel-footer { border-top: 1px solid var(--ts-color-divider); padding-top: 8px; }
.task-manage { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; min-height: 36px; font-size: 12px; border-radius: 8px; }
.task-manage:hover { background: var(--ts-color-surface-muted); }
</style>
