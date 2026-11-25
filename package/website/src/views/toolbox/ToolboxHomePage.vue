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
    <section class="workbench-grid" aria-label="照片工具">
      <RouterLink v-for="tool in [...otherTools, ...mainTools, { path: '/toolbox/albums', title: '批量创建相册', icon: Images }]" :key="tool.path" :to="tool.path" class="workbench-tool">
        <span class="workbench-tool-icon"><component :is="tool.icon" class="h-6 w-6" /></span>
        <h2 class="min-w-0 flex-1 font-semibold">{{ tool.title }}</h2>
        <ChevronRight class="ts-muted h-5 w-5 shrink-0" />
      </RouterLink>
    </section>
    <details id="history" ref="historyPanel" class="mt-7" :open="historyOpen || !!error" @toggle="historyOpen = ($event.target as HTMLDetailsElement).open">
      <summary id="history-heading" class="cursor-pointer py-3 font-semibold">操作记录</summary>
      <p v-if="error" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <div v-else class="ts-surface overflow-hidden">
        <button v-for="plan in history" :key="plan.id" type="button" class="ts-divider flex w-full items-center gap-3 border-b p-4 text-left last:border-b-0" @click="viewRecord(plan)">
          <Clock3 class="h-5 w-5 shrink-0 text-primary-500" />
          <div class="min-w-0 flex-1">
            <p class="text-sm font-semibold">{{ titles[plan.kind] }}</p>
            <time class="ts-muted text-xs">{{ dateLabel(plan.created_at) }}</time>
          </div><ChevronRight class="ts-muted h-4 w-4" />
        </button>
        <p v-if="!history.length && !loading" class="ts-muted p-6 text-center text-sm">暂无操作记录</p>
      </div>
      <div v-if="page > 1 || history.length >= historyPageSize" class="mt-3 flex justify-center gap-2"><el-button aria-label="上一页" :disabled="page === 1 || loading" @click="page--; load()"><ChevronLeft class="h-4 w-4" /></el-button><el-button aria-label="下一页" :disabled="history.length < historyPageSize || loading" @click="page++; load()"><ChevronRight class="h-4 w-4" /></el-button></div>
    </details>
    <ResponsiveDialog v-model="recordOpen" title="操作详情" mobile-mode="fullscreen" mobile-back>
      <template v-if="record">
        <p class="font-medium">{{ titles[record.kind] }}</p>
        <p class="ts-muted mt-1 text-sm">{{ dateLabel(record.created_at) }}</p>
        <p class="my-4 text-sm">处理 {{ record.summary.success || 0 }} 项 · 跳过 {{ record.summary.skipped || 0 }} 项 · 失败 {{ record.summary.failed || 0 }} 项</p>
        <p v-if="detailError" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ detailError }} <el-button @click="loadDetails">重试</el-button></p>
        <div ref="detailList" v-loading="detailLoading" class="space-y-3">
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
          <p v-if="!detailRows.length && !detailLoading" class="ts-muted py-4 text-sm">暂无明细</p>
        </div>

      </template>
      <template #footer>
        <div class="flex items-center justify-center gap-4">
          <el-button aria-label="上一页" :disabled="detailPage <= 1 || detailLoading" @click="detailPage--; loadDetails()"><ChevronLeft class="h-4 w-4" /></el-button>
          <span class="ts-muted text-sm">{{ detailPage }} / {{ Math.max(1, Math.ceil(detailTotal / detailPageSize)) }}</span>
          <el-button aria-label="下一页" :disabled="detailPage * detailPageSize >= detailTotal || detailLoading" @click="detailPage++; loadDetails()"><ChevronRight class="h-4 w-4" /></el-button>
        </div>
      </template>
    </ResponsiveDialog>
  </AppPage>
