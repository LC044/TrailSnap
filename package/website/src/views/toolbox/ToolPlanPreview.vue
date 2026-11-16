<template>
  <section class="space-y-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div><p class="ts-muted text-sm">{{ isPreview ? '真实预览，尚未执行' : labels[plan.status] || plan.status }}</p>
        <h2 class="mt-1 text-2xl font-bold">{{ scanning ? (plan.summary.processed || 0) : isCleanup && isPreview ? selectedCount : (plan.summary.success ?? plan.summary.ready ?? 0) }} <span class="text-base font-medium">{{ scanning ? '项已核对' : isPreview ? '项待处理' : '项已完成' }}</span></h2>
        <p class="ts-muted mt-2 text-sm">范围内 {{ plan.summary.total }} 项 · 跳过 {{ plan.summary.skipped || 0 }} 项<span v-if="plan.summary.failed"> · 失败 {{ plan.summary.failed }} 项</span></p>
      </div>
      <el-button :loading="exporting" @click="exportResult"><Download class="mr-1 h-4 w-4" />导出清单</el-button>
    </div>
    <div v-if="isAsyncCleanup" class="ts-surface space-y-2 p-4 text-sm" aria-live="polite">
      <p>{{ phases[plan.summary.phase] || '准备扫描' }} · 范围内 {{ plan.summary.total || 0 }} 项 · 已核对 {{ plan.summary.processed || 0 }} 项</p>
      <p v-if="plan.request.config.cleanup_mode === 'duplicate' && plan.summary.phase !== 'snapshot'">已计算哈希 {{ plan.summary.hashed || 0 }} · 复用哈希 {{ plan.summary.hash_reused || 0 }} · 读取失败 {{ plan.summary.hash_failed || 0 }}</p>
      <p v-if="plan.request.config.cleanup_mode === 'similar'">已比较 {{ plan.summary.compared || 0 }} 项</p>
      <p v-if="plan.request.config.cleanup_mode === 'similar'">缺少特征 {{ plan.summary.missing_vectors || 0 }} · 无效特征 {{ plan.summary.invalid_vectors || 0 }} · 更新特征缓存 {{ plan.summary.cache_changed || 0 }}</p>
      <p v-if="plan.summary.error" role="alert" class="break-all">{{ plan.summary.error }}</p>
      <p v-if="scanning" class="ts-muted">扫描在后台继续，可以离开此页面；停止后可从检查点继续。</p>
      <el-button v-if="['scan_stopped', 'scan_failed'].includes(plan.status)" @click="$emit('recover', 'retry')">继续扫描</el-button>
    </div>
    <div class="ts-divider rounded-xl border p-4 text-sm leading-6">
      <p><strong>范围：</strong>{{ scopeLabel }}</p>
      <p><strong>操作：</strong>{{ operationLabel }}</p>
      <p v-if="plan.request.config.target" class="break-all"><strong>目标：</strong>{{ plan.request.config.target }}</p>
      <p v-if="plan.request.config.action === 'copy'">预计生成 {{ plan.summary.output_files }} 个文件，约 {{ formatBytes(plan.summary.output_bytes || 0) }}。</p>
    </div>
    <el-alert v-if="isCleanup" title="清理候选默认不勾选。展开参考图核对后手动选择，重复组至少保留一项；确认后移入回收站，不永久删除。" type="warning" :closable="false" />
    <el-alert v-if="isPreview" title="修改范围或规则后，必须重新生成预览。文件已变化或目标被占用时将记录异常，不覆盖。" type="info" :closable="false" />
    <div class="flex flex-wrap items-center gap-2">
      <el-select v-model="status" placeholder="所有结果" clearable class="w-full sm:!w-44" @change="page = 1; load()">
        <el-option label="将变更" value="ready" /><el-option v-if="isCleanup" label="待核对候选" value="candidate" />
        <el-option label="跳过" value="skipped" /><el-option label="失败" value="failed" /><el-option label="成功" value="success" />
      </el-select>
      <el-button :loading="loading" @click="load">刷新明细</el-button>
      <span v-if="isCleanup" class="ts-muted text-sm">已手动选择 {{ selectedCount }} 项（跨页保留）</span>
    </div>
    <p v-if="error" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
    <div v-loading="loading" class="space-y-2">
      <article v-for="item in rows" :key="item.id" class="ts-divider flex min-w-0 items-start gap-3 rounded-xl border p-3">
        <el-checkbox v-if="isCleanup && isPreview && item.status === 'candidate'" :model-value="isAsyncCleanup ? item.selected : selected.includes(item.id)" :disabled="selecting"
          :aria-label="`将 ${basename(item.source)} 移入回收站`" @update:model-value="toggle(item.id, !!$event)" />
        <img :src="thumbnailUrl(item.photo_id)" :alt="basename(item.source)" loading="lazy" class="h-12 w-12 shrink-0 rounded-lg object-cover" />
        <div class="min-w-0 flex-1 text-sm">
          <p class="break-all">{{ basename(item.source) }}</p>
          <p v-if="item.target" class="mt-1 break-all font-medium text-primary-600 dark:text-primary-400">→ {{ plan.kind === 'rename' ? basename(item.target) : item.target }}</p>
          <p v-if="item.reason" class="ts-muted mt-1 text-xs">{{ item.reason }}</p>
          <p v-if="item.detail.label" class="mt-1 text-xs">{{ item.detail.label }}</p>
          <p v-if="plan.kind === 'metadata'" class="mt-1 break-all text-xs">{{ item.detail.time || '不改时间' }} · {{ item.detail.make }} {{ item.detail.model }}</p>
          <details class="ts-muted mt-2 text-xs" @toggle="referenceToggle($event, item)"><summary class="cursor-pointer">路径与参考详情</summary><p class="mt-2 break-all">原位置：{{ item.source }}</p>
            <div v-if="item.detail.group_id && references[item.detail.group_id]" class="mt-2 space-y-2">
              <p>与代表图逐张核验 · 同组 {{ references[item.detail.group_id].total }} 项</p>
              <div class="flex flex-wrap gap-2"><figure v-for="member in references[item.detail.group_id].items" :key="member.photo_id">
                <img :src="thumbnailUrl(member.photo_id)" alt="同组参考影像" loading="lazy" class="h-20 w-20 rounded-lg object-cover" />
                <figcaption v-if="!member.in_scope">范围外参考</figcaption><figcaption v-if="member.photo_id === references[item.detail.group_id].representative_id">代表图</figcaption>
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
      <p v-if="!rows.length && !loading && !error" class="ts-muted py-8 text-center text-sm">没有这类结果</p>
    </div>
    <div class="flex justify-center"><el-pagination v-model:current-page="page" :page-size="40" :total="total" layout="prev, pager, next" :pager-count="5" @current-change="load" /></div>
    <div v-if="isPreview" class="ts-divider space-y-3 border-t pt-4">
      <el-checkbox v-model="confirmed" class="plan-confirmation">我已查看范围了解真实变更</el-checkbox>
      <div class="flex flex-wrap justify-end gap-2">
        <el-button @click="$emit('back')">返回修改</el-button>
        <el-button type="primary" :loading="executing" :disabled="!confirmed || !actionCount || loading || selecting || !!error" @click="$emit('execute', isCleanup && !isAsyncCleanup ? selected : undefined)">
          确认{{ operationVerb }}<template v-if="!['移动', '复制'].includes(operationVerb)"> {{ actionCount }} 项</template>
        </el-button>
      </div>
    </div>
    <div v-else class="flex flex-wrap justify-end gap-2">
      <el-button v-if="['queued', 'running', 'scan_queued', 'scanning'].includes(plan.status)" :disabled="plan.stop_requested" @click="$emit('stop')">{{ plan.stop_requested ? '已请求停止后续项目' : '停止后续项目' }}</el-button>
      <el-button v-if="plan.summary.failed || (plan.status === 'stopped' && plan.summary.ready)" @click="$emit('recover', 'retry')">预览安全重试</el-button>
      <el-button v-if="undoAllowed" @click="$emit('recover', 'undo')">预览撤销</el-button>
      <el-button @click="$emit('again')">再次使用规则</el-button>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Download } from 'lucide-vue-next'
