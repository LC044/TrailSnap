<template>
  <div class="task-management ts-settings-page">
    <SettingsPageHeader title="后台任务" description="查看任务队列，处理失败项与暂停的任务">
      <template #actions>
        <button type="button" class="ts-icon-button ts-button-secondary" aria-label="刷新任务状态" :disabled="loading" @click="fetchTasks">
          <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': loading }" />
        </button>
      </template>
    </SettingsPageHeader>

    <section class="task-overview ts-surface ts-settings-panel" :class="{ 'task-overview-alert': summary.failed > 0 }" aria-label="任务队列总览">
      <div v-if="loading && !groupedTasks.length" class="py-4 ts-muted" role="status">正在加载任务…</div>
      <div v-else-if="loadFailed" role="alert">
        <h2 class="ts-section-title">暂时无法获取任务状态</h2>
        <p class="ts-muted mt-2 text-sm">请重新加载。已有任务不会因此停止；下方信息可能尚未更新。</p>
        <button type="button" class="ts-button ts-button-secondary mt-4" :disabled="loading" @click="fetchTasks">重新加载</button>
      </div>
      <template v-else>
        <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
          <div class="flex min-w-0 items-start gap-3">
            <span class="task-overview-icon" :class="{ 'task-has-failures': summary.failed > 0 }">
              <AlertCircle v-if="summary.failed" class="h-6 w-6" />
              <Clock3 v-else-if="summary.pending" class="h-6 w-6" />
              <CheckCircle2 v-else class="h-6 w-6" />
            </span>
            <h2 class="ts-section-title">{{ overviewTitle }}</h2>
          </div>
          <button v-if="summary.failed" type="button" class="ts-button ts-button-sm task-failure-cta" :aria-label="`查看并处理 ${formatCount(summary.failed)} 项失败任务`" @click="taskFilter = 'failed'">
            处理失败项 <span class="tabular-nums">{{ formatCount(summary.failed) }}</span> <ChevronRight class="h-4 w-4" />
          </button>
        </div>
        <!-- 状态摘要即筛选：胶囊计数与下方列表 taskFilter 联动 -->
        <div class="task-summary-row mt-5" role="group" aria-label="按状态筛选任务">
          <button v-for="statusFilter in summaryFilters" :key="statusFilter.value" type="button"
            class="task-summary-chip" :class="{ 'task-chip-active': taskFilter === statusFilter.value }"
            :aria-pressed="taskFilter === statusFilter.value" :aria-label="`${statusFilter.label} ${formatCount(statusFilter.count)}，${taskFilter === statusFilter.value ? '已选中' : '点击筛选'}`"
            @click="taskFilter = taskFilter === statusFilter.value && statusFilter.value !== 'all' ? 'all' : statusFilter.value">
            <span class="task-chip-dot" :class="`task-dot-${statusFilter.value}`" aria-hidden="true" />
            <span>{{ statusFilter.label }}</span>
            <span class="tabular-nums">{{ formatCount(statusFilter.count) }}</span>
          </button>
        </div>
      </template>
    </section>

    <section class="task-groups" aria-labelledby="task-list-title">
      <h2 id="task-list-title" class="ts-section-title mb-3">{{ filteredTitle }}</h2>

      <!-- 需要关注：失败 / 等待条件 / 已暂停 -->
      <section v-if="attentionTasks.length" class="task-tier" aria-label="需要关注">
        <h3 class="task-tier-title task-tier-attention">{{ tierLabels.attention }}</h3>
        <div class="task-list ts-surface overflow-hidden" :aria-busy="loading">
          <article v-for="cat in attentionTasks" :key="cat.category" class="task-row" :class="`task-row-${getTaskState(cat)}`">
            <TaskRowContent v-bind="rowBindings(cat)" />
          </article>
        </div>
      </section>

      <!-- 进行中：有待处理且未暂停 -->
      <section v-if="progressTasks.length" class="task-tier" aria-label="进行中">
        <h3 class="task-tier-title">{{ tierLabels.progress }}</h3>
        <div class="task-list ts-surface overflow-hidden" :aria-busy="loading">
          <article v-for="cat in progressTasks" :key="cat.category" class="task-row" :class="`task-row-${getTaskState(cat)}`">
            <TaskRowContent v-bind="rowBindings(cat)" />
          </article>
        </div>
      </section>

      <!-- 空闲类型：默认折叠为一行摘要 -->
      <section v-if="idleCount > 0" class="task-tier" aria-label="暂无任务">
        <div v-if="!idleExpanded" class="ts-surface">
          <button type="button" class="task-idle-summary" :aria-expanded="false" aria-controls="task-idle-list" @click="idleExpanded = true">
            <CheckCircle2 class="h-5 w-5 shrink-0 ts-muted" />
            <span class="min-w-0 flex-1 text-left">{{ tierLabels.idle }}（{{ idleCount }} 类）</span>
            <span class="task-idle-names ts-muted hidden truncate md:block">{{ idleNames }}</span>
            <ChevronDown class="h-4 w-4 shrink-0 ts-muted" />
          </button>
        </div>
        <template v-else>
          <div class="mb-3 flex items-center justify-between gap-3">
            <h3 class="task-tier-title">{{ tierLabels.idle }} · {{ idleCount }} 类</h3>
            <button type="button" class="task-idle-collapse min-h-11 text-sm ts-muted" :aria-expanded="true" aria-controls="task-idle-list" @click="idleExpanded = false">收起</button>
          </div>
          <div id="task-idle-list" class="task-list ts-surface overflow-hidden">
            <article v-for="cat in idleTasks" :key="cat.category" class="task-row task-row-idle">
              <TaskRowContent v-bind="rowBindings(cat)" />
            </article>
          </div>
        </template>
      </section>

      <p v-if="!loading && !loadFailed && !visibleTasks.length" class="ts-surface ts-settings-panel text-center ts-muted text-sm">
        {{ taskFilter === 'all' ? '暂无处理类型' : `没有${taskFilters.find(filter => filter.value === taskFilter)?.label}的处理类型` }}
      </p>
    </section>


    <details class="task-performance ts-surface">
      <summary class="flex cursor-pointer items-center gap-3 p-4 md:p-6">
        <Settings2 class="h-5 w-5 shrink-0 ts-muted" />
        <span class="min-w-0 flex-1"><span class="block text-[15px] font-semibold">后台处理性能</span><span class="ts-muted mt-1 block text-sm">调整处理模式与快速模式，不影响任务列表的查看</span></span>
        <ChevronDown class="task-performance-chevron h-4 w-4 shrink-0 ts-muted" />
      </summary>
      <div class="border-t ts-divider p-4 md:p-6">
        <BasicSettings category="tasks" embedded>
          <template #task-options>
            <SettingsFormRow inline label="快速模式" description="同时调度不同类型的任务（CPU/IO），开启后可能增加资源占用。修改立即生效。">
              <el-switch v-model="fastMode" aria-label="快速模式" :disabled="loading || loadFailed || savingFastMode" @change="handleFastModeChange" />
            </SettingsFormRow>
          </template>
        </BasicSettings>
      </div>
    </details>
    <FailedTasksDialog v-model="failedTasksVisible" :category="failedCategory" :title="failedCategoryTitle" @retried="fetchTasks" @ignored="fetchTasks" />
  </div>
