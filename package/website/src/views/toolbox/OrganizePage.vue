<template>
  <div class="container mx-auto py-6 px-4 max-w-4xl">
    <div class="flex items-center gap-4 mb-6">
      <button @click="$router.back()" class="p-2 hover:bg-gray-100 bg-transparent dark:hover:bg-gray-800 rounded-full transition-colors">
        <ArrowLeft class="w-6 h-6 text-gray-600 dark:text-gray-300" />
      </button>
      <div>
        <h1 class="text-2xl font-bold text-gray-800 dark:text-white">图片文件整理</h1>
        <p class="text-sm text-gray-500">按照特定规则自动将照片分类整理到指定的外部文件夹中。</p>
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
          {{ activeTask.processed_items }} / {{ activeTask.total_items }}
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
        <el-form-item label="目标根目录" required>
          <div class="flex items-center gap-4 w-full">
            <el-input 
              v-model="targetRootPath" 
              placeholder="请选择或输入目标外部文件夹的绝对路径" 
              readonly
              class="flex-1"
            >
              <template #prepend>
                <Folder class="w-4 h-4" />
              </template>
            </el-input>
            <el-button type="primary" plain @click="showFolderSelector = true">选择目录</el-button>
          </div>
          <div class="text-xs text-gray-500 mt-1">选中的目录必须是已配置的外部图库或主存储目录。子文件夹将在此目录下自动创建。</div>
        </el-form-item>

        <el-form-item label="整理规则" required>
          <el-radio-group v-model="strategy" class="w-full grid grid-cols-2 sm:grid-cols-4 gap-4">
            <el-radio-button label="time" class="!w-full">按时间</el-radio-button>
            <el-radio-button label="category" class="!w-full">按智能分类</el-radio-button>
            <el-radio-button label="person" class="!w-full">按人物</el-radio-button>
            <el-radio-button label="location" class="!w-full">按位置</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="strategy === 'time'" label="时间粒度" required>
          <el-radio-group v-model="timeGranularity">
            <el-radio label="ym" size="large">年月 (YYYY-MM)</el-radio>
            <el-radio label="ymd" size="large">年月日 (YYYY-MM-DD)</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="strategy === 'time'" label="时间范围">
          <el-date-picker
            v-model="timeRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            class="!w-full max-w-md"
          />
          <div class="text-xs text-gray-500 mt-1">留空则默认整理所有时间的照片。</div>
        </el-form-item>

        <el-form-item v-if="strategy === 'time'" label="时间目录结构" required>
          <div class="flex flex-col gap-2">
            <el-radio-group v-model="timeFormat">
              <el-radio label="flat" size="large">平铺结构 (例如: 2026-01-01)</el-radio>
              <el-radio label="nested" size="large">递归结构 (例如: 2026/01/01)</el-radio>
            </el-radio-group>
            <div class="text-xs text-gray-500 bg-gray-50 dark:bg-gray-900/50 p-3 rounded-lg border border-gray-100 dark:border-gray-800">
              <ul class="list-disc pl-4 space-y-1">
                <li><strong>平铺结构：</strong> 所有时间文件夹都将直接创建在目标根目录下，不会有层级嵌套。</li>
                <li><strong>递归结构：</strong> 会按照年份、月份、日期依次创建多层级的文件夹结构。</li>
              </ul>
            </div>
          </div>
        </el-form-item>

        <el-form-item v-if="strategy === 'category'" label="选择整理类别">
          <el-select
            v-model="selectedCategories"
            multiple
            filterable
            placeholder="请选择类别 (默认全选)"
            :loading="loadingOptions"
            class="w-full max-w-2xl"
          >
            <el-option
              v-for="item in previewOptions"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
        </el-form-item>

        <el-form-item v-if="strategy === 'person'" label="选择整理人物">
          <el-select
            v-model="selectedPeople"
            multiple
            filterable
            placeholder="请选择人物 (默认全选)"
            :loading="loadingOptions"
            class="w-full max-w-2xl"
          >
            <el-option
              v-for="item in previewOptions"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
        </el-form-item>

        <el-form-item v-if="strategy === 'location'" label="位置粒度" required>
          <el-radio-group v-model="locationGranularity" class="w-full grid grid-cols-2 sm:grid-cols-3 gap-4">
            <el-radio-button label="province" class="!w-full">仅省份 (如: 浙江省)</el-radio-button>
            <el-radio-button label="city" class="!w-full">仅城市 (如: 杭州市)</el-radio-button>
            <el-radio-button label="district" class="!w-full">仅区县 (如: 西湖区)</el-radio-button>
            <el-radio-button label="province_city" class="!w-full">省-市</el-radio-button>
            <el-radio-button label="city_district" class="!w-full">市-区</el-radio-button>
            <el-radio-button label="province_city_district" class="!w-full">省-市-区</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="strategy === 'location'" label="位置目录结构" required>
          <div class="flex flex-col gap-2">
            <el-radio-group v-model="locationFormat">
              <el-radio label="flat" size="large">平铺结构 (例如: 浙江省-杭州市)</el-radio>
              <el-radio label="nested" size="large">递归结构 (例如: 浙江省/杭州市)</el-radio>
            </el-radio-group>
            <div class="text-xs text-gray-500 bg-gray-50 dark:bg-gray-900/50 p-3 rounded-lg border border-gray-100 dark:border-gray-800">
              <ul class="list-disc pl-4 space-y-1">
                <li><strong>平铺结构：</strong> 将位置信息拼接为单个文件夹名称，不会有层级嵌套。</li>
                <li><strong>递归结构：</strong> 会按照省份、城市、区县依次创建多层级的文件夹结构。</li>
              </ul>
            </div>
          </div>
        </el-form-item>

        <el-form-item v-if="strategy === 'location'" label="选择整理位置">
          <el-select
            v-model="selectedLocations"
            multiple
            filterable
            placeholder="请选择位置 (默认全选)"
            :loading="loadingOptions"
            class="w-full max-w-2xl"
          >
            <el-option
              v-for="item in previewOptions"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="操作类型" required>
          <el-radio-group v-model="actionType">
            <el-radio label="move" size="large">移动 (原文件会被移走)</el-radio>
            <el-radio label="copy" size="large">复制 (保留原文件，生成新副本)</el-radio>
          </el-radio-group>
        </el-form-item>

        <div class="flex justify-end mt-8">
          <el-button 
            type="primary" 
            size="large" 
            :loading="starting" 
            :disabled="!targetRootPath || isTaskRunning"
            @click="startOrganize"
          >
            开始整理
          </el-button>
        </div>
      </el-form>
    </div>

    <!-- Folder Selection Dialog (Reused but slightly modified logic) -->
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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { ArrowLeft, Folder, Loader2, CheckCircle2, XCircle } from 'lucide-vue-next'
import { toolboxApi } from '@/api/toolbox'
import { tasksApi } from '@/api/tasks'
import { settingsApi } from '@/api/settings'
import { ElMessage } from 'element-plus'
import type { Task as TaskResponse } from '@/api/tasks'

