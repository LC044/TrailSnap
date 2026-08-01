<template>
  <aside
    v-if="visible"
    class="fixed bottom-4 left-4 right-4 z-[3000] mx-auto max-w-md rounded-xl border border-gray-200 bg-white p-4 shadow-xl dark:border-gray-700 dark:bg-gray-800"
    role="status"
    aria-live="polite"
  >
    <div class="flex items-start gap-3">
      <img src="/logo.svg" alt="" class="h-10 w-10 shrink-0 rounded-lg" />
      <div class="min-w-0 flex-1">
        <p class="font-medium text-gray-900 dark:text-gray-100">{{ title }}</p>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ description }}</p>
        <div v-if="canInstall || updateAvailable" class="mt-3 flex gap-2">
          <button
            type="button"
            class="rounded-lg bg-primary-600 px-3 py-2 text-sm font-medium text-white hover:bg-primary-700 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="primaryAction"
          >
            {{ updateAvailable ? '立即更新' : '安装应用' }}
          </button>
          <button
            type="button"
            class="rounded-lg px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:text-gray-300 dark:hover:bg-gray-700"
            @click="dismiss"
          >
            稍后
          </button>
        </div>
      </div>
      <button
        type="button"
        class="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:hover:bg-gray-700 dark:hover:text-gray-300"
        aria-label="关闭"
        @click="dismiss"
      >
        ×
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { usePwa } from '@/composables/usePwa'

const dismissed = ref(sessionStorage.getItem('trailsnap-pwa-prompt-dismissed') === '1')
const { canInstall, isIos, isInstalled, updateAvailable, installPwa, applyPwaUpdate } = usePwa()

const showIosGuide = computed(() => isIos && !isInstalled.value)
const visible = computed(() => !dismissed.value && (canInstall.value || updateAvailable.value || showIosGuide.value))
const title = computed(() => updateAvailable.value ? '发现新版本' : '安装行影集')
const description = computed(() => {
  if (updateAvailable.value) return '刷新以使用最新功能和修复。'
  if (showIosGuide.value) return '在 Safari 中轻点分享按钮，然后选择“添加到主屏幕”。'
  return '安装到设备主屏幕，像应用一样快速打开。'
})

async function primaryAction() {
  if (updateAvailable.value) {
    applyPwaUpdate()
    return
  }
  await installPwa()
}

function dismiss() {
  dismissed.value = true
  sessionStorage.setItem('trailsnap-pwa-prompt-dismissed', '1')
}
</script>
