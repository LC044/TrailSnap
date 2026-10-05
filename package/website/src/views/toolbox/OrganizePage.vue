<template>
  <div class="mx-auto w-full max-w-4xl px-[var(--ts-page-gutter)] py-6">
    <div class="flex items-center gap-4 mb-6">
      <BackButton label="返回工具箱" @click="goBack" />
      <div>
        <h1 class="ts-page-title text-gray-800 dark:text-white">图片文件整理</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400">按照特定规则自动将照片分类整理到指定的外部文件夹中。</p>
      </div>
    </div>

    <TaskStatusCard :task="activeTask" processing-label="整理中" :clearing="clearing" @clear="clearFailedTask" />

    <!-- Configuration Form -->
    <div class="ts-surface p-6">
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
          <div class="text-xs text-gray-500 mt-1 dark:text-gray-400">选中的目录必须是已配置的外部图库或主存储目录。子文件夹将在此目录下自动创建。</div>
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
          <div class="text-xs text-gray-500 mt-1 dark:text-gray-400">留空则默认整理所有时间的照片。</div>
        </el-form-item>

        <el-form-item v-if="strategy === 'time'" label="时间目录结构" required>
          <div class="flex flex-col gap-2">
            <el-radio-group v-model="timeFormat">
              <el-radio label="flat" size="large">平铺结构 (例如: 2026-01-01)</el-radio>
              <el-radio label="nested" size="large">递归结构 (例如: 2026/01/01)</el-radio>
            </el-radio-group>
            <div class="text-xs text-gray-500 bg-gray-50 dark:bg-gray-900/50 p-3 rounded-lg border border-gray-100 dark:border-gray-800 dark:text-gray-400">
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
            <div class="text-xs text-gray-500 bg-gray-50 dark:bg-gray-900/50 p-3 rounded-lg border border-gray-100 dark:border-gray-800 dark:text-gray-400">
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
    <DirectoryPickerDialog v-model:visible="showFolderSelector" v-model="targetRootPath" />


  </div>
</template>

<script setup lang="ts">
import BackButton from '@/components/ui/BackButton.vue'
import { ref, watch } from 'vue'
import TaskStatusCard from '@/components/TaskStatusCard.vue'
import DirectoryPickerDialog from '@/components/DirectoryPickerDialog.vue'
import { useTaskMonitor } from '@/composables/useTaskMonitor'
import { useAppBack } from '@/composables/useAppBack'
import { Folder } from 'lucide-vue-next'
import { toolboxApi } from '@/api/toolbox'
import { ElMessage } from 'element-plus'

const goBack = useAppBack('/toolbox')

const targetRootPath = ref('')
const strategy = ref('time')
const timeGranularity = ref('ym')
const timeFormat = ref('flat')
const locationGranularity = ref('province_city')
const locationFormat = ref('flat')
const actionType = ref('move')
const starting = ref(false)

const timeRange = ref<[string, string] | null>(null)
const selectedCategories = ref<string[]>([])
const selectedPeople = ref<string[]>([])
const selectedLocations = ref<string[]>([])

const previewOptions = ref<string[]>([])
const loadingOptions = ref(false)

const showFolderSelector = ref(false)


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

const { activeTask, isTaskRunning, clearing, clearFailedTask: clearTask } = useTaskMonitor({
  loadLatest: () => toolboxApi.getLatestOrganizeTask(),
  taskType: 'ORGANIZE_PHOTOS',
  onCompleted: () => ElMessage.success('图片整理已完成'),
  onError: error => console.error('Failed to monitor task', error),
})

const clearFailedTask = async () => {
  try { await clearTask(); ElMessage.success('已清除失败任务') }
  catch { ElMessage.error('清除任务失败') }
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
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '创建任务失败')
  } finally {
    starting.value = false
  }
}

</script>

<style scoped>
:deep(.el-radio-button__inner) {
  width: 100%;
}
</style>