import { workflowApi, type ToolPlan, type ToolPlanItem } from '@/api/toolboxWorkflows'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { ElMessage } from 'element-plus'
const props = defineProps<{ plan: ToolPlan; executing: boolean }>()
defineEmits<{ execute: [selected?: number[]]; back: []; stop: []; recover: [mode: 'retry' | 'undo']; again: [] }>()
const labels: Record<string, string> = { preview: '待确认', queued: '排队中', running: '处理中', completed: '已完成', partial: '部分失败', stopped: '已停止', ready: '将变更', candidate: '待核对', skipped: '跳过', success: '成功', failed: '失败' }
const isPreview = computed(() => props.plan.status === 'preview')
Object.assign(labels, { scan_queued: '等待扫描', scanning: '扫描中', scan_stopped: '扫描已停止', scan_failed: '扫描失败' })
const isCleanup = computed(() => props.plan.kind === 'cleanup')
const isAsyncCleanup = computed(() => isCleanup.value && !!props.plan.summary.phase)
const scanning = computed(() => ['scan_queued', 'scanning'].includes(props.plan.status))
const phases: Record<string, string> = { snapshot: '核对扫描范围', hash: '检查文件哈希', groups: '查找照片分组', items: '生成候选', done: '扫描完成' }
const serverSelected = ref(0), selecting = ref(false)
const selectedCount = computed(() => isAsyncCleanup.value ? serverSelected.value : selected.value.length)
const references = ref<Record<number, { total: number; representative_id: string; items: { photo_id: string; in_scope: boolean }[] }>>({})
const referencePages = ref<Record<number, number>>({})
const selected = ref<number[]>([])
const confirmed = ref(false)
const page = ref(1), status = ref('')
const total = ref(0)
const rows = ref<ToolPlanItem[]>([])
const loading = ref(false), error = ref('')
const exporting = ref(false)
let sequence = 0
const load = async () => {
  const version = ++sequence
  loading.value = true
  try {
    const result = await workflowApi.items(props.plan.id, (page.value - 1) * 40, status.value || undefined)
    if (version !== sequence) return
    rows.value = result.items; total.value = result.total; serverSelected.value = result.selected_count || 0; error.value = ''
    references.value = {}; referencePages.value = {}
  } catch { if (version === sequence) error.value = '明细加载失败，请重试' }
  finally { if (version === sequence) loading.value = false }
}
watch(() => props.plan.id, () => { selected.value = []; confirmed.value = false; page.value = 1; status.value = ''; load() }, { immediate: true })
watch(() => props.plan.status, load)
const basename = (path: string) => path.split(/[\\/]/).at(-1) || path
const scopeLabel = computed(() => {
  const scope = props.plan.request.scope
  const names = { albums: `所选 ${scope.album_ids.length} 个相册`, folders: scope.folders.join('、'), selected: `明确选择 ${scope.photo_ids.length} 项`, filter: '条件筛选', all: '全部图库（主动选择）' }
  return `${names[scope.source]}${scope.start_date || scope.end_date ? ` · ${scope.start_date || '不限开始'} 至 ${scope.end_date || '不限结束'}` : ''}`
})
const operationVerb = computed(() => props.plan.kind === 'rename' ? '重命名' : props.plan.kind === 'cleanup' ? '移入回收站'
  : props.plan.kind === 'album' ? '归类到相册' : props.plan.kind === 'metadata' ? '写入拍摄信息' : props.plan.kind === 'undo' ? '恢复原路径'
  : props.plan.request.config.action === 'copy' ? '复制' : '移动')
