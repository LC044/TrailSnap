<template>
  <section class="space-y-5" :aria-busy="loading || taskActive">
    <div v-if="isPreview" class="plan-actions sticky top-0 z-20 flex flex-wrap items-center justify-between gap-3 py-3">
      <el-checkbox v-if="!isCleanup" v-model="confirmed" class="plan-confirmation">已悉知变更情况</el-checkbox>
      <div class="ml-auto flex flex-wrap justify-end gap-2">
        <el-button @click="$emit('back')">返回</el-button>
        <el-button v-if="isGroupedCleanup" @click="$emit('rescan')">重新查找</el-button>
        <el-button type="primary" :loading="executing" :disabled="!canExecute || showDeleteConfirmation" @click="requestExecution">
          {{ isCleanup ? '删除' : '确认' }}
        </el-button>
      </div>
    </div>
    <div v-else class="plan-actions sticky top-0 z-20 flex flex-wrap justify-end gap-2 py-3">
      <el-button v-if="['queued', 'running', 'scan_queued', 'scanning'].includes(plan.status)" :disabled="plan.stop_requested" @click="$emit('stop')">{{ plan.stop_requested ? '停止中' : '停止' }}</el-button>
      <el-button v-if="['scan_stopped', 'scan_failed'].includes(plan.status) || plan.summary.failed || (plan.status === 'stopped' && plan.summary.ready)" @click="$emit('recover', 'retry')">{{ ['scan_stopped', 'scan_failed'].includes(plan.status) ? '继续' : '重试' }}</el-button>
      <el-button v-if="undoAllowed" @click="$emit('recover', 'undo')">撤销</el-button>
      <el-button @click="$emit('again')">重来</el-button>
    </div>
    <p v-if="freshnessMessage" role="status" class="ts-muted ts-divider rounded-lg border p-3 text-sm">{{ freshnessMessage }}</p>
    <div v-if="!taskActive" class="flex flex-wrap items-start justify-between gap-3">
      <div class="text-sm" aria-live="polite">
        <span v-if="isCleanup && isPreview">已选 {{ selectedCount }} 张</span>
        <span v-else-if="isPreview">{{ plan.summary.ready || 0 }} 项待处理</span>
        <span v-else>{{ labels[plan.status] || plan.status }} · {{ plan.summary.success || 0 }} 项</span>
        <span v-if="plan.summary.failed" class="ml-2 text-red-600 dark:text-red-400">失败 {{ plan.summary.failed }} 项</span>
      </div>
    </div>
    <p v-if="plan.summary.error" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ plan.summary.error }}</p>
    <p v-if="!isCleanup && plan.request.config.target" class="ts-muted break-all text-sm">{{ plan.request.config.target }}</p>
    <div class="flex flex-wrap items-center gap-2">
      <el-select v-if="resultFilters.length" v-model="status" placeholder="全部" clearable class="w-full sm:!w-44" :disabled="selecting" @change="resetResults">
        <el-option :label="isPreview ? (isCleanup ? '待选' : '待确认') : '全部'" value="" />
        <el-option v-for="option in resultFilters" :key="option.value" :label="option.label" :value="option.value" />
      </el-select>
      <el-button v-if="error" :loading="loading" @click="load">重试</el-button>
      <el-button v-if="selectionError" :loading="loading" @click="resetResults">重新加载</el-button>
    </div>
    <p v-if="error || selectionError" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ selectionError || error }}</p>
    <div v-if="taskActive" role="status" class="flex min-h-40 flex-col items-center justify-center gap-3 py-8">
      <Loader2 class="h-8 w-8 animate-spin text-primary-500 motion-reduce:animate-none" aria-hidden="true" />
      <p class="text-sm">{{ taskStatusText }}</p>
      <p v-if="scanning && plan.summary.total > 0" class="ts-muted text-sm">已处理 {{ plan.summary.processed || 0 }} / {{ plan.summary.total }} 张</p>
    </div>
    <div v-loading="loading && !rows.length && !taskActive" class="space-y-2">
      <template v-if="isCleanup">
        <section v-for="(group, groupIndex) in photoGroups" :key="group.key" class="py-3">
          <h3 v-if="plan.request.config.cleanup_mode !== 'quality'" class="ts-muted mb-3 text-sm">第 {{ groupIndex + 1 }} 组</h3>
          <div :class="isGroupedCleanup ? 'flex gap-2 overflow-x-auto pb-2' : 'grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4'">
            <article v-for="item in group.items" :key="item.id" class="relative min-w-0" :class="isGroupedCleanup && 'w-48 shrink-0 sm:w-56'">
              <div class="relative">
                <button v-if="canSelect(item)" type="button" role="checkbox" class="photo-choice block aspect-square w-full overflow-hidden rounded-xl"
                  :class="{ 'photo-selected': isSelected(item) }" :aria-checked="isSelected(item)" :disabled="selecting || !!selectionError || executing"
                  :aria-label="`将 ${basename(item.source)} 移入回收站`" @click="toggle(item.id, !isSelected(item))">
                  <img :src="thumbnailUrl(item.photo_id)" alt="" loading="lazy" class="h-full w-full object-cover" />
                  <span class="photo-choice-mark" :class="{ 'is-selected': isSelected(item) }"><Check v-if="isSelected(item)" :size="20" :stroke-width="3" /></span>
                </button>
                <ToolboxPhotoPreview :photo-id="item.photo_id" :photo-ids="group.photoIds"
                  :icon-only="canSelect(item)" :class="canSelect(item) ? 'absolute bottom-2 right-2' : 'aspect-square w-full rounded-xl'" :alt="basename(item.source)" />
              </div>
              <p v-if="plan.request.config.cleanup_mode === 'quality'" class="ts-muted mt-2 break-words text-xs"
                :aria-label="qualityScoreLabel(item, true)">{{ qualityScoreLabel(item) }}</p>
              <p v-if="plan.request.config.cleanup_mode === 'duplicate'" class="ts-muted mt-2 break-all text-xs">{{ item.source }}</p>
              <details v-else class="ts-muted mt-1 text-xs"><summary class="cursor-pointer py-2">详情</summary><p class="break-all">{{ item.source }}</p><p v-if="item.status === 'failed' || item.status === 'skipped'">{{ item.reason }}</p></details>
              <p v-if="plan.request.config.cleanup_mode === 'duplicate' && (item.status === 'failed' || item.status === 'skipped')" class="ts-muted mt-1 text-xs">{{ item.reason }}</p>
            </article>
            <template v-if="group.groupId && isGroupedCleanup">
              <AutoLoadSentinel v-if="canLoadMembers(group.groupId)" @load="loadReferences(group.groupId)" />
              <el-button v-else-if="memberErrors[group.groupId]" class="self-center" @click="loadReferences(group.groupId)">重试</el-button>
              <span v-else-if="memberLoading[group.groupId]" role="status" class="ts-muted shrink-0 self-center text-xs">正在加载同组照片…</span>
            </template>
          </div>
        </section>
      </template>
      <template v-else>
      <article v-for="item in rows" :key="item.id" class="ts-divider flex min-w-0 items-start gap-3 rounded-xl border p-3">
        <ToolboxPhotoPreview :photo-id="item.photo_id" :alt="basename(item.source)" class="h-24 w-24 shrink-0 rounded-lg object-cover sm:h-32 sm:w-32" />
        <div class="min-w-0 flex-1 text-sm">
          <p class="break-all">{{ basename(item.source) }}</p>
          <p v-if="item.target" class="mt-1 break-all font-medium text-primary-600 dark:text-primary-400">→ {{ plan.kind === 'rename' ? basename(item.target) : item.target }}</p>
          <p v-if="item.reason && (item.status === 'failed' || item.status === 'skipped')" class="ts-muted mt-1 text-xs">{{ item.reason }}</p>
          <p v-if="item.detail.label" class="mt-1 text-xs">{{ item.detail.label }}</p>
          <p v-if="plan.kind === 'metadata'" class="mt-1 break-all text-xs">{{ item.detail.time || '不改时间' }} · {{ item.detail.make }} {{ item.detail.model }}</p>
          <details class="ts-muted mt-2 text-xs"><summary class="cursor-pointer">照片详情</summary><p class="mt-2 break-all">原位置：{{ item.source }}</p>
            <div v-if="item.detail.related_ids" class="mt-2 flex flex-wrap gap-2">
              <ToolboxPhotoPreview v-for="id in item.detail.related_ids.slice(0, 12)" :key="id" :photo-id="id" alt="同组参考影像"
                class="h-20 w-20 rounded-lg object-cover" />
            </div>
          </details>
        </div>
        <span class="ts-muted shrink-0 text-xs">{{ labels[item.status] || item.status }}</span>
      </article>
      </template>
      <p v-if="!rows.length && !loading && !error && !taskActive" class="ts-muted py-8 text-center text-sm">没有这类结果</p>
    </div>
    <p v-if="loading && rows.length" role="status" class="ts-muted py-3 text-center text-sm">正在加载更多结果…</p>
    <AutoLoadSentinel v-if="rows.length < total && !loading && !error && !taskActive" @load="load" />
  </section>
  <ConfirmDialog v-model:visible="showDeleteConfirmation" title="确认移入回收站"
    :message="`将选中的 ${selectedCount} 张照片移入回收站？`" confirm-text="移入回收站" @confirm="execute" />