</template>
<script setup lang="ts">
import ToolboxPhotoPreview from './ToolboxPhotoPreview.vue'
import { computed, nextTick, onBeforeUnmount, onActivated, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { FolderOpen, Tag, Images, Copy, Trash2, Clock3, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import AppPage from '@/components/ui/AppPage.vue'
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
const labels: Record<string, string> = { queued: '排队中', running: '处理中', completed: '完成', partial: '部分失败', failed: '失败', stopped: '已停止' }
Object.assign(labels, { preview: '待确认', scan_queued: '等待扫描', scanning: '扫描中', scan_stopped: '扫描已停止', scan_failed: '扫描失败' })
const mainTools = [
  { path: '/toolbox/organize', title: '整理文件夹', icon: FolderOpen },
  { path: '/toolbox/rename', title: '批量修改文件名', icon: Tag },
]
const otherTools = [
  { path: '/toolbox/duplicate', title: '重复照片', icon: Copy },
  { path: '/toolbox/similar', title: '相似照片', icon: Images },
  { path: '/toolbox/cleanup', title: '低质量照片', icon: Trash2 },
  { path: '/toolbox/time-from-filename', title: '修正拍摄信息', icon: Clock3 },
]
const compactDetails = ref(typeof window !== 'undefined' && window.innerWidth < 768)
const detailPageSize = computed(() => compactDetails.value ? 10 : 20)
const detailList = ref<HTMLElement>()
const basename = (path: string) => path.split(/[\\/]/).at(-1) || path
const resetScroll = () => {
  if (typeof document === 'undefined') return
  document.querySelector('.ts-main-scroll')?.scrollTo({ top: 0, behavior: 'instant' })
}
onActivated(() => nextTick(resetScroll))
const historyPageSize = 10
const recordOpen = ref(false), record = ref<ToolPlan | null>(null)
const detailRows = ref<ToolPlanItem[]>([]), detailPage = ref(1), detailTotal = ref(0)
const detailLoading = ref(false), detailError = ref('')
const resultLabels: Record<string, string> = { ready: '未执行', candidate: '未执行', success: '已处理', skipped: '已跳过', failed: '处理失败' }
let detailVersion = 0
const loadDetails = async () => {
  if (!record.value) return
  const version = ++detailVersion
  detailLoading.value = true; detailError.value = ''
  try {
    const result = await workflowApi.items(record.value.id, (detailPage.value - 1) * detailPageSize.value)
    if (version !== detailVersion) return
    detailRows.value = result.items.slice(0, detailPageSize.value); detailTotal.value = result.total
    await nextTick()
    detailList.value?.closest('.responsive-dialog-body')?.scrollTo({ top: 0 })
  } catch { if (version === detailVersion) detailError.value = '明细加载失败' }
  finally { if (version === detailVersion) detailLoading.value = false }
}
const viewRecord = (plan: ToolPlan) => {
  compactDetails.value = typeof window !== 'undefined' && window.innerWidth < 768
  record.value = plan; detailPage.value = 1; detailRows.value = []; detailTotal.value = 0
  recordOpen.value = true; loadDetails()
}
const historyOpen = ref(route.query.history === '1')
const history = ref<ToolPlan[]>([]), page = ref(1), loading = ref(false), error = ref('')
const active = ref<ToolPlan[]>([])
let loadVersion = 0
const load = async () => {
  const version = ++loadVersion
  loading.value = true
  try {
    const [records, running] = await Promise.all([
      workflowApi.history((page.value - 1) * historyPageSize, historyPageSize), workflowApi.history(0, 100, true),
    ])
    if (version !== loadVersion) return
    history.value = records; active.value = running; error.value = ''
  } catch { if (version === loadVersion) error.value = '操作记录加载失败，请重试。' }
  finally { if (version === loadVersion) loading.value = false }
}
watch(historyOpen, value => { if (value) load() })
const open = (plan: ToolPlan) => {
  const kind = plan.kind === 'undo' ? plan.request.config.kind : plan.kind
  const cleanupPaths = { duplicate: '/toolbox/duplicate', similar: '/toolbox/similar', quality: '/toolbox/cleanup' }
  const path = kind === 'cleanup' ? cleanupPaths[plan.request.config.cleanup_mode] || paths.cleanup : paths[kind]
  router.push({ path, query: { plan: plan.id } })
}
const dateLabel = (value: string) => new Date(value.endsWith('Z') ? value : value + 'Z').toLocaleString()
let timer: ReturnType<typeof setTimeout> | undefined, disposed = false
const poll = () => { timer = setTimeout(async () => { if (!disposed && !loading.value && (active.value.length || historyOpen.value)) await load(); if (!disposed) poll() }, 4000) }
onMounted(async () => {
  await load(); poll()
  await nextTick()
  resetScroll()
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