</template>

<script setup lang="ts">
import BasicSettings from './BasicSettings.vue'
import SettingsPageHeader from '@/components/ui/SettingsPageHeader.vue'
import SettingsFormRow from '@/components/ui/SettingsFormRow.vue'
import TaskRowContent from './components/TaskRowContent.vue'
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { createTaskRefresh } from '@/utils/taskRefresh'
import { tasksApi } from '@/api/tasks'
import { ElMessage, ElMessageBox } from 'element-plus'
import { AlertCircle, CheckCircle2, ChevronDown, ChevronRight, Clock3, RefreshCw, Settings2 } from 'lucide-vue-next'
import FailedTasksDialog from '@/components/FailedTasksDialog.vue'
import { useNotificationStore } from '@/stores/notificationStore'
import { filterTaskGroups, getTaskState, summarizeTaskGroups, taskFilters, type TaskFilter, type TaskGroup } from '@/utils/taskPresentation'

const groupedTasks = ref<TaskGroup[]>([])
const isMobile = useMediaQuery('(max-width: 767px)')
const taskFilter = ref<TaskFilter>('all')
const summary = computed(() => summarizeTaskGroups(groupedTasks.value))
const visibleTasks = computed(() => filterTaskGroups(groupedTasks.value, taskFilter.value))
const formatCount = (count: number) => count.toLocaleString('zh-CN')

// —— 三层分组：需要关注（失败/等待/暂停）、进行中、空闲 ——
const isAttention = (task: TaskGroup) => {
  const state = getTaskState(task)
  return state === 'failed' || state === 'waiting' || state === 'paused'
}
const attentionTasks = computed(() => visibleTasks.value.filter(isAttention))
const progressTasks = computed(() => visibleTasks.value.filter(task => !isAttention(task) && getTaskState(task) === 'pending'))
const idleTasks = computed(() => visibleTasks.value.filter(task => getTaskState(task) === 'idle'))
const idleCount = computed(() => idleTasks.value.length)
const idleNames = computed(() => idleTasks.value.map(task => task.task_name).join('、'))
const idleExpanded = ref(false)
const tierLabels = { attention: '需要关注', progress: '进行中', idle: '暂无任务' }

