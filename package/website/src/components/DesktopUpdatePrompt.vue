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
        <h2 class="font-semibold text-gray-900 dark:text-gray-100">{{ phase === 'error' ? '更新未完成' : `发现 TrailSnap ${version}` }}</h2>
        <p class="mt-1 break-words text-sm text-gray-500 dark:text-gray-400">{{ message }}</p>
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
            @click="needsRestart ? restartAfterError() : store.check(true)"
          >{{ needsRestart ? '重启当前实例' : '重试更新' }}</button>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { Download } from 'lucide-vue-next'
import { isTauriApp } from '@/config/server'
import { restartDesktop } from '@/api/desktopDataDirectory'

import { useDesktopUpdatesStore } from '@/stores/desktopUpdates'
const store = useDesktopUpdatesStore()
const { visible, version, phase, message, progress, needsRestart } = storeToRefs(store)
let checkTimer = 0
const checkForUpdate = () => store.check()
const installUpdate = () => store.install()
const restartAfterError = () => restartDesktop().catch(error => { store.message = `重启失败：${String(error)}` })

onMounted(() => {
  if (isTauriApp()) checkTimer = window.setTimeout(checkForUpdate, 4_000)
})
onBeforeUnmount(() => { window.clearTimeout(checkTimer); store.dispose() })
</script>