const operationLabel = computed(() => {
  if (props.plan.kind === 'organize') return `${operationVerb.value}实际文件 · ${props.plan.request.config.layout === 'preserve' ? '保留原目录层级' : '重新归档'}`
  return operationVerb.value
})
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
    error.value = ''
  } catch { error.value = '选择未保存，请刷新核对后重试' }
  finally { selecting.value = false }
}
const loadReferences = async (groupId: number, page = 1) => {
  const planId = props.plan.id
  try {
    const result = await workflowApi.members(planId, groupId, (page - 1) * 24)
    if (planId !== props.plan.id) return
    references.value[groupId] = result; referencePages.value[groupId] = page
  } catch { error.value = '参考照片加载失败，请重试' }
}
const referenceToggle = (event: Event, item: ToolPlanItem) => {
  if ((event.target as HTMLDetailsElement).open && item.detail.group_id) loadReferences(item.detail.group_id)
}
const formatBytes = (bytes: number) => bytes > 1073741824 ? `${(bytes / 1073741824).toFixed(2)} GB` : `${(bytes / 1048576).toFixed(1)} MB`
const exportResult = async () => {
  exporting.value = true
  try {
    const blob = await workflowApi.export(props.plan.id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a'); link.href = url; link.download = `toolbox-${props.plan.id}.csv`; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch { ElMessage.error('清单导出失败') }
  finally { exporting.value = false }
}
</script>

<style scoped>
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
