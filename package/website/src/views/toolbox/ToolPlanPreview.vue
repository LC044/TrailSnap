<template>
  <section class="space-y-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="text-sm" aria-live="polite">
        <span v-if="scanning">正在查找 · {{ plan.summary.processed || 0 }} / {{ plan.summary.total || 0 }}</span>
        <span v-else-if="isCleanup && isPreview">已选 {{ selectedCount }} 张</span>
        <span v-else-if="isPreview">{{ plan.summary.ready || 0 }} 项待处理</span>
        <span v-else>{{ labels[plan.status] || plan.status }} · {{ plan.summary.success || 0 }} 项</span>
        <span v-if="plan.summary.failed" class="ml-2 text-red-600 dark:text-red-400">失败 {{ plan.summary.failed }} 项</span>
      </div>
    </div>
    <p v-if="plan.summary.error" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ plan.summary.error }}</p>
    <el-button v-if="['scan_stopped', 'scan_failed'].includes(plan.status)" @click="$emit('recover', 'retry')">继续</el-button>
    <p v-if="!isCleanup && plan.request.config.target" class="ts-muted break-all text-sm">{{ plan.request.config.target }}</p>
    <div class="flex flex-wrap items-center gap-2">
      <el-select v-if="resultFilters.length" v-model="status" placeholder="全部" clearable class="w-full sm:!w-44" @change="page = 1; load()">
        <el-option :label="isPreview ? (isCleanup ? '待选' : '待确认') : '全部'" value="" />
        <el-option v-for="option in resultFilters" :key="option.value" :label="option.label" :value="option.value" />
      </el-select>
      <el-button v-if="error" :loading="loading" @click="load">重试</el-button>
    </div>
    <p v-if="error" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
    <div v-loading="loading" class="space-y-2">
      <template v-if="isCleanup">
        <section v-for="(group, groupIndex) in photoGroups" :key="group.key" class="py-3">
          <h3 v-if="plan.request.config.cleanup_mode !== 'quality'" class="ts-muted mb-3 text-sm">第 {{ (page - 1) * 40 + groupIndex + 1 }} 组</h3>
          <div :class="isGroupedCleanup ? 'flex gap-2 overflow-x-auto pb-2' : 'grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4'">
            <article v-for="item in group.items" :key="item.id" class="relative min-w-0" :class="isGroupedCleanup && 'w-48 shrink-0 sm:w-56'">
              <el-image :src="thumbnailUrl(item.photo_id)" :preview-src-list="group.items.map(photo => thumbnailToFileUrl(thumbnailUrl(photo.photo_id)))" :initial-index="group.items.indexOf(item)" preview-teleported fit="cover" class="aspect-square w-full rounded-xl" :class="{ 'photo-selected': isAsyncCleanup ? item.selected : selected.includes(item.id) }" :alt="basename(item.source)" />
              <button v-if="isPreview && item.status === 'candidate'" type="button" role="checkbox" class="photo-choice" :class="{ 'is-selected': isAsyncCleanup ? item.selected : selected.includes(item.id) }" :aria-checked="!!(isAsyncCleanup ? item.selected : selected.includes(item.id))" :disabled="selecting" :aria-label="`将 ${basename(item.source)} 移入回收站`" @click="toggle(item.id, !(isAsyncCleanup ? item.selected : selected.includes(item.id)))">
                <span class="photo-choice-mark"><Check v-if="isAsyncCleanup ? item.selected : selected.includes(item.id)" :size="20" :stroke-width="3" /></span>
              </button>
              <p v-if="plan.request.config.cleanup_mode === 'quality'" class="ts-muted mt-2 break-words text-xs"
                :aria-label="qualityScoreLabel(item, true)">{{ qualityScoreLabel(item) }}</p>
              <details class="ts-muted mt-1 text-xs"><summary class="cursor-pointer py-2">详情</summary><p class="break-all">{{ item.source }}</p><p v-if="item.status === 'failed' || item.status === 'skipped'">{{ item.reason }}</p></details>
            </article>
          </div>
          <div v-if="!isGroupedCleanup && group.groupId && references[group.groupId] && (references[group.groupId].total > 24 || references[group.groupId].items.some(photo => !group.items.some(item => item.photo_id === photo.photo_id)))" class="mt-2">
            <p class="ts-muted mb-2 text-xs">同组照片</p>
            <div class="flex gap-2 overflow-x-auto">
              <el-image v-for="member in references[group.groupId].items.filter(photo => !group.items.some(item => item.photo_id === photo.photo_id))" :key="member.photo_id" :src="thumbnailUrl(member.photo_id)" :preview-src-list="references[group.groupId].items.map(photo => thumbnailToFileUrl(thumbnailUrl(photo.photo_id)))" :initial-index="references[group.groupId].items.indexOf(member)" preview-teleported fit="cover" class="h-24 w-24 shrink-0 rounded-lg" alt="同组参考照片" />
            </div>
            <el-pagination v-if="references[group.groupId].total > 24" :current-page="referencePages[group.groupId] || 1" :page-size="24" :total="references[group.groupId].total" layout="prev, next" @current-change="page => loadReferences(group.groupId!, page)" />
          </div>
          <el-pagination v-if="isGroupedCleanup && group.groupId && references[group.groupId]?.total > 24"
            :current-page="referencePages[group.groupId] || 1" :page-size="24" :total="references[group.groupId].total"
            layout="prev, next" @current-change="page => loadReferences(group.groupId!, page)" />
          <el-button v-if="group.groupId && !references[group.groupId]" link @click="loadReferences(group.groupId)">参考</el-button>
        </section>
      </template>
      <template v-else>
      <article v-for="item in rows" :key="item.id" class="ts-divider flex min-w-0 items-start gap-3 rounded-xl border p-3">
        <el-checkbox v-if="isCleanup && isPreview && item.status === 'candidate'" :model-value="isAsyncCleanup ? item.selected : selected.includes(item.id)" :disabled="selecting"
          :aria-label="`将 ${basename(item.source)} 移入回收站`" @update:model-value="toggle(item.id, !!$event)" />
        <img :src="thumbnailUrl(item.photo_id)" :alt="basename(item.source)" loading="lazy" class="h-24 w-24 shrink-0 rounded-lg object-cover sm:h-32 sm:w-32" />
        <div class="min-w-0 flex-1 text-sm">
          <p class="break-all">{{ basename(item.source) }}</p>
          <p v-if="item.target" class="mt-1 break-all font-medium text-primary-600 dark:text-primary-400">→ {{ plan.kind === 'rename' ? basename(item.target) : item.target }}</p>
          <p v-if="item.reason && (item.status === 'failed' || item.status === 'skipped')" class="ts-muted mt-1 text-xs">{{ item.reason }}</p>
          <p v-if="item.detail.label" class="mt-1 text-xs">{{ item.detail.label }}</p>
          <p v-if="plan.kind === 'metadata'" class="mt-1 break-all text-xs">{{ item.detail.time || '不改时间' }} · {{ item.detail.make }} {{ item.detail.model }}</p>
          <details :open="isCleanup" class="ts-muted mt-2 text-xs" @toggle="referenceToggle($event, item)"><summary class="cursor-pointer">照片详情</summary><p class="mt-2 break-all">原位置：{{ item.source }}</p>
            <div v-if="item.detail.group_id && references[item.detail.group_id]" class="mt-2 space-y-2">
              <p>同组 {{ references[item.detail.group_id].total }} 项</p>
              <div class="flex flex-wrap gap-2"><figure v-for="member in references[item.detail.group_id].items" :key="member.photo_id">
                <img :src="thumbnailUrl(member.photo_id)" alt="同组参考影像" loading="lazy" class="h-20 w-20 rounded-lg object-cover" />
                <figcaption v-if="!member.in_scope">范围外参考</figcaption><figcaption v-if="member.photo_id === references[item.detail.group_id].representative_id">保留参考</figcaption>
              </figure></div>
              <el-pagination :current-page="referencePages[item.detail.group_id] || 1" :page-size="24" :total="references[item.detail.group_id].total" layout="prev, next" @current-change="page => loadReferences(item.detail.group_id!, page)" />
            </div>
            <div v-if="item.detail.related_ids" class="mt-2 flex flex-wrap gap-2">
              <img v-for="id in item.detail.related_ids.slice(0, 12)" :key="id" :src="thumbnailUrl(id)" alt="同组参考影像"
                loading="lazy" class="h-20 w-20 rounded-lg object-cover" />
            </div>
          </details>
        </div>
        <span class="ts-muted shrink-0 text-xs">{{ labels[item.status] || item.status }}</span>
      </article>
      </template>
      <p v-if="!rows.length && !loading && !error" class="ts-muted py-8 text-center text-sm">没有这类结果</p>
    </div>
    <div class="flex justify-center"><el-pagination v-model:current-page="page" :page-size="40" :total="total" layout="prev, pager, next" :pager-count="5" @current-change="load" /></div>
    <div v-if="isPreview" class="plan-actions sticky bottom-0 z-10 flex flex-wrap items-center justify-between gap-3 py-3">
      <el-checkbox v-model="confirmed" class="plan-confirmation">已悉知变更情况</el-checkbox>
      <div class="flex flex-wrap justify-end gap-2">
        <el-button @click="$emit('back')">返回</el-button>
        <el-button type="primary" :loading="executing" :disabled="!confirmed || !actionCount || loading || selecting || !!error" @click="$emit('execute', isCleanup && !isAsyncCleanup ? selected : undefined)">
          {{ isCleanup ? '删除' : '确认' }}
        </el-button>
      </div>
    </div>
    <div v-else class="flex flex-wrap justify-end gap-2">
      <el-button v-if="['queued', 'running', 'scan_queued', 'scanning'].includes(plan.status)" :disabled="plan.stop_requested" @click="$emit('stop')">{{ plan.stop_requested ? '停止中' : '停止' }}</el-button>
      <el-button v-if="plan.summary.failed || (plan.status === 'stopped' && plan.summary.ready)" @click="$emit('recover', 'retry')">重试</el-button>
      <el-button v-if="undoAllowed" @click="$emit('recover', 'undo')">撤销</el-button>
      <el-button @click="$emit('again')">重来</el-button>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check } from 'lucide-vue-next'