</template>
<script setup lang="ts">
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import AutoLoadSentinel from '@/components/ui/AutoLoadSentinel.vue'
import { thumbnailUrl } from '@/utils/mediaUrl'
import ToolboxPhotoPreview from './ToolboxPhotoPreview.vue'
import { computed, reactive, ref, watch } from 'vue'
import { Check, Loader2 } from 'lucide-vue-next'
import { workflowApi, type ToolPlan, type ToolPlanItem } from '@/api/toolboxWorkflows'
const props = defineProps<{ plan: ToolPlan; executing: boolean }>()
const emit = defineEmits<{ execute: [selected?: number[]]; back: []; rescan: []; stop: []; recover: [mode: 'retry' | 'undo']; again: [] }>()
const labels: Record<string, string> = { preview: '待确认', queued: '排队中', running: '处理中', completed: '已完成', partial: '部分失败', stopped: '已停止', ready: '待确认', candidate: '待选', skipped: '跳过', success: '成功', failed: '失败' }
const isPreview = computed(() => props.plan.status === 'preview')
Object.assign(labels, { scan_queued: '等待扫描', scanning: '扫描中', scan_stopped: '扫描已停止', scan_failed: '扫描失败' })
const isGroupedCleanup = computed(() => props.plan.kind === 'cleanup' && ['similar', 'duplicate'].includes(props.plan.request.config.cleanup_mode))
const previewExpired = computed(() => isPreview.value && isGroupedCleanup.value && props.plan.cleanup_freshness === 'expired')
const freshnessMessage = computed(() => {
  if (!isPreview.value || !isGroupedCleanup.value) return ''
  if (previewExpired.value) return '这份结果已过期。可以查看照片，重新查找后可继续清理。'
  if (props.plan.cleanup_freshness === 'changed') return '图库自上次查找后已有变化。可以重新查找，或核对旧结果后继续。删除前会复核所选照片。'
  if (props.plan.cleanup_freshness === 'unknown') return '无法确认这份结果是否仍是最新。请核对照片，或重新查找。'
  return ''
})
const isCleanup = computed(() => props.plan.kind === 'cleanup')
const isAsyncCleanup = computed(() => isCleanup.value && !!props.plan.summary.phase)
const resultFilters = computed(() => {
  const options: { label: string; value: string }[] = []
  if (!isAsyncCleanup.value && props.plan.summary.skipped) options.push({ label: '跳过', value: 'skipped' })
  if (props.plan.summary.failed) options.push({ label: '失败', value: 'failed' })
  return options
})
const scanning = computed(() => ['scan_queued', 'scanning'].includes(props.plan.status))
const taskActive = computed(() => ['scan_queued', 'scanning', 'queued', 'running'].includes(props.plan.status))
const taskStatusText = computed(() => ({ scan_queued: '等待开始查找…', scanning: '正在查找照片…', queued: '等待开始处理…', running: '正在处理照片…' } as Record<string, string>)[props.plan.status] || '')
const serverSelected = ref(0), selecting = ref(false)
const selectedCount = computed(() => isAsyncCleanup.value ? serverSelected.value : selected.value.length)
const references = ref<Record<number, { total: number; representative_id: string; items: { photo_id: string; in_scope: boolean; source?: string; item?: ToolPlanItem | null }[] }>>({})
const memberLoading = ref<Record<number, boolean>>({})
const memberErrors = ref<Record<number, boolean>>({})
const selectionError = ref('')
const savedSelections = reactive(new Map<number, boolean>())
let selectionVersion = 0
const selected = ref<number[]>([])
const confirmed = ref(false)
const showDeleteConfirmation = ref(false)
const status = ref('')
const total = ref(0)
const rows = ref<ToolPlanItem[]>([])
const qualityScoreLabel = (item: ToolPlanItem, accessible = false) => {
  const { quality_score, memory_score, label } = item.detail
  // Older plans only have the combined score label; do not invent missing scores.
  if (quality_score === undefined || memory_score === undefined) return label || '评分信息不可用'
  const quality = quality_score ?? 0
  const total = quality + (memory_score ?? 0)
  return accessible
    ? `质量分（0–100）${quality} / 综合评分（0–200）${total}`
    : `质量分 ${quality} / 综合评分 ${total}`
}
const photoGroups = computed(() => {
  const groups = new Map<string, { key: string; groupId?: number; items: ToolPlanItem[] }>()
  for (const item of rows.value) {
    const key = props.plan.request.config.cleanup_mode === 'quality' ? 'quality' : item.detail.group_id ? `group-${item.detail.group_id}` : `item-${item.id}`
    if (!groups.has(key)) groups.set(key, { key, groupId: item.detail.group_id, items: [] })
    groups.get(key)!.items.push(item)
  }
  if (isGroupedCleanup.value) {
    for (const group of groups.values()) {
      const members = group.groupId && references.value[group.groupId]
      if (members?.items.length) {
        const items = new Map(group.items.map(item => [item.photo_id, item]))
        members.items.forEach((member, index) => {
          items.set(member.photo_id, member.item ?? items.get(member.photo_id) ?? {
            id: -index - 1, photo_id: member.photo_id, source: member.source || member.photo_id,
            target: '', status: 'skipped', reason: '此结果不支持选择，请重新查找', detail: {},
          })
        })
        group.items = [...items.values()]
      }
    }
  }
  return [...groups.values()].map(group => ({ ...group, photoIds: group.items.map(item => item.photo_id) }))
})
const loading = ref(false), error = ref('')
let sequence = 0
const load = async () => {
  if (loading.value || taskActive.value) return
  const version = sequence
  const currentSelectionVersion = selectionVersion
  loading.value = true
  error.value = ''
  try {
    const result = await workflowApi.items(props.plan.id, rows.value.length, status.value || (isPreview.value ? (isCleanup.value ? 'candidate' : 'ready') : undefined), isGroupedCleanup.value)
    if (version !== sequence) return
    rows.value.push(...result.items)
    total.value = result.items.length ? result.total : rows.value.length
    if (currentSelectionVersion === selectionVersion && !selecting.value) serverSelected.value = result.selected_count || 0
  } catch { if (version === sequence) error.value = '明细加载失败，请重试' }
  finally { if (version === sequence) loading.value = false }
}
const resetResults = () => {
  sequence++
  loading.value = false
  rows.value = []
  total.value = 0
  references.value = {}
  memberErrors.value = {}
  memberLoading.value = {}
  savedSelections.clear()
  serverSelected.value = 0
  selectionError.value = ''
  load()
}
watch(() => [props.plan.id, props.plan.status], () => {
  selected.value = []
  confirmed.value = false
  showDeleteConfirmation.value = false
  status.value = ''
  resetResults()
}, { immediate: true })
const basename = (path: string) => path.split(/[\\/]/).at(-1) || path
const actionCount = computed(() => isCleanup.value ? selectedCount.value : props.plan.summary.ready || 0)
const canExecute = computed(() => isPreview.value && !props.executing && !previewExpired.value
  && (isCleanup.value || confirmed.value) && actionCount.value > 0 && !selecting.value
  && !selectionError.value && (rows.value.length > 0 || (!loading.value && !error.value)))
