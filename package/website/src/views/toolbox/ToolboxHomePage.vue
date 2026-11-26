<template>
  <AppPage size="wide" bottom-safe class="py-5 md:py-8">
    <header class="journal-index-header mb-6 flex min-w-0 items-end justify-between gap-3">
      <h1 class="ts-page-title">工具箱</h1>
      <button type="button" class="journal-secondary-link" @click="showHistory"><Clock3 class="h-4 w-4" />操作记录</button>
    </header>
    <section v-if="active.length" class="ts-surface mb-7 p-4 md:p-5" aria-label="正在进行">
      <h2 class="ts-section-title mb-3">正在进行</h2>
      <button v-for="plan in active" :key="plan.id" type="button" class="ts-divider flex w-full items-center justify-between gap-3 border-t py-3 text-left"
        @click="open(plan)">
        <span><span class="font-medium">{{ titles[plan.kind] }}</span><span class="ts-muted ml-2 text-sm">{{ plan.summary.total }} 项</span></span>
        <span class="text-sm text-primary-600 dark:text-primary-400">{{ plan.stop_requested ? '请求停止中' : labels[plan.status] }}<ChevronRight class="ml-1 inline h-4 w-4" /></span>
      </button>
    </section>
    <div class="space-y-6">
      <section v-for="group in toolGroups" :key="group.title" :aria-label="group.title">
        <h2 class="ts-section-title mb-3">{{ group.title }}</h2>
        <div class="workbench-grid">
          <RouterLink v-for="tool in group.tools" :key="tool.path" :to="tool.path" class="workbench-tool">
            <span class="workbench-tool-icon"><component :is="tool.icon" class="h-6 w-6" /></span>
            <h3 class="min-w-0 flex-1 font-semibold">{{ tool.title }}</h3>
            <ChevronRight class="ts-muted h-4 w-4" />
          </RouterLink>
        </div>
      </section>
    </div>
    <details id="history" ref="historyPanel" class="mt-7" :open="historyOpen || !!error" @toggle="historyOpen = ($event.target as HTMLDetailsElement).open">
      <summary id="history-heading" class="cursor-pointer py-3 font-semibold">操作记录</summary>
      <p v-if="error" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <div class="ts-surface overflow-hidden">
        <button v-for="plan in history" :key="plan.id" type="button" class="ts-divider flex w-full items-center gap-3 border-b p-4 text-left last:border-b-0" @click="viewRecord(plan)">
          <Clock3 class="h-5 w-5 shrink-0 text-primary-500" />
          <div class="min-w-0 flex-1">
            <p class="text-sm font-semibold">{{ titles[plan.kind] }}</p>
            <time class="ts-muted text-xs">{{ dateLabel(plan.created_at) }}</time>
          </div><ChevronRight class="ts-muted h-4 w-4" />
        </button>
        <p v-if="!history.length && !loading && !error" class="ts-muted p-6 text-center text-sm">暂无操作记录</p>
      </div>
      <p v-if="loading" role="status" class="ts-muted py-3 text-center text-sm">正在加载操作记录…</p>
      <el-button v-else-if="error" @click="load">重试</el-button>
      <AutoLoadSentinel v-else-if="historyOpen && hasMoreHistory" @load="load" />
    </details>
    <ResponsiveDialog v-model="recordOpen" title="操作详情" mobile-mode="fullscreen" mobile-back>
      <template v-if="record">
        <div class="mb-4 flex flex-wrap justify-end gap-2">
          <el-button v-if="!isActive(record)" :disabled="deletingRecord" @click="showDeleteRecord = true">删除计划</el-button>
          <el-button type="primary" :disabled="deletingRecord" @click="open(record)">{{ actionLabel(record) }}</el-button>
        </div>
        <p class="font-medium">{{ titles[record.kind] }}</p>
        <p class="ts-muted mt-1 text-sm">{{ dateLabel(record.created_at) }}</p>
        <p class="my-4 text-sm">处理 {{ record.summary.success || 0 }} 项 · 跳过 {{ record.summary.skipped || 0 }} 项 · 失败 {{ record.summary.failed || 0 }} 项</p>
        <p v-if="detailError" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ detailError }} <el-button @click="loadDetails">重试</el-button></p>
        <div v-loading="detailLoading && !detailRows.length" class="space-y-3">
          <article v-for="item in detailRows" :key="item.id" class="ts-divider flex min-w-0 gap-3 border-b py-3">
            <ToolboxPhotoPreview :photo-id="item.photo_id" alt="操作照片" class="h-16 w-16 shrink-0 rounded-lg object-cover" />
            <div class="min-w-0 flex-1 text-sm">
              <p class="truncate" :title="basename(item.source)">{{ basename(item.source) }}</p>
              <p class="ts-muted mt-1">{{ resultLabels[item.status] || item.status }}</p>
              <details class="mt-1"><summary class="ts-muted cursor-pointer text-xs">详情</summary>
                <p class="mt-2 break-all">{{ item.source }}</p>
                <p v-if="item.target" class="mt-1 break-all">→ {{ item.target }}</p>
                <p v-if="item.detail.targets?.length" class="mt-1 break-all">{{ item.detail.targets.join('、') }}</p>
                <p v-if="item.reason && ['failed', 'skipped'].includes(item.status)" class="ts-muted mt-1">{{ item.reason }}</p>
              </details>
            </div>
          </article>
          <p v-if="!detailRows.length && !detailLoading && !detailError" class="ts-muted py-4 text-sm">暂无明细</p>
        </div>

        <p v-if="detailLoading && detailRows.length" role="status" class="ts-muted py-3 text-center text-sm">正在加载更多明细…</p>
        <AutoLoadSentinel v-if="recordOpen && detailRows.length < detailTotal && !detailLoading && !detailError" @load="loadDetails" />
      </template>
    </ResponsiveDialog>
    <ConfirmDialog v-model:visible="showDeleteRecord" title="删除计划"
      :message="deletePlanMessage"
      confirm-text="删除计划" @confirm="deleteRecord" />
  </AppPage>