import { workflowApi, type ToolPlan, type ToolPlanItem } from '@/api/toolboxWorkflows'
import { thumbnailUrl, thumbnailToFileUrl } from '@/utils/mediaUrl'
const props = defineProps<{ plan: ToolPlan; executing: boolean }>()
defineEmits<{ execute: [selected?: number[]]; back: []; stop: []; recover: [mode: 'retry' | 'undo']; again: [] }>()
const labels: Record<string, string> = { preview: '待确认', queued: '排队中', running: '处理中', completed: '已完成', partial: '部分失败', stopped: '已停止', ready: '待确认', candidate: '待选', skipped: '跳过', success: '成功', failed: '失败' }
const isPreview = computed(() => props.plan.status === 'preview')
Object.assign(labels, { scan_queued: '等待扫描', scanning: '扫描中', scan_stopped: '扫描已停止', scan_failed: '扫描失败' })
const isGroupedCleanup = computed(() => props.plan.kind === 'cleanup' && ['similar', 'duplicate'].includes(props.plan.request.config.cleanup_mode))
const isCleanup = computed(() => props.plan.kind === 'cleanup')
const isAsyncCleanup = computed(() => isCleanup.value && !!props.plan.summary.phase)
const resultFilters = computed(() => {
  const options: { label: string; value: string }[] = []
  if (!isAsyncCleanup.value && props.plan.summary.skipped) options.push({ label: '跳过', value: 'skipped' })
  if (props.plan.summary.failed) options.push({ label: '失败', value: 'failed' })
  return options
})
const scanning = computed(() => ['scan_queued', 'scanning'].includes(props.plan.status))
const serverSelected = ref(0), selecting = ref(false)
const selectedCount = computed(() => isAsyncCleanup.value ? serverSelected.value : selected.value.length)
const references = ref<Record<number, { total: number; representative_id: string; items: { photo_id: string; in_scope: boolean; source?: string; item?: ToolPlanItem | null }[] }>>({})
const referencePages = ref<Record<number, number>>({})
const selected = ref<number[]>([])
const confirmed = ref(false)
const page = ref(1), status = ref('')
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
  const groups = new Map<string, { key: string; groupId?: number; title: string; items: ToolPlanItem[] }>()
  for (const item of rows.value) {
    const key = props.plan.request.config.cleanup_mode === 'quality' ? 'quality' : item.detail.group_id ? `group-${item.detail.group_id}` : `item-${item.id}`
    if (!groups.has(key)) groups.set(key, { key, groupId: item.detail.group_id, title: item.detail.label || '照片', items: [] })
    groups.get(key)!.items.push(item)
  }
  if (isGroupedCleanup.value) {
    for (const group of groups.values()) {
      const members = group.groupId && references.value[group.groupId]
      if (members) {
        group.items = members.items.map(member => member.item || group.items.find(item => item.photo_id === member.photo_id)
          || { id: -members.items.indexOf(member) - 1, photo_id: member.photo_id, source: member.source || member.photo_id,
            target: '', status: 'skipped', reason: '此结果不支持选择，请重新查找', detail: {} } as ToolPlanItem)
      }
    }
  }
  return [...groups.values()]
})
const loading = ref(false), error = ref('')
let sequence = 0
const load = async () => {
  const version = ++sequence
  loading.value = true
  try {
    const result = await workflowApi.items(props.plan.id, (page.value - 1) * 40, status.value || (isPreview.value ? (isCleanup.value ? 'candidate' : 'ready') : undefined), isGroupedCleanup.value)
    if (version !== sequence) return
    rows.value = result.items; total.value = result.total; serverSelected.value = result.selected_count || 0; error.value = ''
    references.value = {}; referencePages.value = {}
    if (isCleanup.value) {
      const ids = [...new Set(result.items.map(item => item.detail.group_id).filter((id): id is number => !!id))]
      for (let offset = 0; offset < ids.length; offset += 4) {
        if (version !== sequence) return
        await Promise.all(ids.slice(offset, offset + 4).map(id => loadReferences(id, 1, version)))
      }
    }
  } catch { if (version === sequence) error.value = '明细加载失败，请重试' }
  finally { if (version === sequence) loading.value = false }
}
watch(() => props.plan.id, () => { selected.value = []; confirmed.value = false; page.value = 1; status.value = ''; load() }, { immediate: true })
watch(() => props.plan.status, () => { selected.value = []; confirmed.value = false; status.value = ''; page.value = 1; load() })
const basename = (path: string) => path.split(/[\\/]/).at(-1) || path
const operationVerb = computed(() => props.plan.kind === 'rename' ? '重命名' : props.plan.kind === 'cleanup' ? '移入回收站'
  : props.plan.kind === 'album' ? '归类到相册' : props.plan.kind === 'metadata' ? '写入拍摄信息' : props.plan.kind === 'undo' ? '恢复原路径'
  : props.plan.request.config.action === 'copy' ? '复制' : '移动')
