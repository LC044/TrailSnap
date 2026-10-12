<template>
  <section class="space-y-6">
    <div>
      <h2 class="text-xl md:text-2xl font-semibold text-gray-800 dark:text-white">AI 扩展包</h2>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">
        AI 能力独立于基础安装包，安装后在人脸、OCR、分类、语义检索或本地 LLM 首次使用时启动。
      </p>
    </div>

    <div
      v-if="guideFeature"
      class="rounded-xl border border-primary-500/30 bg-primary-500/10 p-4 md:p-5"
    >
      <div class="flex flex-col gap-4 sm:flex-row sm:items-center">
        <div class="min-w-0 flex-1">
          <p class="font-semibold text-gray-800 dark:text-gray-100">启用{{ guideFeature.name }}</p>
          <p class="mt-1 text-sm text-gray-600 dark:text-gray-300">
            {{ guideFeature.description }}。先安装包含该能力的 AI 扩展包；扩展安装完成后，可在“AI 模型管理”中查看模型下载状态。
          </p>
        </div>
        <button
          v-if="guideInstalled && guideRedirect"
          class="shrink-0 rounded-lg bg-primary-500 px-4 py-2 text-sm text-white hover:bg-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          @click="returnToFeature"
        >返回{{ guideFeature.name }}</button>
        <button
          v-else-if="recommendedExtension"
          :disabled="busy || !recommendedExtension.available || isBusy(recommendedExtension)"
          class="shrink-0 rounded-lg bg-primary-500 px-4 py-2 text-sm text-white hover:bg-primary-600 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          @click="install(recommendedExtension.id)"
        >{{ isBusy(recommendedExtension) ? '正在下载安装…' : recommendedExtension.available ? '下载并安装 AI 扩展' : '扩展等待发布' }}</button>
      </div>
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
          :disabled="busy || importingPackage"
          class="ts-button ts-button-secondary ml-auto"
          @click="importPackage"
        >
          {{ importingPackage ? '正在校验并导入…' : '离线导入' }}
        </button>
        <button
          :disabled="checking"
          class="ts-button ts-button-secondary"
          @click="refreshCatalog"
        >
          {{ checking ? '正在检查…' : '检查更新' }}
        </button>
      </div>

      <div class="ts-surface space-y-2 p-4 text-sm">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <span class="ts-muted">当前平台：{{ platform || '正在检测…' }} · 客户端 v{{ clientVersion }}</span>
          <a :href="releasePageUrl" target="_blank" rel="noopener noreferrer" class="ts-button ts-button-secondary">官方下载页</a>
        </div>
        <p v-if="snapshot?.serverVersion" class="ts-muted">
          Server v{{ snapshot.serverVersion }} · 最低支持 AI 扩展 v{{ snapshot.minimumAIExtensionVersion || '—' }}
        </p>
        <p class="ts-muted">下载后无需解压，点击“离线导入”。兼容旧版可继续使用，无需随客户端升级重复下载。</p>
      </div>

      <p v-if="catalogError" class="rounded-lg bg-amber-50 dark:bg-amber-950/30 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
        在线清单暂不可用：{{ catalogError }}。满足最低版本的已安装扩展可继续使用，也可离线导入。
      </p>

      <section class="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-center">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="font-semibold text-gray-800 dark:text-gray-100">llama.cpp 运行时</h3>
              <span
                class="rounded-full px-2 py-0.5 text-xs"
                :class="llamaStatus.installed ? 'bg-primary-500/10 text-primary-600 dark:text-primary-500' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'"
              >{{ llamaStatus.installed ? '已安装' : '未安装' }}</span>
            </div>
            <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">MiniCPM 本地模型需要 llama-server。它独立于 AI 扩展安装，并在调用前检测可用性。</p>
            <p v-if="llamaStatus.installed" class="mt-2 break-all text-xs text-gray-400 dark:text-gray-500">可执行文件：{{ llamaStatus.path }}</p>
            <p v-else class="mt-2 text-xs text-gray-400 dark:text-gray-500">{{ llamaStatus.installCommand }}</p>
          </div>
          <div class="flex shrink-0 gap-2">
            <button
              class="rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              @click="loadLlamaStatus"
            >重新检测</button>
            <button
              v-if="!llamaStatus.installed"
              :disabled="busy || installingLlama || !llamaStatus.installSupported"
              class="rounded-lg bg-primary-500 px-4 py-2 text-sm text-white hover:bg-primary-600 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              @click="installLlama"
            >{{ installingLlama ? '安装中…' : '一键安装' }}</button>
          </div>
        </div>
      </section>

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
              <span class="ts-muted text-xs">{{ compatibilityLabels[extension.compatibility] || '兼容性未知' }}</span>
              <span v-if="extension.installed && extension.updateVersion" class="text-xs text-primary-600 dark:text-primary-400">可更新至 v{{ extension.updateVersion }}</span>
            </div>
            <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">{{ extension.description }}</p>
            <p v-if="extension.compatibilityReason" class="ts-muted mt-2 text-sm" role="status">{{ extension.compatibilityReason }}</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <span v-for="capability in extension.capabilities" :key="capability" class="rounded-md bg-gray-100 dark:bg-gray-700 px-2 py-1 text-xs text-gray-600 dark:text-gray-300">
                {{ capabilityLabels[capability] || capability }}
              </span>
            </div>
            <p class="mt-3 text-xs text-gray-400 dark:text-gray-500">
              下载 {{ formatBytes(extension.downloadSize) }} · 磁盘约 {{ extension.requirements?.diskMB || '—' }} MB · 内存建议 {{ extension.requirements?.memoryMB || '—' }} MB
            </p>
            <div class="mt-3 flex flex-wrap items-center gap-2 text-sm">
              <a v-if="extension.downloadUrl" :href="extension.downloadUrl" target="_blank" rel="noopener noreferrer" class="ts-button ts-button-secondary ts-button-sm">手动下载</a>
              <span v-if="extension.downloadFilename" class="ts-muted min-w-0 break-all text-xs">{{ extension.downloadFilename }}</span>
              <span v-else class="ts-muted text-xs">暂无当前平台附件，可前往官方下载页查找兼容版本，再离线导入。</span>
            </div>
          </div>

          <div class="flex shrink-0 flex-wrap gap-2">
            <button
              v-if="(!extension.installed || extension.updateVersion) && !isBusy(extension) && !['failed', 'paused'].includes(extension.job?.status || '')"
              :disabled="busy || !extension.available"
              class="ts-button ts-button-primary"
              @click="install(extension.id)"
            >
              {{ extension.available ? extension.installed ? '下载更新' : '安装' : '暂无兼容附件' }}
            </button>
            <button
              v-if="extension.job?.status === 'downloading'"
              class="ts-button ts-button-secondary"
              @click="runAction(extension.id, 'pause')"
            >暂停</button>
            <button
              v-if="['paused', 'failed'].includes(extension.job?.status || '')"
              :disabled="busy"
              class="ts-button ts-button-primary"
              @click="runAction(extension.id, 'retry')"
            >重试</button>
            <button
              v-if="extension.installed"
              :disabled="busy || isBusy(extension)"
              class="ts-button ts-button-danger"
              @click="uninstall(extension.id)"
            >卸载</button>
          </div>
        </div>

        <div v-if="extension.job && extension.job.status !== 'installed'" class="mt-4" role="status" aria-live="polite">
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

    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { isTauriApp } from '@/config/server'
