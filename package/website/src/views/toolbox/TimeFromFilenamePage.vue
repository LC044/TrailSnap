<template>
  <div class="container mx-auto py-6 px-4 max-w-4xl">
    <div class="flex items-center gap-4 mb-6">
      <button @click="$router.back()" class="p-2 hover:bg-gray-100 bg-transparent dark:hover:bg-gray-800 rounded-full transition-colors">
        <ArrowLeft class="w-6 h-6 text-gray-600 dark:text-gray-300" />
      </button>
      <div>
        <h1 class="text-2xl font-bold text-gray-800 dark:text-white">修改图片元数据</h1>
        <p class="text-sm text-gray-500">选择一个文件夹，将其中的照片根据文件名中的时间（YYYYMMDD_HHMMSS）批量修改拍摄时间，该操作将直接修改图片元数据且不可逆。</p>
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
              placeholder="请选择要进行操作的文件夹" 
              readonly
              class="flex-1"
            >
              <template #prepend>
                <Folder class="w-4 h-4" />
              </template>
            </el-input>
            <el-button type="primary" plain @click="showFolderSelector = true">选择目录</el-button>
          </div>
          <div class="text-xs text-gray-500 mt-1">此文件夹（包含其所有子文件夹）内的所有照片（支持JPG、JPEG、等支持exif元数据的格式）都将根据文件名中的时间进行修改。</div>
        </el-form-item>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <el-form-item label="拍摄品牌（Make）">
            <el-input v-model="make" placeholder="例如: Apple, Samsung, Canon" clearable />
            <div class="text-xs text-gray-500 mt-1">选填，将同步更新到照片的设备品牌信息</div>
          </el-form-item>

          <el-form-item label="拍摄型号（Model）">
            <el-input v-model="model" placeholder="例如: iPhone 15, Galaxy S24" clearable />
            <div class="text-xs text-gray-500 mt-1">选填，将同步更新到照片的设备型号信息</div>
          </el-form-item>
        </div>

        <el-form-item label="拍摄时间处理方式" subtitle="选择如何处理照片的拍摄时间字段">
          <el-radio-group v-model="timeMode" class="flex flex-col items-start gap-3">
            <el-radio value="auto" class="!mr-0 !ml-0">自动识别</el-radio>
            <div class="flex items-center gap-2">
              <el-radio value="custom" class="!mr-0 !ml-0">指定时间</el-radio>
              <el-date-picker
                v-if="timeMode === 'custom'"
                v-model="customTime"
                type="datetime"
                placeholder="选择日期和时间"
                format="YYYY-MM-DD HH:mm:ss"
                value-format="YYYY-MM-DD HH:mm:ss"
              />
            </div>
            <el-radio value="none" class="!mr-0 !ml-0">不修改时间（仅修改设备信息）</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item>
          <el-checkbox v-model="onlyMissingMetadata">仅修改元数据缺失的图片</el-checkbox>
          <div class="text-xs text-gray-500 mt-1">勾选后，仅对缺少拍摄设备信息（品牌、型号）的照片进行修改，否则对所有照片强制进行修改（包括已存在品牌、型号的照片）。
          <br><span class="text-red-500">注意：如果照片已存在品牌、型号信息，勾选后将不会修改。</span></div>
        </el-form-item>

        <div class="flex justify-end mt-8">
          <el-button 
            type="primary" 
            size="large" 
            :loading="starting" 
            :disabled="!targetRootPath || isTaskRunning"
            @click="startProcess"
          >
            开始修改拍摄信息
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
const starting = ref(false)
const clearing = ref(false)
const onlyMissingMetadata = ref(true)
const make = ref('')
const model = ref('')
const timeMode = ref('auto')
const customTime = ref('')

const showFolderSelector = ref(false)

const activeTask = ref<TaskResponse | null>(null)
let pollTimer: number | undefined

const isTaskRunning = computed(() => {
  return activeTask.value?.status === 'pending' || activeTask.value?.status === 'processing'
})

const statusText = computed(() => {
  if (!activeTask.value) return ''
  switch (activeTask.value.status) {
    case 'pending': return '等待中'
    case 'processing': return '处理中'
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
    const task = await toolboxApi.getLatestTimeFromFilenameTask()
    activeTask.value = task
    
    if (task && (task.status === 'pending' || task.status === 'processing')) {
      startPolling()
    }
  } catch (e) {
    console.error('Failed to fetch latest time from filename task', e)
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
          ElMessage.success('批量修改拍摄信息已完成')
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

const startProcess = async () => {
  if (!targetRootPath.value) {
    ElMessage.warning('请选择目标目录')
    return
  }

  if (timeMode.value === 'custom' && !customTime.value) {
    ElMessage.warning('请选择具体的日期和时间')
    return
  }
  
  starting.value = true
  try {
    const payload: any = {
      target_root_path: targetRootPath.value,
      only_missing_metadata: onlyMissingMetadata.value,
      time_mode: timeMode.value
    }
    if (timeMode.value === 'custom' && customTime.value) {
      payload.custom_time = customTime.value
    }
    if (make.value) {
      payload.make = make.value
    }
    if (model.value) {
      payload.model = model.value
    }
    const task = await toolboxApi.createTimeFromFilenameTask(payload)
    activeTask.value = task
    ElMessage.success('已开始修改拍摄信息任务')
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
    await tasksApi.deleteFailedTasks(['BATCH_TIME_FROM_FILENAME'])
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