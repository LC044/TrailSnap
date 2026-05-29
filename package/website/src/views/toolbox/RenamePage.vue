<template>
  <div class="container mx-auto py-6 px-4 max-w-4xl">
    <div class="flex items-center gap-4 mb-6">
      <button @click="$router.back()" class="p-2 hover:bg-gray-100 bg-transparent dark:hover:bg-gray-800 rounded-full transition-colors">
        <ArrowLeft class="w-6 h-6 text-gray-600 dark:text-gray-300" />
      </button>
      <div>
        <h1 class="text-2xl font-bold text-gray-800 dark:text-white">批量重命名</h1>
        <p class="text-sm text-gray-500">选择一个文件夹，将其中的图片按拍摄时间 (YYYYMMDD_HHMMSS) 批量重命名。</p>
      </div>
    </div>

    <!-- Active Task Status -->
    <div v-if="activeTask" class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700 mb-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-bold flex items-center gap-2">
          <Loader2 v-if="activeTask.status === 'pending' || activeTask.status === 'processing'" class="w-5 h-5 animate-spin text-primary-500" />
          <CheckCircle2 v-else-if="activeTask.status === 'completed'" class="w-5 h-5 text-green-500" />
          <XCircle v-else class="w-5 h-5 text-red-500" />
          任务状态: {{ statusText }}
        </h3>
        <span class="text-sm font-medium text-gray-500">
          {{ activeTask.processed_items || 0 }} / {{ activeTask.total_items || 0 }}
        </span>
      </div>
      <el-progress 
        :percentage="progressPercentage" 
        :status="activeTask.status === 'completed' ? 'success' : (activeTask.status === 'failed' ? 'exception' : '')"
        :stroke-width="12"
        striped
        :striped-flow="activeTask.status === 'processing'"
      />
      <div v-if="activeTask.status === 'failed' || activeTask.error" class="mt-4 p-3 bg-red-50 dark:bg-red-900/20 text-red-600 rounded-lg text-sm flex justify-between items-center">
        <span>{{ activeTask.error || '任务执行失败，未知错误' }}</span>
        <el-button v-if="activeTask.status === 'failed'" type="danger" size="small" plain @click="clearFailedTask" :loading="clearing">清除失败任务</el-button>
      </div>
    </div>

    <!-- Configuration Form -->
    <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <el-form label-position="top" :disabled="isTaskRunning">
        <el-form-item label="目标文件夹" required>
          <div class="flex items-center gap-4 w-full">
            <el-input 
              v-model="targetRootPath" 
              placeholder="请选择要进行重命名操作的文件夹" 
              readonly
              class="flex-1"
            >
              <template #prepend>
                <Folder class="w-4 h-4" />
              </template>
            </el-input>
            <el-button type="primary" plain @click="showFolderSelector = true">选择目录</el-button>
          </div>
          <div class="text-xs text-gray-500 mt-1">此文件夹（包含其所有子文件夹）内的所有照片都将被重命名。</div>
        </el-form-item>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <el-form-item label="文件前缀">
            <el-input v-model="prefix" placeholder="例如: IMG_" clearable />
            <div class="text-xs text-gray-500 mt-1">默认前缀为 IMG_</div>
          </el-form-item>

          <el-form-item label="文件后缀">
            <el-input v-model="suffix" placeholder="可选后缀" clearable />
            <div class="text-xs text-gray-500 mt-1">如果有相同时间的照片，会自动追加 (1), (2)...</div>
          </el-form-item>
        </div>

        <div class="mt-4 p-4 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700">
          <div class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">预览示例：</div>
          <div class="text-primary-600 dark:text-primary-400 font-mono">
            {{ previewName }}
          </div>
        </div>

        <div class="flex justify-end mt-8">
          <el-button 
            type="primary" 
            size="large" 
            :loading="starting" 
            :disabled="!targetRootPath || isTaskRunning"
            @click="startRename"
          >
            开始重命名
          </el-button>
        </div>
      </el-form>
    </div>

    <!-- Folder Selection Dialog -->
    <el-dialog
      v-model="showFolderSelector"
      title="选择目标目录"
      width="500px"
      class="rounded-xl"
    >
      <div class="border border-gray-200 dark:border-gray-700 rounded-lg h-[300px] overflow-y-auto p-2 bg-gray-50 dark:bg-gray-900/50">
        <el-tree
          :props="{ label: 'name', children: 'children', isLeaf: 'is_leaf' }"
          :load="loadNode"
          lazy
          highlight-current
          @current-change="(data: any) => tempSelectedPath = data.path"
          node-key="path"
          :empty-text="'无可选目录'"
        >
          <template #default="{ data }">
            <div class="flex items-center gap-2 text-sm">
              <Folder class="w-4 h-4 text-primary-500" />
              <span>{{ data.name }}</span>
            </div>
          </template>
        </el-tree>
      </div>
      <template #footer>
        <div class="flex justify-end gap-3">
          <el-button @click="showFolderSelector = false">取消</el-button>
          <el-button type="primary" :disabled="!tempSelectedPath" @click="confirmFolder">确认</el-button>
        </div>
      </template>
    </el-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ArrowLeft, Folder, Loader2, CheckCircle2, XCircle } from 'lucide-vue-next'
