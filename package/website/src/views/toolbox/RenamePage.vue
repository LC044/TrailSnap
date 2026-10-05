<template>
  <div class="mx-auto w-full max-w-4xl px-[var(--ts-page-gutter)] py-6">
    <div class="flex items-center gap-4 mb-6">
      <BackButton label="返回工具箱" @click="goBack" />
      <div>
        <h1 class="ts-page-title text-gray-800 dark:text-white">批量重命名</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400">选择一个文件夹，将其中的图片按拍摄时间 (YYYYMMDD_HHMMSS) 批量重命名。</p>
      </div>
    </div>

    <TaskStatusCard :task="activeTask" processing-label="重命名中" :clearing="clearing" @clear="clearFailedTask" />

    <!-- Configuration Form -->
    <div class="ts-surface p-6">
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
          <div class="text-xs text-gray-500 mt-1 dark:text-gray-400">此文件夹（包含其所有子文件夹）内的所有照片都将被重命名。</div>
        </el-form-item>

        <div class="grid grid-cols-1 gap-6">
          <el-form-item label="命名模板（不含后缀）">
            <el-input v-model="template" placeholder="例如: IMG_{date}_{time}" clearable />
            <div class="mt-3">
              <p class="text-xs text-gray-500 mb-2 dark:text-gray-400">点击变量插入到模板末尾：</p>
              <div class="flex flex-wrap gap-2">
                <el-tag
                  v-for="v in variables"
                  :key="v.value"
                  size="small"
                  type="info"
                  class="cursor-pointer hover:bg-primary-50 dark:hover:bg-primary-900/20 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
                  @click="insertVariable(v.value)"
                >
                  {{ v.label }}
                </el-tag>
              </div>
            </div>
            <div class="text-xs text-gray-500 mt-2 dark:text-gray-400">默认模板为 IMG_{date}_{time}。如果有相同名字的照片，会自动追加 (1), (2)...</div>
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

    <DirectoryPickerDialog v-model:visible="showFolderSelector" v-model="targetRootPath" />


  </div>
</template>

<script setup lang="ts">
import BackButton from '@/components/ui/BackButton.vue'
import { ref, computed } from 'vue'
import TaskStatusCard from '@/components/TaskStatusCard.vue'
import DirectoryPickerDialog from '@/components/DirectoryPickerDialog.vue'
import { useTaskMonitor } from '@/composables/useTaskMonitor'
import { useAppBack } from '@/composables/useAppBack'
import { Folder } from 'lucide-vue-next'
import { toolboxApi } from '@/api/toolbox'
import { ElMessage } from 'element-plus'

const goBack = useAppBack('/toolbox')

const targetRootPath = ref('')
const template = ref('IMG_{date}_{time}')
const starting = ref(false)

const showFolderSelector = ref(false)


const variables = [
  { label: '日期(YYYY-MM-DD)', value: '{date}' },
  { label: '时间(HHMMSS)', value: '{time}' },
  { label: '年(YYYY)', value: '{year}' },
  { label: '月(MM)', value: '{month}' },
  { label: '日(DD)', value: '{day}' },
  { label: '时(HH)', value: '{hour}' },
  { label: '分(mm)', value: '{minute}' },
  { label: '城市', value: '{city}' },
  { label: '地点', value: '{location}' },
  { label: '原名', value: '{original}' },
  { label: '序号', value: '{index}' },
  { label: '3位序号', value: '{sequence3}' },
  { label: '4位序号', value: '{sequence4}' },
  { label: '相机', value: '{camera}' },
  { label: '镜头', value: '{lens}' },
  { label: 'ISO', value: '{iso}' }
]

const insertVariable = (val: string) => {
  template.value += val
}

// Sample values used to render the live preview. Keep these aligned with the
// variables exposed above and with backend `format_export_filename`.
const PREVIEW_VALUES: Record<string, string> = {
  date: '2026-01-01',
  time: '123000',
  year: '2026',
  month: '01',
  day: '01',
  hour: '12',
  minute: '30',
  city: '北京市',
  location: '朝阳区',
  original: '原文件名',
  index: '1',
  sequence3: '001',
  sequence4: '0001',
  camera: 'Apple',
  lens: 'iPhone 13 Pro',
  iso: '100'
}

const previewName = computed(() => {
  let name = template.value || ''
  for (const [key, value] of Object.entries(PREVIEW_VALUES)) {
    name = name.replace(`{${key}}`, value)
  }
  return `${name}.jpg`
})

const { activeTask, isTaskRunning, clearing, clearFailedTask: clearTask } = useTaskMonitor({
  loadLatest: () => toolboxApi.getLatestRenameTask(),
  taskType: 'BATCH_RENAME',
  onCompleted: () => ElMessage.success('批量重命名已完成'),
  onError: error => console.error('Failed to monitor task', error),
})

const clearFailedTask = async () => {
  try { await clearTask(); ElMessage.success('已清除失败任务') }
  catch { ElMessage.error('清除任务失败') }
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
      template: template.value
    }
    const task = await toolboxApi.createRenameTask(payload)
    activeTask.value = task
    ElMessage.success('已开始重命名任务')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '创建任务失败')
  } finally {
    starting.value = false
  }
}

</script>
