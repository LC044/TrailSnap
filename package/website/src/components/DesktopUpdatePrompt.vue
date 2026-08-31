<template>
  <aside
    v-if="visible"
    class="fixed bottom-5 right-5 z-[10000] w-[min(24rem,calc(100vw-2.5rem))] rounded-2xl border border-gray-200 bg-white p-4 shadow-xl dark:border-gray-700 dark:bg-gray-800"
    role="status"
    aria-live="polite"
  >
    <div class="flex items-start gap-3">
      <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-600 dark:bg-primary-900/20 dark:text-primary-400">
        <Download class="h-5 w-5" />
      </div>
      <div class="min-w-0 flex-1">
        <h2 class="font-semibold text-gray-900 dark:text-gray-100">发现 TrailSnap {{ version }}</h2>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ message }}</p>
        <div v-if="phase === 'downloading'" class="mt-3 h-1.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700">
          <div class="h-full rounded-full bg-primary-500 transition-[width]" :style="{ width: `${progress}%` }" />
        </div>
        <div class="mt-3 flex justify-end gap-2">
          <button
            v-if="phase !== 'installing'"
            type="button"
            class="rounded-lg px-3 py-2 text-sm text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="visible = false"
          >稍后</button>
          <button
            v-if="phase === 'ready'"
            type="button"
            class="rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="installUpdate"
          >立即更新</button>
          <button
            v-else-if="phase === 'error'"
            type="button"
            class="rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="checkForUpdate"
          >重试下载</button>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Download } from 'lucide-vue-next'
import { isTauriApp } from '@/config/server'

type DesktopUpdate = Awaited<ReturnType<typeof import('@tauri-apps/plugin-updater')['check']>>

const visible = ref(false)
const version = ref('')
const phase = ref<'downloading' | 'ready' | 'installing' | 'error'>('downloading')
const message = ref('正在后台下载更新…')
const progress = ref(0)
let update: DesktopUpdate = null
let checkTimer = 0

async function checkForUpdate() {
  if (!isTauriApp()) return
  phase.value = 'downloading'
  progress.value = 0
  message.value = '正在检查并下载更新…'
  try {
    const { check } = await import('@tauri-apps/plugin-updater')
    update = await check({ timeout: 30_000 })
    if (!update) {
      visible.value = false
      return
    }
    version.value = `v${update.version.replace(/^v/i, '')}`
    visible.value = true
    let downloaded = 0
    let total = 0
    await update.download((event) => {
      if (event.event === 'Started') total = event.data.contentLength ?? 0
      if (event.event === 'Progress') downloaded += event.data.chunkLength
      progress.value = total > 0 ? Math.min(100, Math.round(downloaded / total * 100)) : 0
    })
    progress.value = 100
    phase.value = 'ready'
    message.value = '新版已下载并通过签名校验，可以直接安装。'
  } catch (error) {
    visible.value = true
    phase.value = 'error'
    message.value = `更新下载失败：${error instanceof Error ? error.message : String(error)}`
  }
}

async function installUpdate() {
  if (!update) return
  phase.value = 'installing'
  message.value = '正在安装，TrailSnap 将自动重启…'
  try {
    await update.install()
    const { relaunch } = await import('@tauri-apps/plugin-process')
    await relaunch()
  } catch (error) {
    phase.value = 'error'
    message.value = `安装失败：${error instanceof Error ? error.message : String(error)}`
  }
}

onMounted(() => {
  if (isTauriApp()) checkTimer = window.setTimeout(checkForUpdate, 4_000)
})
onBeforeUnmount(() => window.clearTimeout(checkTimer))
</script>
