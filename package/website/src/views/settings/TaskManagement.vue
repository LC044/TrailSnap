<template>
  <div class="task-management ts-settings-page">
    <SettingsPageHeader title="后台任务" description="查看任务队列，处理失败项与暂停的任务">
      <template #actions>
        <button type="button" class="ts-icon-button ts-button-secondary" aria-label="刷新任务状态" :disabled="loading" @click="fetchTasks">
          <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': loading }" />
        </button>
      </template>
    </SettingsPageHeader>

    <section class="task-overview ts-surface ts-settings-panel" aria-label="任务队列总览">
      <div v-if="loading && !groupedTasks.length" class="py-4 ts-muted" role="status">正在加载任务…</div>
      <div v-else-if="loadFailed" role="alert">
        <h2 class="ts-section-title">暂时无法获取任务状态</h2>
        <p class="ts-muted mt-2 text-sm">请重新加载。已有任务不会因此停止；下方信息可能尚未更新。</p>
        <button type="button" class="ts-button ts-button-secondary mt-4" :disabled="loading" @click="fetchTasks">重新加载</button>
      </div>
      <template v-else>
        <div class="flex items-start gap-3">
          <span class="task-overview-icon" :class="{ 'task-has-failures': summary.failed > 0 }">
            <AlertCircle v-if="summary.failed" class="h-6 w-6" />
            <Clock3 v-else-if="summary.pending" class="h-6 w-6" />
            <CheckCircle2 v-else class="h-6 w-6" />
          </span>
          <div class="min-w-0 flex-1">
            <h2 class="ts-section-title">{{ summary.failed ? '有失败任务需要处理' : summary.pending ? '还有任务待处理' : '当前没有待处理任务' }}</h2>
          </div>
        </div>
        <div class="mt-5 flex flex-wrap items-end gap-x-6 gap-y-3">
          <div><span class="text-3xl font-semibold tabular-nums">{{ formatCount(summary.pending) }}</span><span class="ts-muted ml-2 text-sm">项待处理</span></div>
          <button v-if="summary.failed" type="button" class="task-failure-link min-h-11 text-sm font-medium" @click="taskFilter = 'failed'">失败 {{ formatCount(summary.failed) }} 项 <ChevronRight class="inline h-4 w-4" /></button>
          <span v-else class="ts-muted text-sm">没有失败任务</span>
          <button v-if="summary.paused" type="button" class="min-h-11 text-sm ts-muted" @click="taskFilter = 'paused'">已暂停 {{ summary.paused }} 类</button>
        </div>
      </template>
    </section>

    <section class="task-groups" aria-labelledby="task-list-title">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 id="task-list-title" class="ts-section-title">处理类型</h2>
        <div class="task-filters flex flex-wrap gap-1" role="group" aria-label="筛选任务">
          <button v-for="filter in taskFilters" :key="filter.value" type="button" class="task-filter"
            :class="{ 'task-filter-active': taskFilter === filter.value }" :aria-pressed="taskFilter === filter.value" @click="taskFilter = filter.value">
            {{ filter.label }} <span class="tabular-nums">{{ filterTaskGroups(groupedTasks, filter.value).length }}</span>
          </button>
        </div>
      </div>
      <p v-if="!loading && !loadFailed && !visibleTasks.length" class="ts-surface ts-settings-panel text-center ts-muted text-sm">
        {{ taskFilter === 'all' ? '暂无处理类型' : `没有${taskFilters.find(filter => filter.value === taskFilter)?.label}的处理类型` }}
      </p>
      <div v-if="visibleTasks.length" class="task-list ts-surface overflow-hidden" :aria-busy="loading">
        <article v-for="cat in visibleTasks" :key="cat.category" class="task-row">
          <div class="task-row-main">
            <button type="button" class="task-details-trigger flex min-w-0 items-start gap-3 text-left" :aria-label="`${cat.task_name}详情`" :aria-expanded="expandedTask === cat.category" :aria-controls="`task-details-${cat.category}`" @click="expandedTask = expandedTask === cat.category ? '' : cat.category">
              <span class="task-state-icon" :class="`task-state-${getTaskState(cat)}`">
                <component :is="stateIcons[getTaskState(cat)]" class="h-5 w-5" />
              </span>
              <span class="min-w-0 flex-1">
                <span class="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span class="text-[15px] font-semibold">{{ cat.task_name }}</span>
                  <span class="task-state-label" :class="`task-state-${getTaskState(cat)}`">{{ taskStateLabels[getTaskState(cat)] }}</span>
                  <ChevronDown class="h-3.5 w-3.5 ts-muted transition-transform" :class="{ 'rotate-180': expandedTask === cat.category }" />
                </span>
                <span class="ts-muted mt-1 block text-sm">{{ cat.pending > 0 ? `待处理 ${formatCount(cat.pending)} 项` : '暂无待处理任务' }}</span>
                <span v-if="cat.waiting_reason && cat.pending > 0" class="task-waiting-reason mt-1 block text-xs leading-5">{{ cat.waiting_reason }}</span>
              </span>
            </button>
            <div class="task-row-actions flex flex-wrap items-center justify-end gap-2">
              <button v-if="cat.failed > 0" type="button" class="task-failure-link min-h-11 text-sm font-medium" :aria-label="`${cat.task_name}：${cat.failed} 项失败，查看详情`" @click="showFailedTasks(cat.category)">失败 {{ formatCount(cat.failed) }} 项 <ChevronRight class="inline h-4 w-4" /></button>
              <button type="button" class="ts-button ts-button-secondary ts-button-sm hidden md:inline-flex" :disabled="loadFailed" @click="handleCategoryCommand(cat.category, cat.status === 'paused' ? 'resume' : 'pause')">{{ cat.status === 'paused' ? '继续' : '暂停' }}</button>
              <div class="shrink-0">
              <button class="ts-icon-button ts-button-ghost" :aria-label="`${cat.task_name}操作`" :aria-expanded="activeMenu === cat.category" aria-haspopup="menu" :disabled="loadFailed" @click="activeMenu = activeMenu === cat.category ? '' : cat.category"><MoreHorizontal class="h-5 w-5" /></button>
              <AdaptiveMenu :model-value="activeMenu === cat.category" :title="`${cat.task_name}操作`" close-on-action @update:model-value="value => activeMenu = value ? cat.category : ''">
                <button v-if="isMobile" class="ts-action-row" @click="handleCategoryCommand(cat.category, cat.status === 'paused' ? 'resume' : 'pause')">{{ cat.status === 'paused' ? '继续任务' : '暂停任务' }}</button>
                <button class="ts-action-row" @click="handleCategoryCommand(cat.category, 'scan_missing')">执行缺失任务</button>
                <button class="ts-action-row" :disabled="cat.failed === 0" @click="handleCategoryCommand(cat.category, 'retry')">重试失败任务</button>
                <button v-if="cat.category === 'RECOGNIZE_TICKET'" class="ts-action-row" :disabled="recoveringTickets" @click="handleCategoryCommand(cat.category, 'recover_tickets')">恢复旧版未保存的票据</button>
                <button class="ts-action-row danger" :disabled="cat.failed === 0" @click="handleCategoryCommand(cat.category, 'delete_failed')">删除失败任务</button>
                <button class="ts-action-row danger" @click="handleCategoryCommand(cat.category, 'rebuild')">强制重做此项</button>
              </AdaptiveMenu>
              </div>
            </div>
          </div>
          <div v-if="expandedTask === cat.category" :id="`task-details-${cat.category}`" class="task-details ts-muted text-sm leading-6">
            <p>{{ cat.description }}</p>
            <p class="mt-1">调度优先级 {{ cat.priority }} · 待处理 {{ formatCount(cat.pending) }} 项 · 失败 {{ formatCount(cat.failed) }} 项</p>
            <p v-if="cat.status === 'paused'" class="mt-1">此类型已暂停，点击“继续”恢复调度；当前执行中的任务会先完成。</p>
          </div>
        </article>
      </div>
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
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { tasksApi } from '@/api/tasks'
import { ElMessage, ElMessageBox } from 'element-plus'
import { AlertCircle, CheckCircle2, ChevronDown, ChevronRight, Circle, Clock3, MoreHorizontal, PauseCircle, RefreshCw, Settings2 } from 'lucide-vue-next'
import FailedTasksDialog from '@/components/FailedTasksDialog.vue'
import AdaptiveMenu from '@/components/ui/AdaptiveMenu.vue'
import { useNotificationStore } from '@/stores/notificationStore'
import { filterTaskGroups, getTaskState, summarizeTaskGroups, taskFilters, taskStateLabels, type TaskFilter, type TaskGroup } from '@/utils/taskPresentation'

