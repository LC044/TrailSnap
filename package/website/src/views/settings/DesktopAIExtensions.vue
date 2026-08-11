<template>
  <section class="space-y-6">
    <div>
      <h2 class="text-xl md:text-2xl font-semibold text-gray-800 dark:text-white">AI 扩展包</h2>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">
        AI 能力独立于基础安装包，安装后仅在 OCR、票据识别或图片分类首次使用时启动。
      </p>
    </div>

    <div v-if="!desktopAvailable" class="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5">
      <p class="font-medium text-gray-800 dark:text-gray-100">仅 TrailSnap 桌面版支持扩展包管理</p>
      <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">当前页面未连接到桌面扩展管理接口。</p>
    </div>

    <template v-else>
      <div class="flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
        <span class="inline-flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
          <span class="h-2.5 w-2.5 rounded-full" :class="gateway.running ? 'bg-primary-500' : 'bg-gray-300 dark:bg-gray-600'" />
          AI Sidecar：{{ gateway.running ? '运行中' : '按需待机' }}
        </span>
        <button
          class="ml-auto rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          @click="importPackage"
        >
          离线导入
        </button>
        <button
          class="rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          @click="refreshCatalog"
        >
          刷新清单
        </button>
      </div>

      <p v-if="catalogError" class="rounded-lg bg-amber-50 dark:bg-amber-950/30 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
        在线清单暂不可用：{{ catalogError }}。仍可使用已安装扩展或离线导入。
      </p>

      <article
        v-for="extension in extensions"
        :key="extension.id"
        class="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5"
      >
        <div class="flex flex-col gap-4 sm:flex-row sm:items-start">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="font-semibold text-gray-800 dark:text-gray-100">{{ extension.name }}</h3>
              <span class="rounded-full bg-gray-100 dark:bg-gray-700 px-2 py-0.5 text-xs text-gray-600 dark:text-gray-300">
                v{{ extension.installed?.version || extension.version }}
              </span>
              <span v-if="extension.installed" class="rounded-full bg-primary-500/10 px-2 py-0.5 text-xs text-primary-600 dark:text-primary-500">已安装</span>
            </div>
            <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">{{ extension.description }}</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <span v-for="capability in extension.capabilities" :key="capability" class="rounded-md bg-gray-100 dark:bg-gray-700 px-2 py-1 text-xs text-gray-600 dark:text-gray-300">
                {{ capabilityLabels[capability] || capability }}
              </span>
            </div>
            <p class="mt-3 text-xs text-gray-400 dark:text-gray-500">
              下载 {{ formatBytes(extension.downloadSize) }} · 磁盘约 {{ extension.requirements?.diskMB || '—' }} MB · 内存建议 {{ extension.requirements?.memoryMB || '—' }} MB
            </p>
          </div>

          <div class="flex shrink-0 gap-2">
            <button
              v-if="!extension.installed && !isBusy(extension)"
              :disabled="!extension.available"
              class="rounded-lg bg-primary-500 px-4 py-2 text-sm text-white hover:bg-primary-600 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              @click="install(extension.id)"
            >
              {{ extension.available ? '安装' : '等待发布' }}
            </button>
            <button
              v-if="extension.job?.status === 'downloading'"
              class="rounded-lg border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm text-gray-700 dark:text-gray-200 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              @click="runAction(extension.id, 'pause')"
            >暂停</button>
            <button
              v-if="['paused', 'failed'].includes(extension.job?.status || '')"
              class="rounded-lg bg-primary-500 px-4 py-2 text-sm text-white hover:bg-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              @click="runAction(extension.id, 'retry')"
            >重试</button>
            <button
              v-if="extension.installed"
              class="rounded-lg border border-red-300 dark:border-red-800 px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              @click="uninstall(extension.id)"
            >卸载</button>
          </div>
        </div>

        <div v-if="extension.job && !extension.installed" class="mt-4">
          <div class="mb-1 flex justify-between text-xs text-gray-500 dark:text-gray-400">
            <span>{{ statusLabels[extension.job.status] || extension.job.status }}</span>
            <span>{{ extension.job.progress || 0 }}%</span>
          </div>
          <div class="h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700">
            <div class="h-full rounded-full bg-primary-500 transition-all" :style="{ width: `${extension.job.progress || 0}%` }" />
          </div>
          <p v-if="extension.job.error" class="mt-2 text-xs text-red-600 dark:text-red-400">{{ extension.job.error }}</p>
        </div>
      </article>

      <section v-if="extensions.some(item => item.installed)" class="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5">
        <div class="flex flex-wrap items-start gap-3">
          <div class="min-w-0 flex-1">
            <h3 class="font-semibold text-gray-800 dark:text-gray-100">AI 模型管理</h3>
            <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">RapidOCR 小型资源已包含在扩展中；图片分类和票据模型由 AI 服务从 ModelScope 下载，Server 提供管理入口。</p>
          </div>
          <button
            class="rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="loadModels"
          >刷新模型</button>
        </div>
        <p v-if="modelsError" class="mt-4 rounded-lg bg-amber-50 dark:bg-amber-950/30 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">{{ modelsError }}</p>
        <div v-for="model in models" :key="model.id" class="mt-4 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-medium text-gray-800 dark:text-gray-100">{{ model.name }}</span>
                <span class="rounded-full bg-gray-100 dark:bg-gray-700 px-2 py-0.5 text-xs text-gray-600 dark:text-gray-300">{{ modelStatusLabels[model.status] || model.status }}</span>
              </div>
              <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ model.description }}</p>
              <p class="mt-2 text-xs text-gray-400 dark:text-gray-500">下载 {{ formatBytes(model.downloadSize) }} · 磁盘约 {{ model.requirements?.diskMB || '—' }} MB</p>
            </div>
            <div class="flex shrink-0 gap-2">
              <button
                v-if="model.status !== 'ready'"
                :disabled="model.status === 'downloading'"
                class="rounded-lg bg-primary-500 px-4 py-2 text-sm text-white hover:bg-primary-600 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
                @click="downloadModel(model.id)"
              >{{ model.status === 'downloading' ? '下载中' : model.status === 'failed' ? '重试' : '下载模型' }}</button>
              <button
                v-if="model.status === 'ready'"
                class="rounded-lg border border-red-300 dark:border-red-800 px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
                @click="deleteModel(model.id)"
              >删除模型</button>
            </div>
          </div>
          <p v-if="model.error" class="mt-2 text-xs text-red-600 dark:text-red-400">{{ model.error }}</p>
        </div>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { settingsApi } from '@/api/settings'
