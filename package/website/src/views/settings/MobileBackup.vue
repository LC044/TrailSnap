<template>
  <div class="mx-auto max-w-3xl">
    <Transition :name="innerTransition" mode="out-in">
      <div v-if="screen === 'overview'" key="overview" class="space-y-5">
        <div v-if="hosted" class="-mx-4 -mt-4 flex h-12 items-center border-b border-gray-200 bg-white/95 px-2 backdrop-blur dark:border-gray-800 dark:bg-gray-900/95 md:hidden">
          <button type="button" class="flex h-10 items-center gap-1 rounded-lg px-2 text-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-primary-400" aria-label="返回设置" @click="emit('requestSettingsBack')">
            <ArrowLeft class="h-5 w-5" /><span class="text-sm">设置</span>
          </button>
          <div class="pointer-events-none absolute left-1/2 -translate-x-1/2 text-[15px] font-semibold">手机备份</div>
        </div>
        <header class="flex items-start justify-between gap-4 px-1">
          <div>
            <h1 class="text-2xl font-bold tracking-tight text-gray-900 dark:text-white">手机备份</h1>
            <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">安全地将手机照片同步到你的服务器</p>
          </div>
          <button
            v-if="supported"
            type="button"
            class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white text-gray-600 shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:bg-gray-800 dark:text-gray-300"
            aria-label="打开备份设置"
            @click="openSettings"
          >
            <Settings class="h-5 w-5" />
          </button>
        </header>

        <section v-if="!supported" class="rounded-2xl bg-white p-5 shadow-sm dark:bg-gray-800">
          <div class="flex items-start gap-3">
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400"><Smartphone class="h-5 w-5" /></span>
            <div><p class="font-semibold text-gray-900 dark:text-white">当前设备不支持自动备份</p><p class="mt-1 text-sm leading-6 text-gray-500 dark:text-gray-400">请使用 Android 原生 App。网页版无法在后台读取系统图库。</p></div>
          </div>
        </section>

        <template v-else>
          <button
            v-if="!settings.enabled"
            type="button"
            class="flex w-full items-center gap-3 rounded-2xl bg-white p-4 text-left shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:bg-gray-800"
            @click="openSettings"
          >
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400"><CloudOff class="h-5 w-5" /></span>
            <span class="min-w-0 flex-1"><span class="block font-semibold">自动备份已关闭</span><span class="mt-0.5 block text-sm text-gray-500 dark:text-gray-400">轻触配置备份范围和网络条件</span></span>
            <ChevronRight class="h-5 w-5 text-gray-300 dark:text-gray-600" />
          </button>

          <section class="overflow-hidden rounded-2xl bg-white shadow-sm dark:bg-gray-800" aria-label="备份状态">
            <div class="p-5">
              <div class="flex items-center gap-3">
                <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full" :class="statusIconClass"><component :is="statusIcon" class="h-5 w-5" :class="['scanning', 'pausing'].includes(status) ? 'animate-spin' : ''" /></span>
                <div class="min-w-0 flex-1">
                  <p class="font-semibold text-gray-900 dark:text-white">{{ statusText }}</p>
                  <p v-if="currentFile" class="mt-0.5 truncate text-sm text-gray-500 dark:text-gray-400">{{ currentFile }}</p>
                  <p v-else-if="lastRunAt" class="mt-0.5 text-sm text-gray-500 dark:text-gray-400">上次完成 {{ formatRelativeTime(lastRunAt) }}</p>
                  <p v-else class="mt-0.5 text-sm text-gray-500 dark:text-gray-400">尚未执行备份</p>
                </div>
                <button
                  v-if="running && !pauseRequested"
                  type="button"
                  class="rounded-full bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:bg-gray-700 dark:text-gray-200"
                  @click="backup.pauseBackup"
                >暂停</button>
                <button
                  v-else-if="running && pauseRequested"
                  type="button"
                  class="rounded-full bg-primary-600 px-4 py-2 text-sm font-medium text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                  @click="backup.resumeBackup"
                >继续</button>
                <button
                  v-else
                  type="button"
                  class="rounded-full bg-primary-600 px-4 py-2 text-sm font-medium text-white shadow-primary-500/20 disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                  :disabled="!settings.enabled"
                  @click="runNow"
                >{{ pauseReason === 'network' ? '重试' : '立即备份' }}</button>
              </div>

              <div v-if="running || totalItems > 0" class="mt-5">
                <div class="mb-2 flex items-baseline justify-between">
                  <span class="text-sm text-gray-500 dark:text-gray-400">{{ processedItems }} / {{ totalItems }} 项</span>
                  <span class="text-lg font-semibold tabular-nums text-primary-600 dark:text-primary-400">{{ overallProgress }}%</span>
                </div>
                <div class="h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700"><div class="h-full rounded-full bg-primary-500 transition-[width] duration-300" :style="{ width: `${overallProgress}%` }" /></div>
              </div>

              <div v-if="currentFile" class="mt-4 rounded-xl bg-gray-50 px-4 py-3 dark:bg-gray-900">
                <div class="flex items-center gap-2 text-xs"><ImageIcon class="h-4 w-4 shrink-0 text-gray-400" /><span class="min-w-0 flex-1 truncate text-gray-600 dark:text-gray-300">{{ currentFile }}</span><span class="tabular-nums text-gray-500 dark:text-gray-400">{{ currentFileProgress }}%</span></div>
                <div class="mt-2 h-1 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700"><div class="h-full rounded-full bg-primary-500 transition-[width] duration-200" :style="{ width: `${currentFileProgress}%` }" /></div>
              </div>

              <p v-if="lastError" class="mt-4 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/30 dark:text-red-400">{{ lastError }}</p>
            </div>

            <div v-if="running || backedUp || skipped" class="grid grid-cols-3 border-t border-gray-100 py-4 dark:border-gray-700">
              <div class="text-center"><p class="text-lg font-semibold tabular-nums text-gray-900 dark:text-white">{{ backedUp }}</p><p class="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">本次上传</p></div>
              <div class="border-x border-gray-100 text-center dark:border-gray-700"><p class="text-lg font-semibold tabular-nums text-gray-900 dark:text-white">{{ skipped }}</p><p class="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">已存在</p></div>
              <div class="text-center"><p class="truncate px-1 text-lg font-semibold tabular-nums text-gray-900 dark:text-white">{{ speedText }}</p><p class="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">上传速度</p></div>
            </div>
          </section>

          <p v-if="uploadedBytes > 0" class="px-2 text-center text-xs text-gray-500 dark:text-gray-400">本轮已传 {{ formatSize(uploadedBytes) }} · 共 {{ formatSize(totalBytes) }}</p>

          <section v-if="queueItems.length" class="overflow-hidden rounded-2xl bg-white shadow-sm dark:bg-gray-800">
            <div class="flex items-center justify-between border-b border-gray-100 px-4 py-3.5 dark:border-gray-700"><div><h2 class="font-semibold">当前批次</h2><p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">最多显示 40 项</p></div><span class="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-500 dark:bg-gray-700 dark:text-gray-400">{{ queueItems.length }} 项</span></div>
            <ul class="max-h-[22rem] divide-y divide-gray-100 overflow-y-auto dark:divide-gray-700">
              <li v-for="item in queueItems" :key="item.backupKey" class="flex min-h-16 items-center gap-3 px-4 py-2.5">
                <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gray-100 dark:bg-gray-700"><ImageIcon class="h-[18px] w-[18px] text-gray-500 dark:text-gray-400" /></span>
                <div class="min-w-0 flex-1"><p class="truncate text-sm font-medium text-gray-800 dark:text-gray-100">{{ item.name }}</p><p class="mt-0.5 truncate text-xs text-gray-500 dark:text-gray-400">{{ item.relativePath || '图库根目录' }} · {{ formatSize(item.size) }}</p></div>
                <div class="flex shrink-0 items-center gap-1.5 text-xs" :class="queueStatusColor(item.status)"><span class="h-1.5 w-1.5 rounded-full" :class="queueStatusDot(item.status)" />{{ queueStatusText[item.status] }}</div>
              </li>
            </ul>
          </section>

          <section class="overflow-hidden rounded-2xl bg-white shadow-sm dark:bg-gray-800">
            <button type="button" class="flex min-h-14 w-full items-center gap-3 px-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500" @click="openSettings">
              <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400"><Settings class="h-[18px] w-[18px]" /></span>
              <span class="min-w-0 flex-1"><span class="block text-[15px] font-medium">备份设置</span><span class="block truncate text-xs text-gray-500 dark:text-gray-400">范围、网络、视频与保存目录</span></span>
              <ChevronRight class="h-4 w-4 text-gray-300 dark:text-gray-600" />
            </button>
          </section>
        </template>
      </div>

      <div v-else key="settings">
        <header class="mb-5 flex h-11 items-center border-b border-gray-200 dark:border-gray-800">
          <button type="button" class="flex h-9 items-center gap-1 rounded-lg pr-3 text-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-primary-400" aria-label="返回手机备份" @click="closeSettings"><ArrowLeft class="h-5 w-5" /><span class="text-sm">手机备份</span></button>
          <div class="absolute left-1/2 -translate-x-1/2 text-[15px] font-semibold">备份设置</div>
        </header>
        <MobileBackupSettings embedded @saved="closeSettings" />
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Check, ChevronRight, Cloud, CloudOff, Image as ImageIcon, LoaderCircle, Settings, Smartphone, TriangleAlert } from 'lucide-vue-next'
import { useGalleryBackup, type BackupQueueStatus } from '@/composables/useGalleryBackup'
import MobileBackupSettings from './MobileBackupSettings.vue'