const rowBindings = (cat: TaskGroup) => ({
  task: cat,
  expanded: expandedTask.value === cat.category,
  menuOpen: activeMenu.value === cat.category,
  disabled: loadFailed.value,
  onToggleExpand: () => { expandedTask.value = expandedTask.value === cat.category ? '' : cat.category },
  onShowFailed: () => showFailedTasks(cat.category),
  onToggleMenu: () => { activeMenu.value = activeMenu.value === cat.category ? '' : cat.category },
  onUpdateMenu: (value: boolean) => { activeMenu.value = value ? cat.category : '' },
  onCategoryCommand: (command: string) => { void handleCategoryCommand(cat.category, command) },
})

const overviewTitle = computed(() => {
  if (summary.value.failed) return '有失败任务需要处理'
  if (summary.value.pending) return '还有任务待处理'
  return '当前没有待处理任务'
})

// 状态摘要胶囊：与 taskFilter 一一对应，计数分别为任务数与类目数
const summaryFilters = computed(() => [
  { value: 'all' as TaskFilter, label: '全部', count: groupedTasks.value.length },
  { value: 'pending' as TaskFilter, label: '进行中', count: filterTaskGroups(groupedTasks.value, 'pending').length },
  { value: 'failed' as TaskFilter, label: '失败', count: summary.value.failed },
  { value: 'paused' as TaskFilter, label: '已暂停', count: summary.value.paused },
])

const filteredTitle = computed(() => {
  if (taskFilter.value === 'all') return '处理类型'
  const label = taskFilters.find(filter => filter.value === taskFilter.value)?.label ?? ''
  return `${label}类型`
})

const fastMode = ref(false)
const savingFastMode = ref(false)
const notifyStore = useNotificationStore()

const failedTasksVisible = ref(false)
const failedCategory = ref('')
const failedCategoryTitle = ref('')
const activeMenu = ref('')
const expandedTask = ref('')
const loading = ref(true)
const loadFailed = ref(false)
let fetching = false

const fetchTasks = async () => {
    if (fetching) return
    fetching = true
    loading.value = true
    try {
        const [groups, globalStatus] = await Promise.all([tasksApi.getGroupedStatus(), tasksApi.getGlobalStatus()])
        groupedTasks.value = groups
        loadFailed.value = false
        if (!savingFastMode.value && globalStatus && typeof globalStatus.fast_mode !== 'undefined') {
            fastMode.value = globalStatus.fast_mode === true || globalStatus.fast_mode === 'True'
        }
    } catch (e) {
        loadFailed.value = true
        console.error("Failed to fetch tasks", e)
    } finally {
        loading.value = false
        fetching = false
    }
}

const handleFastModeChange = async (val: boolean) => {
    savingFastMode.value = true
    try {
        await tasksApi.toggleFastMode(val)
        ElMessage.success(val ? '快速模式已开启' : '快速模式已关闭')
    } catch (e) {
        ElMessage.error('设置失败')
        fastMode.value = !val
    } finally {
        savingFastMode.value = false
    }
}

const handleCategoryCommand = async (category: string, command: string) => {
    if (command === 'recover_tickets') {
        await recoverTickets()
    } else if (command === 'pause') {
        await pauseCategory(category)
    } else if (command === 'resume') {
        await resumeCategory(category)
    } else if (command === 'retry') {
        await retryCategoryFailed(category)
    } else if (command === 'scan_missing') {
        confirmScanMissing(category)
    } else if (command === 'rebuild') {
        confirmCategoryRebuild(category)
    } else if (command === 'delete_failed') {
        confirmDeleteFailed(category)
    }
}

const recoveringTickets = ref(false)
const recoverTickets = async () => {
    try {
        await ElMessageBox.confirm('重新识别旧版标记完成但没有保存票据的照片（也可能包含未识别出票据的照片），保留已有票据。是否继续？', '恢复票据识别', { type: 'info' })
    } catch { return }
    if (recoveringTickets.value) return
    recoveringTickets.value = true
    try {
        const result = await tasksApi.recoverTicketRecognition()
        ElMessage.info(result.count ? `已加入 ${result.count} 张照片的恢复识别任务，请关注处理结果` : '没有需要恢复的照片，已有任务可在失败列表重试')
        await fetchTasks()
    } catch { ElMessage.error('恢复任务创建失败，请重试') }
    finally { recoveringTickets.value = false }
}