const targetRootPath = ref('')
const tempSelectedPath = ref('')
const strategy = ref('time')
const timeGranularity = ref('ym')
const timeFormat = ref('flat')
const locationGranularity = ref('province_city')
const locationFormat = ref('flat')
const actionType = ref('move')
const starting = ref(false)
const clearing = ref(false)

const timeRange = ref<[string, string] | null>(null)
const selectedCategories = ref<string[]>([])
const selectedPeople = ref<string[]>([])
const selectedLocations = ref<string[]>([])

const previewOptions = ref<string[]>([])
const loadingOptions = ref(false)

const showFolderSelector = ref(false)

const activeTask = ref<TaskResponse | null>(null)
let pollTimer: number | undefined

watch([strategy, locationGranularity, locationFormat], async () => {
  if (['category', 'person', 'location'].includes(strategy.value)) {
    loadingOptions.value = true
    try {
      const res = await toolboxApi.getOrganizePreviewOptions({
        strategy: strategy.value,
        location_granularity: locationGranularity.value,
        location_format: locationFormat.value
      })
      previewOptions.value = res.options || []
      
      // Auto select all by default when options change
      if (strategy.value === 'category') {
        selectedCategories.value = [...previewOptions.value]
      } else if (strategy.value === 'person') {
        selectedPeople.value = [...previewOptions.value]
      } else if (strategy.value === 'location') {
        selectedLocations.value = [...previewOptions.value]
      }
    } catch (e) {
      console.error('Failed to fetch preview options', e)
    } finally {
      loadingOptions.value = false
    }
  }
}, { immediate: true })

const isTaskRunning = computed(() => {
  return activeTask.value?.status === 'pending' || activeTask.value?.status === 'processing'
})

const statusText = computed(() => {
  if (!activeTask.value) return ''
  switch (activeTask.value.status) {
    case 'pending': return '等待中'
    case 'processing': return '整理中'
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
    const task = await toolboxApi.getLatestOrganizeTask()
    activeTask.value = task
    
    if (task && (task.status === 'pending' || task.status === 'processing')) {
      startPolling()
    }
  } catch (e) {
    console.error('Failed to fetch latest organize task', e)
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
          ElMessage.success('图片整理已完成')
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

const startOrganize = async () => {
  if (!targetRootPath.value) {
    ElMessage.warning('请选择目标目录')
    return
  }
  
  starting.value = true
  try {
    const payload: any = {
      target_root_path: targetRootPath.value,
      strategy: strategy.value,
      action: actionType.value
    }
    if (strategy.value === 'time') {
      payload.time_granularity = timeGranularity.value
      payload.time_format = timeFormat.value
      if (timeRange.value && timeRange.value.length === 2) {
        payload.time_range = timeRange.value
      }
    } else if (strategy.value === 'location') {
      payload.location_granularity = locationGranularity.value
      payload.location_format = locationFormat.value
      if (selectedLocations.value && selectedLocations.value.length > 0) {
        payload.locations = selectedLocations.value
      }
    } else if (strategy.value === 'category') {
      if (selectedCategories.value && selectedCategories.value.length > 0) {
        payload.categories = selectedCategories.value
      }
    } else if (strategy.value === 'person') {
      if (selectedPeople.value && selectedPeople.value.length > 0) {
        payload.people = selectedPeople.value
      }
    }

    const task = await toolboxApi.createOrganizeTask(payload)
    activeTask.value = task
    ElMessage.success('已开始整理任务')
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
    await tasksApi.deleteFailedTasks(['ORGANIZE_PHOTOS'])
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

<style scoped>
:deep(.el-radio-button__inner) {
  width: 100%;
}
</style>