import { storeToRefs } from 'pinia'
import { useDesktopAIExtensionsStore } from '@/stores/desktopAIExtensions'
import { extensionIsBusy, type ExtensionAction } from '@/api/desktopAIExtensions'

const route = useRoute()
const router = useRouter()

const extensionStore = useDesktopAIExtensionsStore()
const { snapshot, desktopAvailable, catalogError, checking, busy } = storeToRefs(extensionStore)
const extensions = computed(() => snapshot.value.extensions)
const gateway = computed(() => snapshot.value.gateway)
const platform = computed(() => snapshot.value.platform)
const clientVersion = computed(() => snapshot.value.clientVersion)
const releasePageUrl = computed(() => snapshot.value.releasePageUrl || 'https://github.com/LC044/TrailSnap/releases')
const llamaStatus = ref<any>({ installed: false, installSupported: false, installCommand: '正在检测…' })
const installingLlama = ref(false)
const importingPackage = ref(false)
let pollTimer: number | undefined

const capabilityLabels: Record<string, string> = {
  face: '人脸识别',
  ocr: '文字识别',
  object_detection: '目标检测',
  tickets: '票据识别',
  classification: '图片分类',
  embedding: 'CLIP 向量',
  llm: '本地 LLM',
  emotion: '情绪色彩',
}
const statusLabels: Record<string, string> = { downloading: '下载中', paused: '已暂停', failed: '失败', verifying: '校验中', draining: '等待任务与模型下载结束', installing: '安装中' }
const compatibilityLabels: Record<string, string> = { unknown: '兼容性未知', compatible: '满足 Server 最低版本', required_update: '必须更新', not_installed: '未安装' }
const guideFeatures: Record<string, { name: string; description: string }> = {
  face: { name: '人脸识别', description: '人脸识别会检测照片中的人脸并生成人物相册' },
  classification: { name: '智能分类', description: '智能分类会分析照片内容并生成分类相册' },
}
const guideCapability = computed(() => typeof route.query.guide === 'string' ? route.query.guide : '')
const guideFeature = computed(() => guideFeatures[guideCapability.value])
const guideRedirect = computed(() => {
  const value = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  return value.startsWith('/') && !value.startsWith('//') ? value : ''
})
const guideInstalled = computed(() => extensions.value.some(extension =>
  extension.installed?.capabilities?.includes(guideCapability.value),
))
const recommendedExtension = computed(() => extensions.value.find(extension =>
  !extension.installed && extension.capabilities?.includes(guideCapability.value),
))