import { isTauriApp } from '@/config/server'

const desktopAvailable = ref(true)
const extensions = ref<any[]>([])
const gateway = ref<any>({ running: false })
const catalogError = ref<string | null>(null)
const models = ref<any[]>([])
const modelsError = ref<string | null>(null)
const modelsLoaded = ref(false)
let pollTimer: number | undefined
let modelPollTimer: number | undefined

const capabilityLabels: Record<string, string> = { ocr: '文字识别', tickets: '票据识别', classification: '图片分类' }
const statusLabels: Record<string, string> = { downloading: '下载中', paused: '已暂停', failed: '失败', verifying: '校验中', installing: '安装中' }
const modelStatusLabels: Record<string, string> = { pending: '未下载', downloading: '下载中', ready: '已就绪', failed: '下载失败' }

async function desktopRequest(path: string, options?: RequestInit) {
  if (isTauriApp()) {
    const { invoke } = await import('@tauri-apps/api/core')
    if (!path) return invoke('ai_extension_list')
    if (path === '/refresh') return invoke('ai_extension_refresh')
    const match = path.match(/^\/([^/]+)\/(install|pause|retry|uninstall)$/)
    if (!match) throw new Error(`未知桌面扩展操作：${path}`)
    const [, encodedId, action] = match
    const command = `ai_extension_${action}`
    return invoke(command, { id: decodeURIComponent(encodedId) })
  }
  const response = await fetch(`/desktop-api/ai/extensions${path}`, {
    ...options,
    headers: { 'content-type': 'application/json', ...(options?.headers || {}) },
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`)
  return data
}

async function load() {
  try {
    const data = await desktopRequest('')
    desktopAvailable.value = true
    extensions.value = data.extensions || []
    gateway.value = data.gateway || { running: false }
    catalogError.value = data.catalogError
    if (extensions.value.some(item => item.installed) && !modelsLoaded.value) void loadModels()
  } catch {
    desktopAvailable.value = false
  }
}

const isBusy = (extension: any) => ['downloading', 'verifying', 'installing'].includes(extension.job?.status)
const formatBytes = (value?: number) => value ? `${(value / 1024 / 1024).toFixed(1)} MB` : '待发布'

async function install(id: string) {
  try { await desktopRequest(`/${encodeURIComponent(id)}/install`, { method: 'POST', body: '{}' }); await load() }
  catch (error: any) { ElMessage.error(error.message) }
}
async function runAction(id: string, action: string) {
  try { await desktopRequest(`/${encodeURIComponent(id)}/${action}`, { method: 'POST' }); await load() }
  catch (error: any) { ElMessage.error(error.message) }
}
async function uninstall(id: string) {
  try {
    await ElMessageBox.confirm('卸载 AI 运行时；模型和 PostgreSQL 中的分析结果将保留，可在模型管理中单独删除。', '卸载 AI 扩展包')
    await desktopRequest(`/${encodeURIComponent(id)}/uninstall`, { method: 'DELETE' })
    await load()
  } catch (error: any) { if (error !== 'cancel') ElMessage.error(error.message || String(error)) }
}
async function importPackage() {
  try {
    if (isTauriApp()) {
      const [{ invoke }, { open }] = await Promise.all([
        import('@tauri-apps/api/core'),
        import('@tauri-apps/plugin-dialog'),
      ])
      const selected = await open({
        multiple: false,
        directory: false,
        filters: [{ name: 'TrailSnap AI 扩展包', extensions: ['gz', 'tgz'] }],
      })
      if (!selected) return
      await invoke('ai_extension_import', { path: selected })
      ElMessage.success('AI 扩展包导入成功')
      await load()
      return
    }
    const result = await desktopRequest('/import', { method: 'POST', body: '{}' })
    if (!result.canceled) ElMessage.success('AI 扩展包导入成功')
    await load()
  } catch (error: any) { ElMessage.error(error.message) }
}
async function refreshCatalog() {
  try { await desktopRequest('/refresh', { method: 'POST', body: '{}' }); await load() }
  catch (error: any) { ElMessage.error(error.message) }
}

async function loadModels() {
  try {
    const result: any = await settingsApi.getAIModels()
    models.value = result.models || []
    modelsError.value = null
    modelsLoaded.value = true
    if (!models.value.some(model => model.status === 'downloading') && modelPollTimer) {
      window.clearInterval(modelPollTimer)
      modelPollTimer = undefined
    }
  } catch (error: any) {
    modelsError.value = error.message || 'AI 模型服务不可用'
  }
}

async function downloadModel(id: string) {
  try {
    await settingsApi.downloadAIModel(id)
    ElMessage.success('模型下载已开始')
    await loadModels()
    if (!modelPollTimer) modelPollTimer = window.setInterval(loadModels, 1500)
  } catch (error: any) { ElMessage.error(error.message || String(error)) }
}

async function deleteModel(id: string) {
  try {
    await ElMessageBox.confirm('删除本地 AI 模型文件？扩展运行时和 PostgreSQL 分析结果不会被删除。', '删除 AI 模型')
    await settingsApi.deleteAIModel(id)
    await loadModels()
  } catch (error: any) { if (error !== 'cancel') ElMessage.error(error.message || String(error)) }
}

onMounted(() => { load(); pollTimer = window.setInterval(load, 1200) })
onUnmounted(() => {
  window.clearInterval(pollTimer)
  if (modelPollTimer) window.clearInterval(modelPollTimer)
})
</script>