const execute = () => {
  if (canExecute.value) emit('execute', isCleanup.value && !isAsyncCleanup.value ? selected.value : undefined)
}
const requestExecution = () => {
  if (!canExecute.value) return
  if (isCleanup.value) showDeleteConfirmation.value = true
  else execute()
}
const undoAllowed = computed(() => ['completed', 'partial', 'stopped'].includes(props.plan.status)
  && ['organize', 'rename'].includes(props.plan.kind) && props.plan.request.config.action !== 'copy'
  && !!props.plan.finished_at && Date.now() - new Date(props.plan.finished_at + 'Z').getTime() < 86400000)
const canSelect = (item: ToolPlanItem) => isPreview.value && !previewExpired.value && item.status === 'candidate'
const isSelected = (item: ToolPlanItem) => isAsyncCleanup.value
  ? (savedSelections.get(item.id) ?? !!item.selected)
  : selected.value.includes(item.id)
const toggle = async (id: number, checked: boolean) => {
  if (!isAsyncCleanup.value) {
    selected.value = checked ? [...new Set([...selected.value, id])] : selected.value.filter(value => value !== id)
    return
  }
  if (selecting.value) return
  const { id: planId, status: planStatus } = props.plan
  selecting.value = true
  selectionVersion++
  try {
    const result = await workflowApi.selection(props.plan, [id], checked)
    if (props.plan.id !== planId || props.plan.status !== planStatus) return
    savedSelections.set(id, checked)
    serverSelected.value = result.selected_count
  } catch {
    if (props.plan.id === planId && props.plan.status === planStatus) selectionError.value = '选择未保存，请重新加载后核对'
  } finally {
    selectionVersion++
    selecting.value = false
  }
}
const canLoadMembers = (id: number) => !memberLoading.value[id] && !memberErrors.value[id]
  && (!references.value[id] || references.value[id].items.length < references.value[id].total)
