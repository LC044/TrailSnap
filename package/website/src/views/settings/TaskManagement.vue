<template>
  <div class="task-management ts-settings-page">
    <SettingsPageHeader title="任务管理" description="查看处理进度，排查与重试失败任务">
      <template #actions>
        <div class="flex items-center gap-2">
        <span class="text-sm text-gray-600 dark:text-gray-300">快速模式</span>
        <el-switch v-model="fastMode" @change="handleFastModeChange" />
        <el-tooltip content="开启后将同时运行不同类型的任务（CPU/IO），最大化资源利用" placement="top">
            <span class="text-gray-400 dark:text-gray-500 cursor-pointer">
                <i class="i-mdi-help-circle-outline"></i>
            </span>
        </el-tooltip>
        </div>
      </template>
    </SettingsPageHeader>
    <div class="task-groups">
      <div v-if="loading && !groupedTasks.length" class="py-12 text-center ts-muted" role="status">正在加载任务…</div>
      <div v-else-if="loadFailed" class="task-group mb-4" role="alert">
        <p class="ts-muted mb-3">任务状态加载失败，请稍后重试</p>
        <button class="ts-button ts-button-secondary" @click="fetchTasks">重新加载</button>
      </div>
      <p v-else-if="!groupedTasks.length" class="py-12 text-center ts-muted">暂无任务</p>
      <!-- Category Cards -->
      <div class="grid grid-cols-1 gap-4">
        <div v-for="cat in groupedTasks" :key="cat.category" class="task-group">
          <div class="flex justify-between items-start gap-3 mb-4">
            <div class="min-w-0 flex flex-wrap items-center gap-2 sm:gap-3">
              <h3 class="text-lg flex items-center min-w-0 font-medium dark:text-white">{{cat.task_name}}
                <el-tooltip :content="cat.description" placement="top">
                    <Info class="w-4 h-4 ml-1 text-gray-400 dark:text-gray-500 cursor-help" />
                </el-tooltip>
              </h3>
              <el-tag effect="plain" size="small" class="ml-0 sm:ml-2">
                 优先级: {{ cat.priority }}
              </el-tag>

              <!-- Status Logic -->
              <el-tag v-if="cat.status === 'paused'" type="warning" size="small">已暂停</el-tag>
              <el-tag v-else-if="cat.waiting_reason && cat.pending > 0" type="info" size="small">{{ cat.waiting_reason }}</el-tag>
              <el-tag v-else-if="cat.failed > 0" type="danger" size="small">有失败任务</el-tag>
              <el-tag v-else-if="cat.pending === 0" type="success" size="small">已完成</el-tag>
              <el-tag v-else-if="cat.completed === 0 && cat.pending === 0" type="info" size="small">等待中</el-tag>
              <el-tag v-else type="primary" size="small">进行中</el-tag>
            </div>
            <div class="shrink-0">
              <button class="ts-icon-button ts-button-secondary" :aria-label="`${cat.task_name}操作`" :aria-expanded="activeMenu === cat.category" aria-haspopup="menu" @click="activeMenu = activeMenu === cat.category ? '' : cat.category"><MoreHorizontal class="h-5 w-5" /></button>
              <AdaptiveMenu :model-value="activeMenu === cat.category" :title="`${cat.task_name}操作`" close-on-action @update:model-value="value => activeMenu = value ? cat.category : ''">
                <button class="ts-action-row" @click="handleCategoryCommand(cat.category, cat.status === 'paused' ? 'resume' : 'pause')">{{ cat.status === 'paused' ? '继续任务' : '暂停任务' }}</button>
                <button class="ts-action-row" @click="handleCategoryCommand(cat.category, 'scan_missing')">执行缺失任务</button>
                <button class="ts-action-row" :disabled="cat.failed === 0" @click="handleCategoryCommand(cat.category, 'retry')">重试失败任务</button>
                <button v-if="cat.category === 'RECOGNIZE_TICKET'" class="ts-action-row" :disabled="recoveringTickets" @click="handleCategoryCommand(cat.category, 'recover_tickets')">恢复旧版未保存的票据</button>
                <button class="ts-action-row" :disabled="cat.failed === 0" @click="handleCategoryCommand(cat.category, 'delete_failed')">删除失败任务</button>
                <button class="ts-action-row" @click="handleCategoryCommand(cat.category, 'rebuild')">强制重做此项</button>
              </AdaptiveMenu>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-4 text-center">
             <div class="task-stat">
               <div class="ts-muted text-xs mb-1">待处理</div>
               <div class="text-xl font-bold primary-text">{{ cat.pending }}</div>
             </div>
             <button type="button" :disabled="cat.failed === 0"
                class="task-stat task-stat-failed transition-colors"
                :class="{'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800': cat.failed > 0, 'opacity-60': cat.failed === 0}"
                @click="cat.failed > 0 && showFailedTasks(cat.category)"
             >
               <div class="ts-muted text-xs mb-1">失败 {{ cat.failed > 0 ? '(点击查看)' : '' }}</div>
               <div class="text-xl font-bold text-red-600 dark:text-red-400">{{ cat.failed }}</div>
             </button>
          </div>
        </div>
      </div>

    </div>

    <FailedTasksDialog v-model="failedTasksVisible" :category="failedCategory" :title="failedCategoryTitle" @retried="fetchTasks" />
  </div>