const load = () => extensionStore.load()
const isBusy = extensionIsBusy
const formatBytes = (value?: number) => value ? `${(value / 1024 / 1024).toFixed(1)} MB` : '待发布'

async function install(id: string) {
  try { await extensionStore.action(id, 'install') }
  catch (error: any) { ElMessage.error(error.message) }
}
async function runAction(id: string, action: ExtensionAction) {
  try { await extensionStore.action(id, action) }
  catch (error: any) { ElMessage.error(error.message) }
}
async function uninstall(id: string) {
  try {
    await ElMessageBox.confirm('等待在途任务及模型下载结束后卸载 AI 运行时。照片、独立模型和分析结果将保留；重新安装后任务自动继续。', '卸载 AI 扩展包')
    await extensionStore.action(id, 'uninstall')
  } catch (error: any) { if (error !== 'cancel') ElMessage.error(error.message || String(error)) }
}
async function importPackage() {
  importingPackage.value = true
  try {
    const result = await extensionStore.importArchive()
    if (!result.canceled) ElMessage.success('AI 扩展包导入成功')
    await load()
  } catch (error: any) { ElMessage.error(error.message) }
  finally { importingPackage.value = false }
}
async function refreshCatalog() {
  try { await extensionStore.refresh() }
  catch (error: any) { ElMessage.error(error.message) }
}
function returnToFeature() {
  if (guideRedirect.value) void router.push(guideRedirect.value)
}

async function loadLlamaStatus() {
  if (!isTauriApp()) return
  try {
    const { invoke } = await import('@tauri-apps/api/core')
    llamaStatus.value = await invoke('llama_runtime_status')
  } catch (error: any) {
    ElMessage.error(error.message || '无法检测 llama-server')
  }
}

async function installLlama() {
  installingLlama.value = true
  try {
    const { invoke } = await import('@tauri-apps/api/core')
    llamaStatus.value = await invoke('llama_runtime_install')
    ElMessage.success('llama.cpp 安装并验证成功')
  } catch (error: any) {
    ElMessage.error(error.message || String(error))
    await loadLlamaStatus()
  } finally {
    installingLlama.value = false
  }
}

onMounted(() => { load(); void loadLlamaStatus(); pollTimer = window.setInterval(load, 1200) })
onUnmounted(() => {
  window.clearInterval(pollTimer)
})
</script>