const loadReferences = async (groupId: number) => {
  if (memberLoading.value[groupId] || (references.value[groupId] && references.value[groupId].items.length >= references.value[groupId].total)) return
  const version = sequence
  const previous = references.value[groupId]?.items ?? []
  memberLoading.value[groupId] = true
  memberErrors.value[groupId] = false
  try {
    const result = await workflowApi.members(props.plan.id, groupId, previous.length)
    if (version !== sequence) return
    references.value[groupId] = {
      ...result,
      total: result.items.length ? result.total : previous.length,
      items: [...previous, ...result.items],
    }
  } catch { if (version === sequence) memberErrors.value[groupId] = true }
  finally { if (version === sequence) memberLoading.value[groupId] = false }
}
</script>

<style scoped>
.photo-choice {
  position: relative;
  cursor: pointer;
}
.photo-choice-mark {
  position: absolute; top: 8px; left: 8px;
  display: grid; place-items: center; width: 30px; height: 30px;
  border: 2px solid white; border-radius: 50%;
  background: rgb(0 0 0 / 35%); color: white;
  box-shadow: 0 1px 5px rgb(0 0 0 / 35%);
}
.photo-choice-mark.is-selected { background: var(--theme-primary); }
.photo-choice:focus-visible { outline: 3px solid var(--theme-primary); }
.photo-choice:disabled { cursor: wait; opacity: .6; }
.photo-selected::after { content: ""; position: absolute; inset: 0; border: 3px solid var(--theme-primary); border-radius: inherit; pointer-events: none; }
.plan-actions {
  background: var(--ts-color-surface);
  border-bottom: 1px solid var(--ts-color-divider);
}
.plan-confirmation {
  max-width: 100%;
  height: auto;
  min-height: 44px;
  margin-right: 0;
}
.plan-confirmation :deep(.el-checkbox__label) {
  min-width: 0;
  white-space: normal;
  overflow-wrap: anywhere;
}
</style>
