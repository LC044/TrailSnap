<template>
  <AppPage size="wide" bottom-safe class="py-5 md:py-8">
    <header class="mb-7 flex min-w-0 items-start justify-between gap-3">
      <h1 class="ts-page-title">工具箱</h1>
      <button class="ts-button ts-button-ghost" @click="historyOpen = !historyOpen">操作记录</button>
    </header>
    <section v-if="active.length" class="ts-surface mb-7 p-4 md:p-5" aria-label="正在进行">
      <h2 class="ts-section-title mb-3">正在进行</h2>
      <button v-for="plan in active" :key="plan.id" type="button" class="ts-divider flex w-full items-center justify-between gap-3 border-t py-3 text-left"
        @click="open(plan)">
        <span><span class="font-medium">{{ titles[plan.kind] }}</span><span class="ts-muted ml-2 text-sm">{{ plan.summary.total }} 项</span></span>
        <span class="text-sm text-primary-600 dark:text-primary-400">{{ plan.stop_requested ? '请求停止中' : labels[plan.status] }}<ChevronRight class="ml-1 inline h-4 w-4" /></span>
      </button>
    </section>
    <section class="grid gap-3 md:grid-cols-2" aria-label="照片工具">
      <RouterLink v-for="tool in [...otherTools, ...mainTools, { path: '/toolbox/albums', title: '批量创建相册', desc: '按日期、地点归类，不移动原文件', icon: Images }]" :key="tool.path" :to="tool.path" class="ts-surface flex min-w-0 items-center gap-4 p-4">
        <component :is="tool.icon" class="h-6 w-6 shrink-0 text-primary-500" />
        <div class="min-w-0 flex-1"><h2 class="font-semibold">{{ tool.title }}</h2><p class="ts-muted mt-1 text-sm">{{ 'note' in tool ? tool.note : tool.desc }}</p></div>
        <ChevronRight class="ts-muted h-5 w-5 shrink-0" />
      </RouterLink>
    </section>
    <details id="history" class="mt-7" :open="historyOpen || !!error">
      <summary id="history-heading" class="cursor-pointer py-3 font-semibold">操作记录</summary>
      <el-button :loading="loading" class="mb-3" @click="load">刷新记录</el-button>
      <p v-if="error" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <div v-else class="ts-surface overflow-hidden">
        <button v-for="plan in history" :key="plan.id" type="button" class="ts-divider flex w-full items-center gap-3 border-b p-4 text-left last:border-b-0 hover:bg-[var(--ts-color-surface-muted)]"
          @click="open(plan)">
          <Clock3 class="h-5 w-5 shrink-0 text-primary-500" /><span class="min-w-0 flex-1"><span class="block text-sm font-semibold">{{ titles[plan.kind] }} · {{ plan.summary.total }} 项</span>
            <span class="ts-muted text-xs">{{ dateLabel(plan.created_at) }} · {{ labels[plan.status] || plan.status }}<span v-if="plan.summary.failed"> · {{ plan.summary.failed }} 项失败</span></span></span><ChevronRight class="h-4 w-4 ts-muted" />
        </button>
        <p v-if="!history.length && !loading" class="ts-muted p-6 text-center text-sm">暂无操作记录</p>
      </div>
      <div v-if="page > 1 || history.length >= 20" class="mt-3 flex justify-center gap-2"><el-button :disabled="page === 1 || loading" @click="page--; load()">上一页</el-button><el-button :disabled="history.length < 20 || loading" @click="page++; load()">下一页</el-button></div>
    </details>
  </AppPage>
</template>
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { FolderOpen, Tag, Images, Copy, Trash2, Clock3, ChevronRight } from 'lucide-vue-next'
import AppPage from '@/components/ui/AppPage.vue'
import { workflowApi, type ToolKind, type ToolPlan } from '@/api/toolboxWorkflows'
const router = useRouter()
const titles: Record<string, string> = { organize: '整理文件夹', rename: '批量修改文件名', album: '批量创建相册', cleanup: '照片清理', metadata: '拍摄信息修复', undo: '恢复原路径' }
const paths: Record<ToolKind, string> = { organize: '/toolbox/organize', rename: '/toolbox/rename', album: '/toolbox/albums', cleanup: '/toolbox/duplicate', metadata: '/toolbox/time-from-filename' }
const labels: Record<string, string> = { queued: '排队中', running: '处理中', completed: '完成', partial: '部分失败', failed: '失败', stopped: '已停止' }
Object.assign(labels, { preview: '待核对', scan_queued: '等待扫描', scanning: '扫描中', scan_stopped: '扫描已停止', scan_failed: '扫描失败' })
const mainTools = [
  { path: '/toolbox/organize', title: '整理文件夹', desc: '只整理选中的影像，按日期、地点、人物或分类归档。', note: '移动或复制实际文件', icon: FolderOpen },
  { path: '/toolbox/rename', title: '批量修改文件名', desc: '统一照片文件名。', note: '仅修改原文件名', icon: Tag },
]
const otherTools = [
  { path: '/toolbox/duplicate', title: '重复照片', desc: '相同内容，手动确认保留', icon: Copy },
  { path: '/toolbox/similar', title: '相似照片', desc: '相近画面，先比较再清理', icon: Images },
  { path: '/toolbox/cleanup', title: '低质量照片', desc: '评分候选，不自动删除', icon: Trash2 },
  { path: '/toolbox/time-from-filename', title: '修正拍摄信息', desc: '选择范围，写入时间与设备', icon: Clock3 },
]
const historyOpen = ref(false)
const history = ref<ToolPlan[]>([]), page = ref(1), loading = ref(false), error = ref('')
const active = ref<ToolPlan[]>([])
let loadVersion = 0
const load = async () => {
  const version = ++loadVersion
  loading.value = true
  try {
    const [records, running] = await Promise.all([
      workflowApi.history((page.value - 1) * 20), workflowApi.history(0, 100, true),
    ])
    if (version !== loadVersion) return
    history.value = records; active.value = running; error.value = ''
  } catch { if (version === loadVersion) error.value = '操作记录加载失败，请重试。' }
  finally { if (version === loadVersion) loading.value = false }
}
const open = (plan: ToolPlan) => router.push({ path: paths[plan.kind === 'undo' ? plan.request.config.kind : plan.kind], query: { plan: plan.id } })
const dateLabel = (value: string) => new Date(value.endsWith('Z') ? value : value + 'Z').toLocaleString()
let timer: ReturnType<typeof setTimeout> | undefined, disposed = false
const poll = () => { timer = setTimeout(async () => { if (!disposed && active.value.length) await load(); if (!disposed) poll() }, 4000) }
onMounted(async () => { await load(); poll() })
onBeforeUnmount(() => { disposed = true; clearTimeout(timer) })
</script>
