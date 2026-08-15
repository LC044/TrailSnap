<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start">
      <div class="min-w-0 flex-1">
        <h2 class="text-xl font-semibold text-gray-800 dark:text-white md:text-2xl">AI 模型管理</h2>
        <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">
          AI 服务启动后会自动下载全部默认模型；也可以在这里手动下载、失败重试、删除后重新下载，并在未来有多个候选模型时进行切换。
        </p>
      </div>
      <button
        :disabled="loading"
        class="shrink-0 rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
        @click="loadModels"
      >{{ loading ? '刷新中…' : '刷新状态' }}</button>
    </div>

    <div class="rounded-xl border border-primary-500/30 bg-primary-500/10 p-4 text-sm text-gray-600 dark:text-gray-300">
      模型文件和选择配置均保存在 AI 服务的数据目录中。Docker 与桌面端通过相同的模型管理 API 操作当前连接的 AI 服务。
    </div>

    <div v-if="errorMessage" class="rounded-xl border border-amber-200 bg-amber-50 p-5 dark:border-amber-900 dark:bg-amber-950/30">
      <p class="font-medium text-amber-800 dark:text-amber-300">暂时无法连接 AI 模型服务</p>
      <p class="mt-1 break-words text-sm text-amber-700 dark:text-amber-400">{{ errorMessage }}</p>
      <button
        class="mt-4 rounded-lg bg-primary-500 px-4 py-2 text-sm text-white hover:bg-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
        @click="loadModels"
      >重新检测</button>
    </div>

    <template v-else>
      <section v-if="selectionEntries.length" class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
        <h3 class="font-semibold text-gray-800 dark:text-gray-100">当前模型选择</h3>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">只有一个候选项时无需切换；以后服务增加模型后会自动出现在下拉列表中。</p>
        <div class="mt-4 grid gap-4 md:grid-cols-2">
          <label v-for="[task, selection] in selectionEntries" :key="task" class="block">
            <span class="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-200">{{ taskLabels[task] || task }}</span>
            <select
              :value="selection.selected"
              :disabled="switchingTask === task || selection.available?.length < 2 || !canSwitchTask(task)"
              class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
              @change="selectModel(task, $event)"
            >
              <option v-for="modelName in selection.available || []" :key="modelName" :value="modelName">{{ modelName }}</option>
            </select>
          </label>
        </div>
      </section>

      <div v-if="!models.length && !loading" class="rounded-xl border border-gray-200 bg-white p-6 text-center text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400">
        当前 AI 服务没有注册可管理的模型。
      </div>

      <article v-for="model in models" :key="model.id" class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-start">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="font-semibold text-gray-800 dark:text-gray-100">{{ model.name || model.id }}</h3>
              <span class="rounded-full px-2 py-0.5 text-xs" :class="statusClasses[model.status] || statusClasses.pending">
                {{ statusLabels[model.status] || model.status }}
              </span>
            </div>
            <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">{{ model.description }}</p>
            <div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400 dark:text-gray-500">
              <span>下载 {{ formatBytes(model.downloadSize) }}</span>
              <span>磁盘约 {{ model.requirements?.diskMB || '—' }} MB</span>
              <span v-if="model.source">来源 {{ model.source }}</span>
            </div>
            <p v-if="model.error" class="mt-3 break-words text-xs text-red-600 dark:text-red-400">{{ model.error }}</p>
          </div>
          <div class="flex shrink-0 flex-wrap gap-2">
            <button
              v-if="model.status !== 'ready'"
              :disabled="model.status === 'downloading' || activeModel === model.id"
              class="rounded-lg bg-primary-500 px-4 py-2 text-sm text-white hover:bg-primary-600 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
              @click="downloadModel(model.id)"
            >{{ model.status === 'downloading' ? '自动下载中…' : model.status === 'failed' ? '重试下载' : '立即下载' }}</button>
            <button
              v-if="model.status === 'ready' && model.canDelete"
              :disabled="activeModel === model.id"
              class="rounded-lg border border-red-300 px-4 py-2 text-sm text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
              @click="deleteModel(model.id)"
            >删除模型</button>
          </div>
        </div>
      </article>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { settingsApi } from '@/api/settings'

type ModelSelection = { selected: string; available: string[]; description?: string }

const models = ref<any[]>([])
const selections = ref<Record<string, ModelSelection>>({})
const loading = ref(false)
const errorMessage = ref('')
const activeModel = ref('')
const switchingTask = ref('')
let pollTimer: number | undefined

const taskLabels: Record<string, string> = {
  ocr: '文字识别',
  face: '人脸识别',
  classification: '智能分类与 CLIP',
  llm: '本地多模态 LLM',
}
const statusLabels: Record<string, string> = {
  pending: '等待下载',
  downloading: '下载中',
  ready: '已就绪',
  failed: '下载失败',
}
const statusClasses: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
  downloading: 'bg-primary-500/10 text-primary-600 dark:text-primary-500',
  ready: 'bg-primary-500/10 text-primary-600 dark:text-primary-500',
  failed: 'bg-red-50 text-red-600 dark:bg-red-950/30 dark:text-red-400',
}
const selectionEntries = computed(() => Object.entries(selections.value))
const formatBytes = (value?: number) => value ? `${(value / 1024 / 1024).toFixed(1)} MB` : '未知'
const canSwitchTask = (task: string) => models.value.some(model => model.task === task)

function updatePolling() {
  const downloading = models.value.some(model => model.status === 'downloading')
  if (downloading && !pollTimer) pollTimer = window.setInterval(() => void loadModels(true), 1500)
  if (!downloading && pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

async function loadModels(silent = false) {
  if (!silent) loading.value = true
  try {
    const result: any = await settingsApi.getAIModels()
    models.value = result.models || []
    selections.value = result.selections || {}
    errorMessage.value = ''
    updatePolling()
  } catch (error: any) {
    errorMessage.value = error.message || 'AI 模型服务不可用'
    if (pollTimer) {
      window.clearInterval(pollTimer)
      pollTimer = undefined
    }
  } finally {
    if (!silent) loading.value = false
  }
}

async function downloadModel(id: string) {
  activeModel.value = id
  try {
    await settingsApi.downloadAIModel(id)
    ElMessage.success('模型下载任务已启动')
    await loadModels(true)
  } catch (error: any) {
    ElMessage.error(error.message || String(error))
  } finally {
    activeModel.value = ''
  }
}

async function deleteModel(id: string) {
  try {
    await ElMessageBox.confirm('删除本地模型文件？需要时可再次下载，已有照片分析结果不会被删除。', '删除 AI 模型', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    activeModel.value = id
    await settingsApi.deleteAIModel(id)
    ElMessage.success('模型文件已删除')
    await loadModels(true)
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error.message || String(error))
  } finally {
    activeModel.value = ''
  }
}

async function selectModel(task: string, event: Event) {
  const model = (event.target as HTMLSelectElement).value
  if (!model || model === selections.value[task]?.selected) return
  switchingTask.value = task
  try {
    await settingsApi.selectAIModel(task, model)
    ElMessage.success(`${taskLabels[task] || task}模型已切换`)
    await loadModels(true)
  } catch (error: any) {
    ElMessage.error(error.message || String(error))
    await loadModels(true)
  } finally {
    switchingTask.value = ''
  }
}

onMounted(() => void loadModels())
onUnmounted(() => {
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>