</template>

<script setup lang="ts">
import SettingsPageHeader from '@/components/ui/SettingsPageHeader.vue'
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { tasksApi } from '@/api/tasks'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Info, MoreHorizontal } from 'lucide-vue-next'
import FailedTasksDialog from '@/components/FailedTasksDialog.vue'
import AdaptiveMenu from '@/components/ui/AdaptiveMenu.vue'
import { useNotificationStore } from '@/stores/notificationStore'

interface GroupedTask {
    task_name: string
    category: string
    pending: number
    completed: number
    failed: number
    status: string
    priority: number
    description: string
    waiting_reason?: string
}

const groupedTasks = ref<GroupedTask[]>([])
const fastMode = ref(false)
const notifyStore = useNotificationStore()

const failedTasksVisible = ref(false)
const failedCategory = ref('')
const failedCategoryTitle = ref('')
const activeMenu = ref('')
const loading = ref(true)
const loadFailed = ref(false)

const fetchTasks = async () => {
    try {
        const [groups, globalStatus] = await Promise.all([tasksApi.getGroupedStatus(), tasksApi.getGlobalStatus()])
        groupedTasks.value = groups
        loadFailed.value = false
        if (globalStatus && typeof globalStatus.fast_mode !== 'undefined') {
            fastMode.value = globalStatus.fast_mode === true || globalStatus.fast_mode === 'True'
        }
    } catch (e) {
        loadFailed.value = true
        console.error("Failed to fetch tasks", e)
    } finally { loading.value = false }
}

const handleFastModeChange = async (val: boolean) => {
    try {
        await tasksApi.toggleFastMode(val)
        ElMessage.success(val ? '快速模式已开启' : '快速模式已关闭')
    } catch (e) {
        ElMessage.error('设置失败')
        fastMode.value = !val
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
.task-management { min-width: 0; }
.task-group { padding: var(--ts-space-6); border-radius: var(--ts-radius-card); border: 1px solid var(--ts-color-border); background: var(--ts-color-surface); }
.task-stat { padding: 12px; border-radius: 14px; background: var(--ts-color-surface-muted); text-align: center; min-width: 0; }
.task-stat-failed:enabled:hover { background: color-mix(in srgb, var(--ts-color-danger) 8%, var(--ts-color-surface-muted)); }
.primary-text { color: var(--theme-primary); }
@media (max-width: 767px) {
  .task-group { padding: var(--ts-space-4); }
  .task-group h3 { font-size: 16px; }
  .task-stat { padding: 10px; }
}
</style>
