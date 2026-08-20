<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start">
      <div class="min-w-0 flex-1">
        <h2 class="text-xl font-semibold text-gray-800 dark:text-white md:text-2xl">AI 模型管理</h2>
        <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">
          选择适合当前设备的模型。
        </p>
      </div>
      <button
        :disabled="loading"
        class="shrink-0 rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
        @click="loadModels"
      >{{ loading ? '刷新中…' : '刷新状态' }}</button>
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
      <div v-if="taskCards.length" class="grid gap-4 xl:grid-cols-2">
        <article
          v-for="card in taskCards"
          :key="card.task"
          class="flex flex-col rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800"
        >
          <div class="flex items-center justify-between gap-3">
            <h3 class="font-semibold text-gray-800 dark:text-gray-100">{{ card.info.name || taskLabels[card.task] || card.task }}</h3>
            <span class="shrink-0 rounded-full px-2 py-0.5 text-xs" :class="statusClasses[card.model.status] || statusClasses.pending">
              {{ statusLabels[card.model.status] || card.model.status }}
            </span>
          </div>

          <label class="mt-4 block">
            <span class="sr-only">选择模型</span>
            <select
              :value="card.info.selected"
              :disabled="switchingTask === card.task || card.info.available.length < 2"
              class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
              @change="selectModel(card.task, $event)"
            >
              <option
                v-for="modelId in card.info.available"
                :key="modelId"
                :value="modelId"
              >{{ modelById(modelId)?.name || modelId }}</option>
            </select>
          </label>

          <div class="mt-4 min-w-0 flex-1">
            <p class="text-sm text-gray-500 dark:text-gray-400">{{ card.model.description }}</p>
            <div v-if="card.model.tags?.length" class="mt-2 flex flex-wrap gap-1.5">
              <span v-for="tag in card.model.tags" :key="tag" class="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-500 dark:bg-gray-700 dark:text-gray-400">{{ tag }}</span>
            </div>
            <div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400 dark:text-gray-500">
              <span>大小 {{ formatBytes(card.model.downloadSize) }}</span>
              <span>建议内存 {{ card.model.requirements?.memoryMB || '—' }} MB</span>
            </div>
            <p v-if="card.model.error" class="mt-3 break-words text-xs text-red-600 dark:text-red-400">{{ card.model.error }}</p>
          </div>

          <div class="mt-4 flex flex-wrap gap-2">
            <button
              v-if="card.model.status !== 'ready'"
              :disabled="card.model.status === 'downloading' || activeModel === card.model.id"
              class="rounded-lg bg-primary-500 px-4 py-2 text-sm text-white hover:bg-primary-600 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
              @click="downloadModel(card.model.id)"
            >{{ card.model.status === 'downloading' ? '下载中…' : card.model.status === 'failed' ? '重试下载' : '下载' }}</button>
            <button
              v-if="card.model.status === 'ready' && card.model.canDelete"
              :disabled="activeModel === card.model.id"
              class="rounded-lg border border-red-300 px-4 py-2 text-sm text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
              @click="deleteModel(card.model.id)"
            >删除模型</button>
          </div>
        </article>
      </div>

      <div v-if="!taskCards.length && !loading" class="rounded-xl border border-gray-200 bg-white p-6 text-center text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400">
        暂无可用模型
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { settingsApi } from '@/api/settings'

type TaskSelection = { name: string; selected: string; available: string[] }

const models = ref<any[]>([])
const tasks = ref<Record<string, TaskSelection>>({})
const loading = ref(false)
const errorMessage = ref('')
const activeModel = ref('')
const switchingTask = ref('')
let pollTimer: number | undefined

const taskLabels: Record<string, string> = {
  ocr: '文字识别',
  face: '人脸识别',
  classification: '图片智能分类',
  embedding: '语义向量与搜索',
  ticket: '票据识别',
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
const formatBytes = (value?: number) => value ? `${(value / 1024 / 1024).toFixed(1)} MB` : '未知'
const modelById = (id: string) => models.value.find(model => model.id === id)
const taskCards = computed(() => Object.entries(tasks.value)
  .map(([task, info]) => ({ task, info, model: modelById(info.selected) }))
  .filter((card): card is { task: string; info: TaskSelection; model: any } => Boolean(card.model)))

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
    models.value = (result.models || []).filter((model: any) => model.available !== false)
    const visibleIds = new Set(models.value.map(model => model.id))
    tasks.value = Object.fromEntries(
      Object.entries(result.tasks || {}).map(([task, info]: [string, any]) => [
        task,
        { ...info, available: (info.available || []).filter((id: string) => visibleIds.has(id)) },
      ]),
    )
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
  if (!model || model === tasks.value[task]?.selected) return
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
