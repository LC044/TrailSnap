<template>
  <ResponsiveDialog v-model="visible" :title="recovering ? '上次复制尚未完成' : '找回旧版本照片'" :close-on-backdrop="false">
    <div class="space-y-4">
      <template v-if="recovering">
        <p>上次导入或备份被中断，原图库仍保留。可以继续验证已保存的副本，或清理本次临时文件后重试。</p>
        <p class="ts-muted break-all text-sm">副本位置：{{ store.discovery?.operation?.target }}</p>
      </template>
      <p v-else>发现旧版本的图库，可以复制到新版继续使用。原照片和数据都会保留。</p>
      <p v-if="!recovering" class="ts-muted text-sm">暂不导入也可以，以后可在“设置 → 照片与数据位置”中找回。导入会打开另一个图库，两边的照片、票夹和设置不会自动合并。</p>
      <p v-if="store.discovery?.currentPhotos" class="ts-muted">当前图库已有 {{ store.discovery.currentPhotos }} 张照片。导入会打开另一个图库，两边的照片不会自动合并。</p>
      <ul v-if="!recovering" class="ts-muted space-y-2 break-all text-sm">
        <li v-for="candidate in store.discovery?.candidates" :key="candidate.path">{{ candidate.path }}<br>{{ candidate.photos === null ? candidate.error : `${candidate.photos} 张照片` }}</li>
        <li v-for="notice in store.discovery?.notices" :key="notice">{{ notice }}</li>
      </ul>
    </div>
    <template #footer>
      <div class="flex flex-wrap justify-end gap-3">
        <button class="ts-button ts-button-secondary" @click="visible = false">稍后提醒</button>
        <button v-if="!recovering" class="ts-button ts-button-secondary" @click="dismiss">暂不导入，使用新图库</button>
        <button class="ts-button ts-button-primary" @click="openImport">{{ recovering ? '继续处理' : '检查旧照片' }}</button>
      </div>
      <p v-if="dismissError" role="alert" class="mt-3 text-sm text-[var(--ts-color-danger)]">{{ dismissError }}</p>
    </template>
  </ResponsiveDialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import { isTauriApp } from '@/config/server'
import { useDesktopDataDirectoryStore } from '@/stores/desktopDataDirectory'
import { dismissLegacyDiscovery, subscribeImportProgress } from '@/api/desktopDataDirectory'

const store = useDesktopDataDirectoryStore()
const router = useRouter()
const visible = ref(false)
const recovering = computed(() => !!store.discovery?.operation && store.discovery.operation.phase !== 'completed')
const dismissError = ref('')
let disposed = false
let unlisten: (() => void) | undefined
async function dismiss() {
  try { await dismissLegacyDiscovery(); visible.value = false }
  catch (cause) { dismissError.value = String(cause) }
}
async function openImport() {
  visible.value = false
  await router.push({ path: '/settings', hash: '#data-directory' })
}
onMounted(async () => {
  if (!isTauriApp()) return
  try {
    const stop = await subscribeImportProgress(value => { store.progress = value })
    if (disposed) { stop(); return }
    unlisten = stop
  } catch { /* Discovery remains available if native event setup fails. */ }
  await store.loadDiscovery()
  if (disposed) return
  const discovery = store.discovery
  visible.value = recovering.value || (!!discovery && !discovery.completed && !discovery.dismissed
    && (discovery.candidates.length > 0 || discovery.notices.length > 0))
})
onBeforeUnmount(() => { disposed = true; unlisten?.() })
</script>