import { toolboxApi } from '@/api/toolbox'
import { tasksApi } from '@/api/tasks'
import { settingsApi } from '@/api/settings'
import { ElMessage } from 'element-plus'
import type { Task as TaskResponse } from '@/api/tasks'

const targetRootPath = ref('')
const tempSelectedPath = ref('')
const prefix = ref('IMG_')
const suffix = ref('')
const starting = ref(false)
const clearing = ref(false)

const showFolderSelector = ref(false)

const activeTask = ref<TaskResponse | null>(null)
let pollTimer: number | undefined

const previewName = computed(() => {
  const p = prefix.value || ''
  const s = suffix.value || ''
  return `${p}20260101_123000${s}.jpg`
})

const isTaskRunning = computed(() => {
  return activeTask.value?.status === 'pending' || activeTask.value?.status === 'processing'
})

const statusText = computed(() => {
  if (!activeTask.value) return ''
  switch (activeTask.value.status) {
    case 'pending': return '等待中'
    case 'processing': return '重命名中'
    case 'completed': return '已完成'
    case 'failed': return '失败'
    case 'cancelled': return '已取消'
    default: return activeTask.value.status
  }
})

const progressPercentage = computed(() => {
  if (!activeTask.value || !activeTask.value.total_items) return 0
  return Math.min(100, Math.round((activeTask.value.processed_items || 0) / (activeTask.value.total_items || 0) * 100))
})

const loadNode = async (node: any, resolve: (data: any[]) => void) => {
  try {
    if (node.level === 0) {
      const res = await settingsApi.getDirectoryTree()
      resolve(res.directories || [])
    } else {
      const res = await settingsApi.getDirectoryTree(node.data.path)
      resolve(res.directories || [])
    }
  } catch (e) {
    resolve([])
  }
}

const confirmFolder = () => {
  targetRootPath.value = tempSelectedPath.value
  showFolderSelector.value = false
}

const fetchLatestTask = async () => {
  try {
    const task = await toolboxApi.getLatestRenameTask()
    activeTask.value = task
    
    if (task && (task.status === 'pending' || task.status === 'processing')) {
      startPolling()
    }
  } catch (e) {
    console.error('Failed to fetch latest rename task', e)
  }
}

const startPolling = () => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = window.setInterval(async () => {
    if (!activeTask.value?.id) return
    try {
      const task = await tasksApi.getTask(activeTask.value.id)
      activeTask.value = task
      
      if (task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled') {
        stopPolling()
        if (task.status === 'completed') {
          ElMessage.success('批量重命名已完成')
        }
      }
    } catch (e) {
      console.error('Failed to poll task status', e)
    }
  }, 2000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = undefined
  }
}

const startRename = async () => {
  if (!targetRootPath.value) {
    ElMessage.warning('请选择目标目录')
    return
  }
  
  starting.value = true
  try {
    const payload = {
      target_root_path: targetRootPath.value,
      prefix: prefix.value,
      suffix: suffix.value
    }
    const task = await toolboxApi.createRenameTask(payload)
    activeTask.value = task
    ElMessage.success('已开始重命名任务')
    startPolling()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '创建任务失败')
  } finally {
    starting.value = false
  }
}

const clearFailedTask = async () => {
  if (!activeTask.value || activeTask.value.status !== 'failed') return
  
  clearing.value = true
  try {
    await tasksApi.deleteFailedTasks(['BATCH_RENAME'])
    activeTask.value = null
    ElMessage.success('已清除失败任务')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '清除任务失败')
  } finally {
    clearing.value = false
  }
}

onMounted(() => {
  fetchLatestTask()
})

onUnmounted(() => {
  stopPolling()
})
</script>