withDefaults(defineProps<{ hosted?: boolean }>(), { hosted: false })
const emit = defineEmits<{ requestSettingsBack: [] }>()
const route = useRoute()
const router = useRouter()
const backup = useGalleryBackup()
const { supported, settings, running, status, pauseReason, pauseRequested, currentFile, currentFileProgress, backedUp, skipped, totalItems, processedItems, totalBytes, uploadedBytes, speedBytesPerSecond, overallProgress, lastError, lastRunAt, queueItems } = backup
const screen = ref<'overview' | 'settings'>(route.hash === '#mobile-backup-settings' ? 'settings' : 'overview')
const innerTransition = ref('backup-forward')
let openedSettingsHere = false
onMounted(() => backup.initialize())
const openSettings = () => {
  innerTransition.value = 'backup-forward'
  openedSettingsHere = true
  screen.value = 'settings'
  void router.push({ path: '/settings', hash: '#mobile-backup-settings' })
}
const closeSettings = () => {
  innerTransition.value = 'backup-back'
  screen.value = 'overview'
  if (openedSettingsHere) {
    openedSettingsHere = false
    router.back()
  } else {
    void router.replace({ path: '/settings', hash: '#mobile-backup' })
  }
}
watch(() => route.hash, hash => {
  const next = hash === '#mobile-backup-settings' ? 'settings' : 'overview'
  if (next !== screen.value) {
    innerTransition.value = next === 'settings' ? 'backup-forward' : 'backup-back'
    screen.value = next
  }
})
const runNow = async () => { if (!settings.value.enabled) return; await backup.runBackup({ manual: true }); if (status.value === 'idle') ElMessage.success(`备份完成，新增 ${backedUp.value} 项`) }
const statusText = computed(() => ({ idle: '照片已备份', scanning: '正在查找新照片', uploading: '正在备份', pausing: '正在暂停', paused: pauseReason.value === 'network' ? '等待可用网络' : '备份已暂停', error: '备份未完成', unsupported: '当前平台不支持' }[status.value]))
const statusIcon = computed<Component>(() => ({ idle: Check, scanning: LoaderCircle, uploading: Cloud, pausing: LoaderCircle, paused: CloudOff, error: TriangleAlert, unsupported: CloudOff }[status.value]))
const statusIconClass = computed(() => status.value === 'error' ? 'bg-red-50 text-red-600 dark:bg-red-950/30 dark:text-red-400' : status.value === 'idle' ? 'bg-green-50 text-green-600 dark:bg-green-950/30 dark:text-green-400' : 'bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400')
const formatRelativeTime = (value: number) => { const seconds = Math.max(1, Math.round((Date.now() - value) / 1000)); if (seconds < 60) return '刚刚'; if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`; if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`; return new Date(value).toLocaleDateString() }
const formatSize = (bytes: number) => { if (!bytes) return '0 B'; const units = ['B', 'KB', 'MB', 'GB']; const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024))); return `${(bytes / 1024 ** index).toFixed(index > 1 ? 1 : 0)} ${units[index]}` }
const speedText = computed(() => speedBytesPerSecond.value > 0 ? `${formatSize(speedBytesPerSecond.value)}/s` : '—')
const queueStatusText: Record<BackupQueueStatus, string> = { pending: '等待', uploading: '上传中', uploaded: '完成', skipped: '已存在', error: '失败' }
const queueStatusDot = (value: BackupQueueStatus) => ({ pending: 'bg-gray-300 dark:bg-gray-600', uploading: 'bg-primary-500 animate-pulse', uploaded: 'bg-green-500', skipped: 'bg-gray-400', error: 'bg-red-500' }[value])
const queueStatusColor = (value: BackupQueueStatus) => value === 'error' ? 'text-red-500' : value === 'uploading' ? 'text-primary-600 dark:text-primary-400' : 'text-gray-500 dark:text-gray-400'
</script>

<style scoped>
.backup-forward-enter-active, .backup-back-enter-active { transition: opacity .2s ease, transform .25s cubic-bezier(.22, 1, .36, 1); }
.backup-forward-enter-from { opacity: 0; transform: translateX(18px); }
.backup-back-enter-from { opacity: 0; transform: translateX(-18px); }
.animate-spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
