<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-xl font-bold text-gray-800 dark:text-white md:text-2xl">手机自动备份</h1>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">增量扫描系统图库，只上传新增或修改过的照片。</p>
    </div>

    <section v-if="!supported" class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
      <p class="font-medium text-gray-800 dark:text-white">当前平台暂不支持图库自动备份</p>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">目前支持 Android 原生 APP；网页版无法在后台读取手机系统图库。</p>
    </section>

    <template v-else>
      <section class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
        <div class="flex items-center justify-between gap-4">
          <div>
            <p class="font-medium text-gray-800 dark:text-white">自动增量备份</p>
            <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">启动 APP、回到前台时自动检查新增照片。</p>
          </div>
          <el-switch v-model="form.enabled" @change="persist" />
        </div>

        <div class="mt-5 flex items-center justify-between gap-4 border-t border-gray-100 pt-5 dark:border-gray-700">
          <div>
            <p class="text-sm font-medium text-gray-700 dark:text-gray-200">仅在 Wi-Fi / 不计费网络上传</p>
            <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">避免自动备份消耗移动流量。</p>
          </div>
          <el-switch v-model="form.wifiOnly" @change="persist" />
        </div>

        <div class="mt-5 flex items-center justify-between gap-4 border-t border-gray-100 pt-5 dark:border-gray-700">
          <div>
            <p class="text-sm font-medium text-gray-700 dark:text-gray-200">同时备份视频</p>
            <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">视频文件较大，默认关闭。</p>
          </div>
          <el-switch v-model="form.includeVideos" @change="persist" />
        </div>

        <label class="mt-5 block border-t border-gray-100 pt-5 text-sm text-gray-700 dark:border-gray-700 dark:text-gray-200">
          <span class="mb-2 block font-medium">服务器保存目录</span>
          <el-input v-model="form.folder" placeholder="手机备份" maxlength="120" @change="persist" />
        </label>
      </section>

      <section class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p class="font-medium text-gray-800 dark:text-white">{{ statusText }}</p>
            <p v-if="currentFile" class="mt-1 max-w-[18rem] truncate text-sm text-gray-500 dark:text-gray-400">{{ currentFile }}</p>
            <p v-else-if="lastRunAt" class="mt-1 text-sm text-gray-500 dark:text-gray-400">上次完成：{{ formatTime(lastRunAt) }}</p>
            <p v-if="lastError" class="mt-2 text-sm text-red-500">{{ lastError }}</p>
          </div>
          <button
            type="button"
            class="rounded-lg bg-primary-600 px-4 py-2 text-sm text-white shadow-primary-500/20 hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
            :disabled="running"
            @click="runNow"
          >
            {{ running ? '备份中…' : '立即备份' }}
          </button>
        </div>
        <div v-if="running || backedUp || skipped" class="mt-4 grid grid-cols-2 gap-3 text-center">
          <div class="rounded-lg bg-gray-50 p-3 dark:bg-gray-900">
            <p class="text-xl font-semibold text-primary-600">{{ backedUp }}</p>
            <p class="text-xs text-gray-500 dark:text-gray-400">本次已上传</p>
          </div>
          <div class="rounded-lg bg-gray-50 p-3 dark:bg-gray-900">
            <p class="text-xl font-semibold text-gray-700 dark:text-gray-200">{{ skipped }}</p>
            <p class="text-xs text-gray-500 dark:text-gray-400">服务端已存在</p>
          </div>
        </div>
      </section>

      <button
        type="button"
        class="text-sm text-gray-500 hover:text-primary-600 dark:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
        :disabled="running"
        @click="rescan"
      >
        重新扫描全部图库（已备份照片仍会由服务端去重）
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useGalleryBackup, type GalleryBackupSettings } from '@/composables/useGalleryBackup'

const backup = useGalleryBackup()
const { supported, settings, running, status, currentFile, backedUp, skipped, lastError, lastRunAt } = backup
const form = reactive<GalleryBackupSettings>({ ...settings.value })

onMounted(async () => {
  await backup.initialize()
  Object.assign(form, settings.value)
})
watch(settings, value => Object.assign(form, value))

const persist = async () => {
  await backup.saveSettings({ ...form })
  if (form.enabled) void backup.runBackup()
}
const runNow = async () => {
  await backup.saveSettings({ ...form })
  await backup.runBackup({ manual: true })
  if (status.value === 'idle') ElMessage.success(`备份完成，新增 ${backedUp.value} 项`)
}
const rescan = async () => {
  try {
    await ElMessageBox.confirm('重新扫描不会重复上传服务端已有照片，但大型图库可能需要较长时间。', '重新扫描图库', {
      confirmButtonText: '重新扫描', cancelButtonText: '取消', type: 'warning',
    })
    await backup.resetCursor()
    await backup.runBackup({ manual: true })
  } catch { /* cancelled */ }
}
const statusText = computed(() => ({
  idle: '图库已同步', scanning: '正在扫描新增照片…', uploading: '正在上传…',
  paused: '等待 Wi-Fi / 可用网络', error: '备份已暂停', unsupported: '当前平台不支持',
}[status.value]))
const formatTime = (value: number) => new Date(value).toLocaleString()
</script>
