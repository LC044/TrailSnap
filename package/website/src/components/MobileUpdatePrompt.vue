<template>
  <div
    v-if="visible"
    class="fixed inset-0 z-[10000] flex items-end justify-center bg-black/40 p-4 sm:items-center"
    role="dialog"
    aria-modal="true"
    aria-labelledby="app-update-title"
  >
    <section
      class="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-5 shadow-xl dark:border-gray-700 dark:bg-gray-800"
    >
      <header class="flex items-start gap-3">
        <div
          class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-600 dark:bg-primary-900/20 dark:text-primary-400"
        >
          <Download class="h-5 w-5" />
        </div>
        <div class="min-w-0 flex-1">
          <h2 id="app-update-title" class="font-semibold text-gray-900 dark:text-gray-100">
            {{ title }}
          </h2>
          <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ subtitle }}</p>
        </div>
      </header>

      <div
        v-if="updateInfo && phase === 'available'"
        class="mt-4 max-h-40 overflow-y-auto rounded-xl bg-gray-50 p-3 text-sm leading-6 text-gray-600 dark:bg-gray-900 dark:text-gray-300"
        v-html="sanitizedUpdateInfo"
      />

      <div v-if="phase === 'downloading'" class="mt-4 space-y-2">
        <div class="h-1.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700">
          <div
            class="h-full rounded-full bg-primary-500 transition-[width]"
            :style="{ width: `${percent}%` }"
          />
        </div>
        <p class="text-xs text-gray-500 dark:text-gray-400">
          {{ percent }}% · {{ formatBytes(downloadedBytes) }}
          <span v-if="totalBytes > 0"> / {{ formatBytes(totalBytes) }}</span>
        </p>
      </div>

      <p
        v-if="errorMessage"
        role="alert"
        class="mt-4 rounded-xl bg-red-50 p-3 text-sm leading-6 text-red-700 dark:bg-red-950/30 dark:text-red-300"
      >
        {{ errorMessage }}
      </p>

      <footer class="mt-5 flex flex-wrap justify-end gap-2">
        <button
          v-if="phase === 'available'"
          type="button"
          class="rounded-lg px-3 py-2 text-sm text-gray-500 hover:bg-gray-100 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:text-gray-400 dark:hover:bg-gray-700"
          @click="skipVersion"
        >
          跳过此版本
        </button>
        <button
          v-if="phase !== 'installing'"
          type="button"
          class="rounded-lg px-3 py-2 text-sm text-gray-500 hover:bg-gray-100 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:text-gray-400 dark:hover:bg-gray-700"
          @click="onSecondary"
        >
          {{ phase === 'downloading' ? '取消下载' : '稍后' }}
        </button>
        <button
          v-if="phase === 'available' || phase === 'error'"
          type="button"
          class="rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          @click="downloadUpdate"
        >
          {{ phase === 'error' ? '重试' : '立即更新' }}
        </button>
        <button
          v-else-if="phase === 'downloaded'"
          type="button"
          class="rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          @click="installUpdate"
        >
          安装
        </button>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { Download } from 'lucide-vue-next'
import DOMPurify from 'dompurify'
import { useAppUpdate } from '@/composables/useAppUpdate'

const {
  supported,
  phase,
  visible,
  latestVersion,
  updateInfo,
  totalBytes,
  downloadedBytes,
  percent,
  errorMessage,
  checkForUpdate,
  downloadUpdate,
  installUpdate,
  cancelDownload,
  skipVersion,
  dismiss,
} = useAppUpdate()

let checkTimer = 0

const title = computed(() => {
  if (phase.value === 'downloading') return '正在下载安装包'
  if (phase.value === 'downloaded') return '安装包已就绪'
  if (phase.value === 'installing') return '正在唤起安装'
  if (phase.value === 'error') return '更新失败'
  return `发现新版本 v${latestVersion.value}`
})

const subtitle = computed(() => {
  switch (phase.value) {
    case 'downloading':
      return '下载完成后会自动打开系统安装界面。'
    case 'downloaded':
      return '点击安装，并在系统界面确认覆盖安装。'
    case 'installing':
      return '请在系统安装界面继续操作。'
    case 'error':
      return '也可以前往设置 → 关于，稍后重试。'
    default:
      return '将下载官方安装包并覆盖安装，服务器地址和登录状态会保留。'
  }
})

// 更新日志来自服务端 version.json，含 <br> 等标签，渲染前先净化。
const sanitizedUpdateInfo = computed(() =>
  DOMPurify.sanitize(updateInfo.value, { ALLOWED_TAGS: ['br', 'b', 'strong', 'em', 'p', 'ul', 'li'] }),
)

function formatBytes(value: number): string {
  if (value <= 0) return '0 MB'
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function onSecondary() {
  if (phase.value === 'downloading') void cancelDownload()
  else dismiss()
}

onMounted(() => {
  // 冷启动稍作延迟，避免和相册备份、SSE 建连抢占启动阶段的带宽。
  if (supported) checkTimer = window.setTimeout(() => void checkForUpdate(true), 6_000)
})
onBeforeUnmount(() => window.clearTimeout(checkTimer))
</script>