const actionCount = computed(() => isCleanup.value ? selectedCount.value : props.plan.summary.ready || 0)
const undoAllowed = computed(() => ['completed', 'partial', 'stopped'].includes(props.plan.status)
  && ['organize', 'rename'].includes(props.plan.kind) && props.plan.request.config.action !== 'copy'
  && !!props.plan.finished_at && Date.now() - new Date(props.plan.finished_at + 'Z').getTime() < 86400000)
const toggle = async (id: number, checked: boolean) => {
  if (!isAsyncCleanup.value) { selected.value = checked ? [...new Set([...selected.value, id])] : selected.value.filter(value => value !== id); return }
  if (selecting.value) return
  const planId = props.plan.id
  selecting.value = true
  try {
    const result = await workflowApi.selection(props.plan, [id], checked)
    if (props.plan.id !== planId) return
    serverSelected.value = result.selected_count
    const row = rows.value.find(item => item.id === id)
    if (row) row.selected = checked
    for (const group of Object.values(references.value)) {
      const member = group.items.find(member => member.item?.id === id)
      if (member?.item) member.item.selected = checked
    }
    error.value = ''
  } catch { error.value = '选择未保存，请刷新核对后重试' }
  finally { selecting.value = false }
}
const referenceRequests = new Map<number, number>()
const loadReferences = async (groupId: number, page = 1, requestSequence = sequence) => {
  const planId = props.plan.id
  const version = (referenceRequests.get(groupId) || 0) + 1
  referenceRequests.set(groupId, version)
  const isCurrent = () => planId === props.plan.id && requestSequence === sequence
    && referenceRequests.get(groupId) === version
  try {
    const result = await workflowApi.members(planId, groupId, (page - 1) * 24)
    if (!isCurrent()) return
    references.value[groupId] = result; referencePages.value[groupId] = page
  } catch { if (isCurrent()) error.value = '参考照片加载失败，请重试' }
}
const referenceToggle = (event: Event, item: ToolPlanItem) => {
  if ((event.target as HTMLDetailsElement).open && item.detail.group_id) loadReferences(item.detail.group_id)
}
</script>

<style scoped>
.photo-choice {
  position: absolute; top: 4px; right: 4px;
  display: grid; place-items: center; width: 48px; height: 48px;
  border: 0; background: transparent; cursor: pointer;
}
.photo-choice-mark {
  display: grid; place-items: center; width: 30px; height: 30px;
  border: 2px solid white; border-radius: 50%;
  background: rgb(0 0 0 / 35%); color: white;
  box-shadow: 0 1px 5px rgb(0 0 0 / 35%);
}
.photo-choice.is-selected .photo-choice-mark { background: var(--theme-primary); }
.photo-choice:focus-visible { outline: 3px solid var(--theme-primary); border-radius: 50%; }
.photo-choice:disabled { cursor: wait; opacity: .6; }
.photo-selected { outline: 3px solid var(--theme-primary); outline-offset: -3px; }
.plan-actions {
  background: var(--ts-color-surface);
  border-top: 1px solid var(--ts-color-divider);
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
