<template>
  <ResponsiveDialog :model-value="modelValue" title="填充本月" description="为还没选的日子挑选候选，确认后才会保存。" max-width="50rem" mobile-mode="fullscreen" mobile-back :close-on-backdrop="false" @update:model-value="close">
    <p v-if="error" role="alert" class="mb-3 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
    <p v-if="loading" role="status" class="py-12 text-center text-gray-500 dark:text-gray-400">正在整理候选…</p>
    <template v-else>
      <div class="mb-4 flex items-center justify-between gap-3">
        <p class="text-sm text-gray-500 dark:text-gray-400">将填充 {{ checked.length }} 天，保留已有 {{ preserved }} 天</p>
        <button class="df-button" type="button" :disabled="saving" @click="refresh">刷新候选</button>
      </div>
      <p v-if="!items.length" class="py-10 text-center text-gray-500 dark:text-gray-400">本月暂无待填充日期。</p>
      <div class="space-y-3">
        <div v-for="item in items" :key="item.day" class="flex items-center gap-3 rounded-xl border border-gray-200 p-3 dark:border-gray-700">
          <input v-model="item.checked" type="checkbox" :aria-label="`填充 ${item.day}`" class="h-5 w-5 accent-[var(--theme-primary)]" :disabled="saving" />
          <img :src="thumbnailUrl(item.photo_id)" :alt="`${item.day} 候选`" class="h-16 w-16 rounded-lg object-cover" loading="lazy" />
          <div class="min-w-0 flex-1">
            <p class="text-sm font-medium">{{ item.day }} <span class="text-xs text-gray-500 dark:text-gray-400">{{ item.mode === 'motion' ? '动态一秒' : '照片一秒' }}</span></p>
            <p class="truncate text-xs text-gray-500 dark:text-gray-400">{{ item.caption || '还没有写一句话' }}</p>
            <p v-if="item.error" class="text-xs text-red-600 dark:text-red-400">{{ item.error }}</p>
          </div>
          <button class="df-button" type="button" :disabled="saving" @click="edit(item)">调整</button>
        </div>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <button class="df-button" type="button" :disabled="saving" @click="close(false)">取消</button>
        <button class="df-primary" type="button" :disabled="saving || loading || !checked.length" @click="save">{{ saving ? '保存中…' : `保存所选 ${checked.length} 天` }}</button>
      </div>
    </template>
  </ResponsiveDialog>
  <FrameEditor v-if="editing" v-model="editorVisible" :day="editing.day" :initial-selection="editing" draft-mode @selected="replace" />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import FrameEditor from './FrameEditor.vue'
import { dailyFrameApi, dailyFrameError } from '@/api/dailyFrame'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { monthRange } from '@/utils/dailyFrame'
import type { DailyFrameSuggestion } from '@/types/dailyFrame'

const props = defineProps<{ modelValue: boolean; month: string }>()
const emit = defineEmits<{ 'update:modelValue': [boolean]; saved: [] }>()
const items = ref<Array<DailyFrameSuggestion & { checked: boolean; error?: string }>>([])
const checked = computed(() => items.value.filter(item => item.checked))
const preserved = ref(0), loading = ref(false), saving = ref(false), error = ref('')
const editing = ref<DailyFrameSuggestion | null>(null), editorVisible = ref(false)
let requestId = 0

async function load() {
  const request = ++requestId; loading.value = true; error.value = ''
  try {
    const result = await dailyFrameApi.suggestions(...monthRange(props.month))
    if (request !== requestId) return
    items.value = result.items.map(item => ({ ...item, checked: true })); preserved.value = result.preserved
  } catch (err) { if (request === requestId) error.value = dailyFrameError(err) }
  finally { if (request === requestId) loading.value = false }
}
async function refresh() {
  try { await ElMessageBox.confirm('刷新会重新挑选候选，替换本次尚未保存的调整。', '刷新候选') } catch { return }
  await load()
}
function edit(item: DailyFrameSuggestion) { editing.value = item; editorVisible.value = true }
function replace(item: DailyFrameSuggestion) {
  const index = items.value.findIndex(row => row.day === item.day)
  if (index >= 0) items.value[index] = { ...item, checked: items.value[index].checked }
}
function close(value: boolean) { if (!value && !saving.value && !editorVisible.value) { requestId++; emit('update:modelValue', false) } }
async function save() {
  saving.value = true; error.value = ''
  try {
    const result = await dailyFrameApi.fill(checked.value.map(({ day, photo_id, mode, start_seconds, caption, version }) => ({ day, photo_id, mode, start_seconds, caption, version })))
    const successes = result.items.filter(item => item.status === 'saved').length
    const skipped = result.items.filter(item => item.status === 'skipped').length
    const failures = result.items.filter(item => item.status === 'failed')
    emit('saved')
    ElMessage.success(`已保存 ${successes} 天，跳过 ${skipped} 天，失败 ${failures.length} 天`)
    if (!failures.length) emit('update:modelValue', false)
    else items.value = items.value.filter(item => {
      const failed = failures.find(row => row.day === item.day)
      item.error = failed?.reason
      return !!failed
    })
  } catch (err) { error.value = dailyFrameError(err) } finally { saving.value = false }
}
watch(() => props.modelValue, visible => { if (visible) void load(); else requestId++ }, { immediate: true })
</script>
