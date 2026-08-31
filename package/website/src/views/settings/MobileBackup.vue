<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-xl font-bold text-gray-800 dark:text-white md:text-2xl">手机备份</h1>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">查看增量备份进度，并随时暂停或继续任务。</p>
    </div>

    <section v-if="!supported" class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
      <p class="font-medium text-gray-800 dark:text-white">当前平台暂不支持图库自动备份</p>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">目前支持 Android 原生 APP；网页版无法在后台读取手机系统图库。</p>
    </section>

    <template v-else>
      <section v-if="!settings.enabled" class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
        <p class="font-medium text-gray-800 dark:text-white">备份功能已停用</p>
        <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">请前往“备份设置”启用并选择备份范围。</p>
      </section>

      <section class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="min-w-0">
            <p class="font-medium text-gray-800 dark:text-white">{{ statusText }}</p>
            <p v-if="currentFile" class="mt-1 max-w-[22rem] truncate text-sm text-gray-500 dark:text-gray-400">{{ currentFile }}</p>
            <p v-else-if="lastRunAt" class="mt-1 text-sm text-gray-500 dark:text-gray-400">上次完成：{{ formatTime(lastRunAt) }}</p>
            <p v-if="lastError" class="mt-2 text-sm text-red-500">{{ lastError }}</p>
          </div>
          <div class="flex gap-2">
            <button v-if="running && !pauseRequested" type="button" class="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 hover:border-primary-500 hover:text-primary-600 dark:border-gray-700 dark:text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="backup.pauseBackup">暂停</button>
            <button v-else-if="running && pauseRequested" type="button" class="rounded-lg bg-primary-600 px-4 py-2 text-sm text-white shadow-primary-500/20 hover:bg-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="backup.resumeBackup">继续</button>
            <button v-else type="button" class="rounded-lg bg-primary-600 px-4 py-2 text-sm text-white shadow-primary-500/20 hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" :disabled="!settings.enabled" @click="runNow">
              {{ pauseReason === 'network' ? '重试' : '立即备份' }}
            </button>
          </div>
        </div>

        <div v-if="running || totalItems > 0" class="mt-5">
          <div class="mb-2 flex items-center justify-between text-sm">
            <span class="text-gray-600 dark:text-gray-300">总进度 {{ processedItems }} / {{ totalItems }}</span>
            <span class="font-medium text-primary-600">{{ overallProgress }}%</span>
          </div>
          <div class="h-2.5 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
            <div class="h-full rounded-full bg-primary-500 transition-[width] duration-300" :style="{ width: `${overallProgress}%` }" />
          </div>
          <div v-if="currentFile" class="mt-4 rounded-lg bg-gray-50 p-3 dark:bg-gray-900">
            <div class="mb-2 flex items-center justify-between gap-3 text-xs">
              <span class="min-w-0 truncate text-gray-600 dark:text-gray-300">{{ currentFile }}</span>
              <span class="shrink-0 text-gray-500 dark:text-gray-400">{{ currentFileProgress }}%</span>
            </div>
            <div class="h-1.5 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
              <div class="h-full rounded-full bg-primary-500 transition-[width] duration-200" :style="{ width: `${currentFileProgress}%` }" />
            </div>
          </div>
        </div>

        <div v-if="running || backedUp || skipped" class="mt-4 grid grid-cols-3 gap-3 text-center">
          <div class="rounded-lg bg-gray-50 p-3 dark:bg-gray-900"><p class="text-xl font-semibold text-primary-600">{{ backedUp }}</p><p class="text-xs text-gray-500 dark:text-gray-400">本次已上传</p></div>
          <div class="rounded-lg bg-gray-50 p-3 dark:bg-gray-900"><p class="text-xl font-semibold text-gray-700 dark:text-gray-200">{{ skipped }}</p><p class="text-xs text-gray-500 dark:text-gray-400">服务端已存在</p></div>
          <div class="rounded-lg bg-gray-50 p-3 dark:bg-gray-900"><p class="truncate text-lg font-semibold text-gray-700 dark:text-gray-200">{{ speedText }}</p><p class="text-xs text-gray-500 dark:text-gray-400">当前速度</p></div>
        </div>
        <p v-if="uploadedBytes > 0" class="mt-3 text-xs text-gray-500 dark:text-gray-400">已上传流量 {{ formatSize(uploadedBytes) }}，本轮媒体共 {{ formatSize(totalBytes) }}</p>
      </section>

      <section v-if="queueItems.length" class="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
        <div class="border-b border-gray-100 px-5 py-4 dark:border-gray-700">
          <h2 class="font-medium text-gray-800 dark:text-white">待备份文件</h2>
          <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">仅显示当前批次，最多 40 项，不加载缩略图。</p>
        </div>
        <ul class="max-h-96 divide-y divide-gray-100 overflow-y-auto dark:divide-gray-700">
          <li v-for="item in queueItems" :key="item.backupKey" class="flex items-center gap-3 px-5 py-3">
            <span class="h-2 w-2 shrink-0 rounded-full" :class="queueStatusClass(item.status)" />
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm text-gray-700 dark:text-gray-200">{{ item.name }}</p>
              <p class="truncate text-xs text-gray-500 dark:text-gray-400">{{ item.relativePath || '图库根目录' }}</p>
            </div>
            <div class="shrink-0 text-right">
              <p class="text-xs text-gray-500 dark:text-gray-400">{{ queueStatusText[item.status] }}</p>
              <p class="mt-0.5 text-xs text-gray-400 dark:text-gray-500">{{ formatSize(item.size) }}</p>
            </div>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useGalleryBackup, type BackupQueueStatus } from '@/composables/useGalleryBackup'

const backup = useGalleryBackup()
const {
  supported, settings, running, status, pauseReason, pauseRequested, currentFile, currentFileProgress,
  backedUp, skipped, totalItems, processedItems, totalBytes, uploadedBytes, speedBytesPerSecond,
  overallProgress, lastError, lastRunAt, queueItems,
} = backup

onMounted(() => backup.initialize())

const runNow = async () => {
  if (!settings.value.enabled) return
  await backup.runBackup({ manual: true })
  if (status.value === 'idle') ElMessage.success(`备份完成，新增 ${backedUp.value} 项`)
}
const statusText = computed(() => ({
  idle: '图库已同步', scanning: '正在扫描新增照片…', uploading: '正在上传…',
  pausing: '正在暂停，等待当前分片完成…', paused: pauseReason.value === 'network' ? '等待 Wi-Fi / 可用网络' : '备份已暂停',
  error: '备份发生错误', unsupported: '当前平台不支持',
}[status.value]))
const formatTime = (value: number) => new Date(value).toLocaleString()
const formatSize = (bytes: number) => {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  return `${(bytes / 1024 ** index).toFixed(index > 1 ? 1 : 0)} ${units[index]}`
}
const speedText = computed(() => speedBytesPerSecond.value > 0 ? `${formatSize(speedBytesPerSecond.value)}/s` : '—')
const queueStatusText: Record<BackupQueueStatus, string> = { pending: '等待中', uploading: '上传中', uploaded: '已上传', skipped: '已存在', error: '失败' }
const queueStatusClass = (value: BackupQueueStatus) => ({
  pending: 'bg-gray-300 dark:bg-gray-600', uploading: 'bg-primary-500 animate-pulse', uploaded: 'bg-green-500', skipped: 'bg-gray-400', error: 'bg-red-500',
}[value])
</script>
