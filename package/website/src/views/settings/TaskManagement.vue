<template>
  <div>
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4 sm:gap-0">
        <h2 class="text-xl md:text-2xl font-semibold text-gray-800 dark:text-white">任务管理</h2>
        <div class="flex gap-4 items-center w-full sm:w-auto justify-between sm:justify-end">
                <div class="flex items-center gap-2">
                <span class="text-sm text-gray-600 dark:text-gray-300">快速模式</span>
                <el-switch v-model="fastMode" @change="handleFastModeChange" />
                <el-tooltip content="开启后将同时运行不同类型的任务（CPU/IO），最大化资源利用" placement="top">
                    <span class="text-gray-400 cursor-pointer">
                        <i class="i-mdi-help-circle-outline"></i>
                    </span>
                </el-tooltip>
                </div>
        </div>
    </div>
    <!-- Stats Cards -->
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6 mb-6">

      
      <!-- Category Cards -->
      <div class="grid grid-cols-1 gap-4">
        <div v-for="cat in groupedTasks" :key="cat.category" class="border rounded-lg p-4 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50">
          <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-4 gap-2 sm:gap-0">
            <div class="flex flex-wrap items-center gap-2 sm:gap-3">
              <h3 class="text-lg flex items-center font-medium dark:text-white">{{cat.task_name}}
                <el-tooltip :content="cat.description" placement="top">
                    <Info class="w-4 h-4 ml-1 text-gray-400 cursor-help" />
                </el-tooltip>
              </h3>
              <el-tag effect="plain" size="small" class="ml-0 sm:ml-2">
                 优先级: {{ cat.priority }}
              </el-tag>

              <!-- Status Logic -->
              <el-tag v-if="cat.status === 'paused'" type="warning" size="small">已暂停</el-tag>
              <el-tag v-else-if="cat.pending === 0" type="success" size="small">已完成</el-tag>
              <el-tag v-else-if="cat.completed === 0 && cat.pending === 0" type="info" size="small">等待中</el-tag>
              <el-tag v-else type="primary" size="small">进行中</el-tag>
            </div>
            <div class="w-full sm:w-auto mt-2 sm:mt-0">
                <el-dropdown trigger="click" @command="(cmd: string) => handleCategoryCommand(cat.category, cmd)" class="w-full sm:w-auto">
                    <el-button type="primary" size="small" plain class="w-full sm:w-auto">
                        操作<i class="el-icon-arrow-down el-icon--right"></i>
                    </el-button>
                    <template #dropdown>
                        <el-dropdown-menu>
                            <el-dropdown-item v-if="cat.status === 'paused'" command="resume">继续任务</el-dropdown-item>
                            <el-dropdown-item v-else command="pause">暂停任务</el-dropdown-item>
                            <el-dropdown-item command="scan_missing" divided>执行缺失任务</el-dropdown-item>
                            <el-dropdown-item command="retry" :disabled="cat.failed === 0">重试失败任务</el-dropdown-item>
                            <el-dropdown-item command="delete_failed" :disabled="cat.failed === 0">删除失败任务</el-dropdown-item>
                            <el-dropdown-item command="rebuild">强制重做此项</el-dropdown-item>
                        </el-dropdown-menu>
                    </template>
                </el-dropdown>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-4 text-center">
             <div class="bg-white dark:bg-gray-900 p-3 rounded shadow-sm">
               <div class="text-gray-500 text-xs mb-1">待处理</div>
               <div class="text-xl font-bold text-blue-600">{{ cat.pending }}</div>
             </div>
             <div 
                class="bg-white dark:bg-gray-900 p-3 rounded shadow-sm transition-colors" 
                :class="{'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800': cat.failed > 0, 'opacity-60': cat.failed === 0}"
                @click="cat.failed > 0 && showFailedTasks(cat.category)"
             >
               <div class="text-gray-500 text-xs mb-1">失败 {{ cat.failed > 0 ? '(点击查看)' : '' }}</div>
               <div class="text-xl font-bold text-red-600">{{ cat.failed }}</div>
             </div>
          </div>
        </div>
      </div>

    </div>

    <!-- Failed Tasks Dialog -->
    <el-dialog v-model="failedTasksVisible" title="失败任务列表" width="900px" class="max-w-[90%] w-full sm:w-[900px]">
        <el-table :data="failedTasksList" style="width: 100%" v-loading="failedTasksLoading" height="500">
            <el-table-column prop="type" label="类型" width="160" />
            <el-table-column prop="payload.file_path" label="文件路径" width="180" show-overflow-tooltip />
            <el-table-column prop="error" label="错误信息" show-overflow-tooltip />
            <el-table-column prop="created_at" label="创建时间" width="180">
                <template #default="{ row }">
                    {{ new Date(row.created_at).toLocaleString('zh-CN') || 'N/A' }}
                </template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
                <template #default="{ row }">
                    <el-button type="primary" link size="small" @click="retrySingleTask(row)">重试</el-button>
                </template>
            </el-table-column>
        </el-table>
        <template #footer>
            <span class="dialog-footer">
                <el-button @click="failedTasksVisible = false">关闭</el-button>
            </span>
        </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { tasksApi } from '@/api/tasks'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Sun, Moon, Palette, Check, Info, Download, Loader2, Trash2 } from 'lucide-vue-next'
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
}

const groupedTasks = ref<GroupedTask[]>([])
const fastMode = ref(false)
const notifyStore = useNotificationStore()

const failedTasksVisible = ref(false)
const failedTasksList = ref<any[]>([])
const failedTasksLoading = ref(false)

const fetchTasks = async () => {
    try {
        groupedTasks.value = await tasksApi.getGroupedStatus()
        // Fetch global status for fast mode
        const globalStatus = await tasksApi.getGlobalStatus()
        if (globalStatus && typeof globalStatus.fast_mode !== 'undefined') {
            fastMode.value = globalStatus.fast_mode=="True"
        }
    } catch (e) {
        console.error("Failed to fetch tasks", e)
    }
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
    if (command === 'pause') {
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

const showFailedTasks = async (category: string) => {
    failedTasksVisible.value = true
    failedTasksLoading.value = true
    failedTasksList.value = []
    
    try {
       const types = [category]
       if (types) {
          failedTasksList.value = await tasksApi.listTasks('failed', types[0], 1000)
       }
    } catch (e) {
        ElMessage.error('获取失败列表失败')
    } finally {
        failedTasksLoading.value = false
    }
}

const retrySingleTask = async (row: any) => {
    try {
        await tasksApi.retryTask(row.id)
        ElMessage.success('已重试')
        // Remove from local list
        failedTasksList.value = failedTasksList.value.filter(t => t.id !== row.id)
        fetchTasks()
    } catch (e) {
        ElMessage.error('重试失败')
    }
}

const pauseCategory = async (category: string) => {
    try {
        await tasksApi.pauseCategory(category)
        ElMessage.success('已暂停')
        fetchTasks()
    } catch (e) {
        ElMessage.error('暂停失败')
    }
}

const resumeCategory = async (category: string) => {
    try {
        await tasksApi.resumeCategory(category)
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
