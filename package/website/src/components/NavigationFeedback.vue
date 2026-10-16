<template>
  <div :class="{ dark: isDarkMode }" :style="themeStyle" class="navigation-feedback">
    <div v-if="navigation.pending" class="navigation-progress" role="progressbar" aria-label="正在打开页面">
      <span />
    </div>
    <div v-if="navigation.pending || navigation.failed" class="navigation-notice ts-surface" :role="navigation.failed ? 'alert' : 'status'" aria-live="polite" aria-atomic="true">
      <template v-if="navigation.pending">
        <LoaderCircle class="navigation-spinner h-4 w-4 shrink-0 text-primary-600 dark:text-primary-400" aria-hidden="true" />
        <p>正在打开{{ navigation.pending.meta.title || '页面' }}…</p>
      </template>
      <template v-else>
        <div class="min-w-0 flex-1">
          <p class="font-semibold">{{ navigation.failed?.meta.title || '页面' }}加载失败</p>
          <p class="ts-muted mt-1 text-sm">{{ navigation.message }}</p>
          <div class="mt-3 flex flex-wrap gap-2">
            <button class="ts-button ts-button-primary ts-button-sm" @click="retry">重试</button>
            <button class="ts-button ts-button-secondary ts-button-sm" @click="reload">重新加载页面</button>
          </div>
        </div>
        <button class="ts-icon-button ts-button-ghost ts-button-sm" aria-label="关闭加载失败提示" @click="navigation.dismiss"><X class="h-4 w-4" /></button>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { LoaderCircle, X } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { injectTheme } from '@/composables/useTheme'
import { useNavigationStore } from '@/stores/navigation'

const navigation = useNavigationStore()
const router = useRouter()
const { isDarkMode, themeStyle } = injectTheme()
async function retry() {
  const target = navigation.failed?.fullPath
  if (target) {
    try { await router.push(target) } catch { /* router.onError restores the recovery notice. */ }
  }
}
function reload() {
  const target = navigation.failed?.fullPath
  if (target) {
    // Also reload when the failed destination is already in the address bar
    // (initial route / browser back), including URLs with a fragment.
    window.history.replaceState(window.history.state, '', router.resolve(target).href)
    window.location.reload()
  }
}
</script>

<style scoped>
.navigation-feedback { position: relative; z-index: 3000; }
.navigation-progress { position: fixed; top: 0; left: 0; right: 0; height: 3px; overflow: hidden; background: rgba(var(--theme-rgb), .15); pointer-events: none; }
.navigation-progress span { display: block; width: 35%; height: 100%; background: var(--theme-primary); animation: navigation-progress 1.2s ease-in-out infinite; }
.navigation-notice { position: fixed; top: calc(var(--ts-safe-area-top) + 16px); left: 50%; transform: translateX(-50%); width: max-content; max-width: min(480px, calc(100vw - 32px)); display: flex; align-items: flex-start; gap: 12px; padding: 16px; }
.navigation-spinner { margin-top: 4px; animation: navigation-spin 1s linear infinite; }
@keyframes navigation-progress { from { transform: translateX(-100%); } to { transform: translateX(385%); } }
@keyframes navigation-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .navigation-progress span { animation: none; width: 100%; opacity: .65; }
  .navigation-spinner { animation: none; }
}
</style>