const retryCategoryFailed = async (category: string) => {
    const types = [category]
    if (!types) return
    try {
        const res = await tasksApi.retryAllFailedTasks(types)
        ElMessage.success(`已重试 ${res.count} 个失败任务`)
        fetchTasks()
    } catch (e) {
        ElMessage.error('操作失败')
    }
}

const confirmDeleteFailed = (category: string) => {
    ElMessageBox.confirm(
        `确定要删除 "${formatCategory(category)}" 类别下的所有失败任务吗？此操作不可恢复。`,
        '警告',
        {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning',
        }
    ).then(() => {
        deleteCategoryFailed(category)
    })
}

const deleteCategoryFailed = async (category: string) => {
    const types = [category]
    if (!types) return
    try {
        const res = await tasksApi.deleteFailedTasks(types)
        ElMessage.success(`已删除 ${res.count} 个失败任务`)
        fetchTasks()
    } catch (e) {
        ElMessage.error('操作失败')
    }
}

const confirmScanMissing = (category: string) => {
    ElMessageBox.confirm(
        `此操作将扫描并为 "${formatCategory(category)}" 类别下缺失数据的照片创建任务。是否继续？`,
        '提示',
        {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'info',
        }
    ).then(() => {
        triggerScanMissing(category)
    })
}

const triggerScanMissing = async (category: string) => {
    const types = [category]
    if (!types) return
    try {
        for (const type of types) {
            // force: false indicates scanning for missing data only
            await tasksApi.createTask(type, { scope: 'all', force: false })
        }
        ElMessage.success('已触发缺失数据扫描')
        fetchTasks()
    } catch (e) {
        ElMessage.error('操作部分失败，请查看日志')
    }
}

const confirmCategoryRebuild = (category: string) => {
     ElMessageBox.confirm(
        `此操作将重新创建 "${formatCategory(category)}" 类别下的所有任务，可能会消耗大量时间。是否继续？`,
        '警告',
        {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning',
        }
    ).then(() => {
        forceRebuildCategory(category)
    })
}

const forceRebuildCategory = async (category: string) => {
    const types = [category]
    if (!types) return
    try {
        for (const type of types) {
             // Skip some legacy or non-trigger types if necessary, but "Force Rebuild" implies all
             // For scanning, we usually just need SCAN_FOLDER, but others might be useful to force re-run
             // Actually, SCAN_FOLDER triggers others.
             // But if we want to rebuild thumbnails specifically, we trigger GENERATE_THUMBNAIL.
             // Let's trigger all defined types for the category.
            await tasksApi.createTask(type, { scope: 'all', force: true })
        }
        ElMessage.success('已触发任务重做')
        fetchTasks()
    } catch (e) {
        ElMessage.error('操作部分失败，请查看日志')
    }
}

const showFailedTasks = (category: string) => {
    failedCategory.value = category
    failedCategoryTitle.value = groupedTasks.value.find(task => task.category === category)?.task_name || formatCategory(category)
    failedTasksVisible.value = true
}

const pauseCategory = async (category: string) => {
    try {
        await tasksApi.pauseCategory(category)
        notifyStore.handleEvent('task.category', { category, status: 'paused' })
        ElMessage.success('已暂停')
        fetchTasks()
    } catch (e) {
        ElMessage.error('暂停失败')
    }
}

const resumeCategory = async (category: string) => {
    try {
        await tasksApi.resumeCategory(category)
        notifyStore.handleEvent('task.category', { category, status: 'active' })
        ElMessage.success('已继续')
        fetchTasks()
    } catch (e) {
        ElMessage.error('操作失败')
    }
}

const formatCategory = (cat: string) => {
    const group = groupedTasks.value.find(task => task.category === cat)
    if (group) return group.task_name
    const names: Record<string, string> = {
        'scanning': '扫描与基础处理',
        'metadata': '元数据提取',
        'face': '人脸识别',
        'classification': '场景识别',
        'ai': '大模型智能分析',
        'ocr': '文字识别',
        'tickets': '车票识别'
    }
    return names[cat] || cat
}

// Shared API caching avoids duplicate summary reads from the sidebar.
let taskPollTimer: number | null = null
const taskRefresh = createTaskRefresh(() => { void fetchTasks() })
watch(() => notifyStore.taskRevision, taskRefresh.schedule)

onMounted(() => {
    taskRefresh.schedule()
    taskPollTimer = window.setInterval(taskRefresh.schedule, 60000)
})