</template>
<script setup lang="ts">
import AutoLoadSentinel from '@/components/ui/AutoLoadSentinel.vue'
import ToolboxPhotoPreview from './ToolboxPhotoPreview.vue'
import { nextTick, onBeforeUnmount, onActivated, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { FolderOpen, Tag, Images, Copy, Trash2, Clock3, ChevronRight } from 'lucide-vue-next'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import AppPage from '@/components/ui/AppPage.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { ElMessage } from 'element-plus'
import { actionLabel, dateLabel, isActive, labels, deletePlanMessage } from './toolPlanDisplay'
import { workflowApi, type ToolKind, type ToolPlan, type ToolPlanItem } from '@/api/toolboxWorkflows'
const router = useRouter()
const route = useRoute()
const historyPanel = ref<HTMLDetailsElement | null>(null)
function showHistory() {
  const panel = historyPanel.value
  if (!panel) return
  panel.open = true
  panel.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
  panel.querySelector<HTMLElement>('summary')?.focus({ preventScroll: true })
}
onMounted(() => { if (historyPanel.value && router.currentRoute.value.hash === '#history') showHistory() })
const titles: Record<string, string> = { organize: '整理文件夹', rename: '批量修改文件名', album: '批量创建相册', cleanup: '照片清理', metadata: '拍摄信息修复', undo: '恢复原路径' }
const paths: Record<ToolKind, string> = { organize: '/toolbox/organize', rename: '/toolbox/rename', album: '/toolbox/albums', cleanup: '/toolbox/duplicate', metadata: '/toolbox/time-from-filename' }
const toolGroups = [
  { title: '照片清理', tools: [
    { path: '/toolbox/duplicate', title: '重复照片', icon: Copy },
    { path: '/toolbox/similar', title: '相似照片', icon: Images },
    { path: '/toolbox/cleanup', title: '低质量照片', icon: Trash2 },
  ] },
  { title: '照片整理', tools: [
    { path: '/toolbox/organize', title: '整理文件夹', icon: FolderOpen },
    { path: '/toolbox/rename', title: '批量修改文件名', icon: Tag },
    { path: '/toolbox/albums', title: '批量创建相册', icon: Images },
    { path: '/toolbox/time-from-filename', title: '修正拍摄信息', icon: Clock3 },
  ] },
]
const basename = (path: string) => path.split(/[\\/]/).at(-1) || path
const resetScroll = () => {
  if (typeof document === 'undefined') return
  document.querySelector('.ts-main-scroll')?.scrollTo({ top: 0, behavior: 'instant' })
}
onActivated(() => nextTick(resetScroll))
const historyPageSize = 10
const recordOpen = ref(false), record = ref<ToolPlan | null>(null)
const showDeleteRecord = ref(false), deletingRecord = ref(false)
const detailRows = ref<ToolPlanItem[]>([]), detailTotal = ref(0)
const detailLoading = ref(false), detailError = ref('')
const resultLabels: Record<string, string> = { ready: '未执行', candidate: '未执行', success: '已处理', skipped: '已跳过', failed: '处理失败' }
let detailVersion = 0
const loadDetails = async () => {
  if (!record.value || detailLoading.value) return
  const version = ++detailVersion
  detailLoading.value = true; detailError.value = ''
  try {
    const result = await workflowApi.items(record.value.id, detailRows.value.length)
    if (version !== detailVersion) return
    detailRows.value.push(...result.items)
    detailTotal.value = result.items.length ? result.total : detailRows.value.length
  } catch { if (version === detailVersion) detailError.value = '明细加载失败' }
  finally { if (version === detailVersion) detailLoading.value = false }
}
const viewRecord = (plan: ToolPlan) => {
  detailVersion++
  detailLoading.value = false
  record.value = plan; detailRows.value = []; detailTotal.value = 0
  recordOpen.value = true; loadDetails()
}
const historyOpen = ref(route.query.history === '1')
const history = ref<ToolPlan[]>([]), loading = ref(false), error = ref('')
const hasMoreHistory = ref(true)
let historyOffset = 0
let historyVersion = 0
const active = ref<ToolPlan[]>([])
const load = async () => {
  if (loading.value || !hasMoreHistory.value) return
  loading.value = true
  const version = historyVersion
  error.value = ''
  try {
    const records = await workflowApi.history(historyOffset, historyPageSize)
    if (version !== historyVersion) return
    historyOffset += records.length
    const known = new Set(history.value.map(plan => plan.id))
    history.value.push(...records.filter(plan => !known.has(plan.id)))
    hasMoreHistory.value = records.length === historyPageSize
  } catch {
    if (version === historyVersion) error.value = '操作记录加载失败，请重试。'
  } finally {
    if (version === historyVersion) loading.value = false
  }
}
const loadActive = async () => {
  try {
    const running = await workflowApi.history(0, 100, true)
    if (!disposed) active.value = running
  } catch {
    // Keep the last known tasks while polling retries.
  }
}
const open = (plan: ToolPlan) => {
  const kind = plan.kind === 'undo' ? plan.request.config.kind : plan.kind
  const cleanupPaths = { duplicate: '/toolbox/duplicate', similar: '/toolbox/similar', quality: '/toolbox/cleanup' }
  const path = kind === 'cleanup' ? cleanupPaths[plan.request.config.cleanup_mode] || paths.cleanup : paths[kind]
  router.push({ path, query: { plan: plan.id } })
}
const deleteRecord = async () => {
  const plan = record.value
  if (!plan || deletingRecord.value || isActive(plan)) return
  deletingRecord.value = true
  try {
    await workflowApi.deletePlan(plan.id)
    recordOpen.value = false
    historyVersion++
    historyOffset = 0
    history.value = []
    hasMoreHistory.value = true
    loading.value = false
    void load()
    ElMessage.success('计划已删除')
  } catch {
    // The request layer displays the server's reason.
  } finally {
    deletingRecord.value = false
  }
}
let timer: ReturnType<typeof setTimeout> | undefined, disposed = false
const poll = () => {
  timer = setTimeout(async () => {
    if (!disposed) await Promise.all([loadActive(), refreshHistory()])
    if (!disposed) poll()
  }, 4000)
}
const refreshHistory = async () => {
  if (!historyOpen.value || !historyOffset || loading.value) return
  const offset = historyOffset
  const version = historyVersion
  try {
    const latest = await workflowApi.history(0, historyPageSize)
    if (disposed || loading.value || offset !== historyOffset || version !== historyVersion) return
    const firstKnown = latest.findIndex(plan => plan.id === history.value[0]?.id)
    if (firstKnown < 0) return
    const latestIds = new Set(latest.map(plan => plan.id))
    history.value = [...latest, ...history.value.filter(plan => !latestIds.has(plan.id))]
    historyOffset += firstKnown
    if (firstKnown) hasMoreHistory.value = true
  } catch {
    // Keep the loaded history while polling retries.
  }
}
onMounted(async () => {
  void load()
  await loadActive()
  if (!disposed) poll()
})
onBeforeUnmount(() => { disposed = true; clearTimeout(timer) })
</script>
<style scoped>
.workbench-grid { display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0,1fr)); }
.workbench-tool { display: flex; align-items: center; flex-wrap: wrap; min-width: 0; gap: 12px; padding: 14px; border: 1px solid var(--ts-color-border); border-radius: 18px; background: var(--ts-journal-rail); transition: border-color 180ms ease, transform 180ms ease; }
.workbench-tool:hover { border-color: var(--ts-journal-focus); transform: translateY(-2px); }
.workbench-tool:focus-visible { outline: 2px solid var(--ts-journal-focus); outline-offset: 2px; }
.workbench-tool-icon { display: grid; place-items: center; width: 42px; height: 42px; border-radius: 50%; color: var(--ts-journal-accent-text); background: var(--ts-journal-active); }
.workbench-tool > :nth-child(2) { flex: 1 1 calc(100% - 60px); }
.workbench-tool > svg:last-child { align-self: center; margin-left: auto; }
#history { scroll-margin-top: 14px; }
@media (max-width: 860px) {
  .workbench-grid { grid-template-columns: minmax(0,1fr); }
  .workbench-tool { padding: 12px; }
  .workbench-tool-icon { flex-shrink: 0; }
  .workbench-tool > :nth-child(2) { flex: 1 1 auto; }
}
@media (prefers-reduced-motion: reduce) { .workbench-tool { transition: none; } }
</style>