const groupedTasks = ref<TaskGroup[]>([])
const isMobile = useMediaQuery('(max-width: 767px)')
const taskFilter = ref<TaskFilter>('all')
const summary = computed(() => summarizeTaskGroups(groupedTasks.value))
const visibleTasks = computed(() => filterTaskGroups(groupedTasks.value, taskFilter.value))
const stateIcons = { paused: PauseCircle, waiting: Clock3, pending: Clock3, failed: AlertCircle, idle: Circle }
const formatCount = (count: number) => count.toLocaleString('zh-CN')
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

// 任务列表刷新：挂载拉一次 + SSE 事件驱动（防抖 1s）+ 60s 兜底轮询。
let taskPollTimer: number | null = null
let refreshDebounce: number | null = null
const scheduleRefresh = () => {
    if (refreshDebounce) window.clearTimeout(refreshDebounce)
    refreshDebounce = window.setTimeout(() => {
        refreshDebounce = null
        fetchTasks()
    }, 1000)
}
watch(() => notifyStore.lastEventAt, () => {
    scheduleRefresh()
})

onMounted(() => {
    fetchTasks()
    taskPollTimer = window.setInterval(fetchTasks, 60000)
})

onUnmounted(() => {
    if (taskPollTimer) {
        clearInterval(taskPollTimer)
        taskPollTimer = null
    }
    if (refreshDebounce) {
        window.clearTimeout(refreshDebounce)
        refreshDebounce = null
    }
})
</script>