onUnmounted(() => {
    if (taskPollTimer !== null) window.clearInterval(taskPollTimer)
    taskRefresh.cancel()
})
</script>

<style scoped>
.task-management { min-width: 0; container: task-management / inline-size; }
/* —— 总览：警示态 + 状态胶囊 —— */
.task-overview-alert { border-color: rgb(239 68 68 / 35%); }
.task-overview-icon { display: flex; flex-shrink: 0; align-items: center; justify-content: center; width: 44px; height: 44px; border-radius: 12px; color: var(--theme-primary); background: rgba(var(--theme-rgb), .1); }
.task-has-failures { color: var(--ts-color-danger); background: rgb(239 68 68 / 10%); }
.task-failure-cta { color: var(--ts-color-danger); }
.task-summary-row { display: flex; flex-wrap: wrap; gap: 8px; }
.task-summary-chip {
  display: inline-flex; align-items: center; gap: 6px; min-height: 36px;
  padding: 4px 12px 4px 10px; border-radius: 10px; font-size: 13px;
  color: var(--ts-color-text-secondary); background: var(--ts-color-surface-muted);
  transition: background-color var(--ts-motion-fast) ease, color var(--ts-motion-fast) ease;
}
.task-summary-chip:hover { color: var(--ts-color-text); }
.task-chip-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--ts-color-text-tertiary); }
.task-dot-pending { background: var(--theme-primary); }
.task-dot-failed { background: var(--ts-color-danger); }
.task-dot-paused { background: #f59e0b; }
.task-chip-active { background: rgba(var(--theme-rgb), .1); color: var(--theme-primary); font-weight: 600; }
/* 失败/暂停胶囊即使未被选中也保持语义色计数可读 */
.task-summary-chip[aria-pressed="true"].task-chip-failed { color: var(--ts-color-danger); }
/* —— 三层分组 —— */
.task-tier + .task-tier { margin-top: 24px; }
.task-tier-title { margin-bottom: 8px; font-size: 13px; font-weight: 600; color: var(--ts-color-text-secondary); }
.task-tier-attention { color: var(--ts-color-danger); }
/* —— 行 —— */
/* 行容器与左边条作用于本组件的 article；徽章/状态点样式随 TaskRowContent 迁移 */
.task-row { padding: 16px; }
.task-row + .task-row { border-top: 1px solid var(--ts-color-divider); }
/* 需要关注：彩色左边条（失败红 / 等待琥珀 / 暂停灰琥珀） */
.task-row-failed, .task-row-waiting, .task-row-paused { position: relative; }
.task-row-failed::before, .task-row-waiting::before, .task-row-paused::before {
  content: ''; position: absolute; left: 0; top: 12px; bottom: 12px; width: 3px; border-radius: 0 3px 3px 0;
}
.task-row-failed::before { background: var(--ts-color-danger); }
.task-row-waiting::before, .task-row-paused::before { background: #f59e0b; }
:global(.dark .task-row-waiting::before), :global(.dark .task-row-paused::before) { background: #fbbf24; }
/* —— 空闲收纳 —— */
.task-idle-summary { display: flex; align-items: center; gap: 10px; width: 100%; min-height: 48px; padding: 10px 16px; font-size: 14px; }
.task-idle-summary:hover { background: var(--ts-color-surface-muted); }
.task-idle-names { flex: 1 1 auto; max-width: 40%; font-size: 13px; }
.task-idle-collapse { min-height: 44px; padding: 4px 10px; border-radius: 8px; }
.task-idle-collapse:hover { background: var(--ts-color-surface-muted); color: var(--ts-color-text); }
.task-row-idle { padding: 12px 16px; }
.task-performance > summary { list-style: none; }
.task-performance > summary::-webkit-details-marker { display: none; }
.task-performance[open] .task-performance-chevron { transform: rotate(180deg); }
.task-performance :deep(.settings-native-group) { border: 0; box-shadow: none; background: transparent; }
.task-performance :deep(.settings-native-group > header) { display: none; }
.task-performance :deep(.settings-native-fields > div) { padding: 0; }
.task-performance :deep(.settings-native-fields) { background: transparent; }
.task-management button:focus-visible, .task-performance > summary:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 2px; border-radius: 8px; }
@container task-management (min-width: 560px) {
  .task-row { padding: 16px 20px; }
  .task-row-idle { padding: 12px 20px; }
}
@media (max-width: 767px) {
  .task-summary-chip { min-height: 44px; }
  .task-overview.ts-settings-panel { padding: 16px; }
}
</style>