<style scoped>
.task-management { min-width: 0; container: task-management / inline-size; }
.task-overview-icon, .task-state-icon { display: flex; flex-shrink: 0; align-items: center; justify-content: center; border-radius: 12px; }
.task-overview-icon { width: 44px; height: 44px; color: var(--theme-primary); background: rgba(var(--theme-rgb), .1); }
.task-state-icon { width: 36px; height: 36px; background: var(--ts-color-surface-muted); color: var(--ts-color-text-secondary); }
.task-state-label { border-radius: 6px; padding: 2px 6px; font-size: 11px; line-height: 1.5; background: var(--ts-color-surface-muted); color: var(--ts-color-text-secondary); }
.task-state-pending { color: var(--theme-primary); background: rgba(var(--theme-rgb), .1); }
.task-state-paused, .task-state-waiting { color: #b45309; background: rgb(245 158 11 / 10%); }
.task-state-failed, .task-has-failures { color: var(--ts-color-danger); background: rgb(239 68 68 / 10%); }
.task-failure-link { color: var(--ts-color-danger); }
.task-waiting-reason { overflow-wrap: anywhere; color: var(--ts-color-text-secondary); }
.task-filter { min-height: 36px; padding: 6px 10px; border-radius: 10px; font-size: 13px; color: var(--ts-color-text-secondary); }
.task-filter:hover { background: var(--ts-color-surface-muted); }
.task-filter-active { background: rgba(var(--theme-rgb), .1); color: var(--theme-primary); font-weight: 600; }
.task-row { padding: 16px; }
.task-row + .task-row { border-top: 1px solid var(--ts-color-divider); }
.task-row-main { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 12px; }
.task-row-main:has(.task-failure-link) .task-row-actions { grid-column: 1 / -1; }
.task-details-trigger { padding-block: 4px; }
.task-details { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--ts-color-divider); }
.task-performance > summary { list-style: none; }
.task-performance > summary::-webkit-details-marker { display: none; }
.task-performance[open] .task-performance-chevron { transform: rotate(180deg); }
.task-performance :deep(.settings-native-group) { border: 0; box-shadow: none; background: transparent; }
.task-performance :deep(.settings-native-group > header) { display: none; }
.task-performance :deep(.settings-native-fields > div) { padding: 0; }
.task-performance :deep(.settings-native-fields) { background: transparent; }
.task-management button:focus-visible, .task-performance > summary:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 2px; border-radius: 8px; }
:global(.dark) .task-state-paused, :global(.dark) .task-state-waiting { color: #fbbf24; }
@container task-management (min-width: 560px) {
  .task-row { padding: 16px 20px; }
  .task-row-main:has(.task-failure-link) .task-row-actions { grid-column: auto; }
}
@media (max-width: 767px) {
  .task-filter { min-height: 44px; }
  .task-overview.ts-settings-panel { padding: 16px; }
}
</style>
