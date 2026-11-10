<template>
  <AppPage size="wide" bottom-safe class="py-5 md:py-8">
    <header class="mb-7 flex min-w-0 items-start justify-between gap-3">
      <div><span class="mb-3 inline-flex rounded-xl bg-primary-50 p-3 text-primary-600 dark:bg-primary-900/20 dark:text-primary-400"><Wrench class="h-6 w-6" /></span>
        <h1 class="ts-page-title md:text-3xl">工具箱</h1><p class="ts-muted mt-2 text-sm md:text-base">整理、命名与修复。先选范围，再放心操作。</p></div>
      <el-button :loading="loading" @click="load">刷新记录</el-button>
    </header>
    <section v-if="active.length" class="ts-surface mb-7 p-4 md:p-5" aria-label="正在进行">
      <h2 class="ts-section-title mb-3">正在进行</h2>
      <button v-for="plan in active" :key="plan.id" type="button" class="ts-divider flex w-full items-center justify-between gap-3 border-t py-3 text-left"
        @click="open(plan)">
        <span><span class="font-medium">{{ titles[plan.kind] }}</span><span class="ts-muted ml-2 text-sm">{{ plan.summary.total }} 项</span></span>
        <span class="text-sm text-primary-600 dark:text-primary-400">{{ plan.stop_requested ? '请求停止中' : labels[plan.status] }}<ChevronRight class="ml-1 inline h-4 w-4" /></span>
      </button>
    </section>
    <section aria-labelledby="organize-heading">
      <h2 id="organize-heading" class="ts-section-title mb-3">整理与命名</h2>
      <div class="grid gap-3 md:grid-cols-2 md:gap-5">
        <RouterLink v-for="tool in mainTools" :key="tool.path" :to="tool.path"
          class="ts-surface group flex min-h-[100px] items-center gap-4 p-4 transition hover:border-primary-500 focus-visible:outline-primary-500 md:min-h-[148px] md:p-6">
          <span class="rounded-xl bg-primary-50 p-3 text-primary-600 dark:bg-primary-900/20 dark:text-primary-400"><component :is="tool.icon" class="h-6 w-6" /></span>
          <div class="min-w-0 flex-1"><h3 class="text-base font-semibold md:text-lg">{{ tool.title }}</h3><p class="ts-muted mt-1 text-sm leading-6">{{ tool.desc }}</p>
            <p class="mt-2 text-xs text-primary-600 dark:text-primary-400">{{ tool.note }}</p></div>
          <ChevronRight class="h-5 w-5 shrink-0 ts-muted" />
        </RouterLink>
      </div>
      <RouterLink to="/toolbox/albums" class="ts-surface mt-3 flex items-center gap-3 p-4 hover:border-primary-500">
        <Images class="h-5 w-5 text-primary-500" /><span class="min-w-0 flex-1"><span class="block font-medium">按规则创建相册</span><span class="ts-muted text-sm">按年份、城市等组合分组，只整理应用内相册，不移动文件。</span></span><ChevronRight class="h-4 w-4 ts-muted" />
      </RouterLink>
    </section>
    <section class="mt-7" aria-labelledby="cleanup-heading">
      <h2 id="cleanup-heading" class="ts-section-title mb-3">清理与修复</h2>
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <RouterLink v-for="tool in otherTools" :key="tool.path" :to="tool.path" class="ts-surface flex min-w-0 items-center gap-3 p-4 hover:border-primary-500">
          <component :is="tool.icon" class="h-5 w-5 shrink-0 text-primary-500" />
          <div class="min-w-0"><h3 class="text-sm font-semibold">{{ tool.title }}</h3><p class="ts-muted mt-1 text-xs leading-5">{{ tool.desc }}</p></div>
        </RouterLink>
      </div>
    </section>
    <section class="mt-7" aria-labelledby="templates-heading">
      <div class="mb-3 flex items-center justify-between"><h2 id="templates-heading" class="ts-section-title">我的常用模板</h2><RouterLink to="/toolbox/rename" class="text-sm text-primary-600 dark:text-primary-400">编辑与管理</RouterLink></div>
      <p v-if="templateError" role="alert" class="text-sm text-red-600 dark:text-red-400">模板加载失败，请刷新后重试。</p>
      <div v-else-if="store.preferences.presets.length" class="grid gap-3 sm:grid-cols-3">
        <RouterLink v-for="preset in store.preferences.presets.slice(0, 3)" :key="preset.id" :to="{ path: paths[preset.config.kind], query: { preset: preset.id } }" class="ts-surface min-w-0 p-4">
          <p class="font-semibold">{{ preset.name }}</p><p class="ts-muted mt-2 truncate text-xs">{{ preset.config.kind === 'rename' ? preset.config.template : '复用归档规则，重新选择范围' }}</p>
        </RouterLink>
      </div>
      <p v-else class="ts-surface ts-muted p-4 text-sm">保存常用命名模板或整理方案，下次直接使用。规则会按账号保存。</p>
    </section>
    <section class="mt-7" aria-labelledby="history-heading">
      <h2 id="history-heading" class="ts-section-title mb-3">操作记录</h2>
      <p v-if="error" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <div v-else class="ts-surface overflow-hidden">
        <button v-for="plan in history" :key="plan.id" type="button" class="ts-divider flex w-full items-center gap-3 border-b p-4 text-left last:border-b-0 hover:bg-[var(--ts-color-surface-muted)]"
          @click="open(plan)">
          <Clock3 class="h-5 w-5 shrink-0 text-primary-500" /><span class="min-w-0 flex-1"><span class="block text-sm font-semibold">{{ titles[plan.kind] }} · {{ plan.summary.total }} 项</span>
            <span class="ts-muted text-xs">{{ dateLabel(plan.created_at) }} · {{ labels[plan.status] || plan.status }}<span v-if="plan.summary.failed"> · {{ plan.summary.failed }} 项失败</span></span></span><ChevronRight class="h-4 w-4 ts-muted" />
        </button>
        <p v-if="!history.length && !loading" class="ts-muted p-6 text-center text-sm">尚无新工具箱操作记录。预览不算已执行操作。</p>
      </div>
      <div class="mt-3 flex justify-center gap-2"><el-button :disabled="page === 1 || loading" @click="page--; load()">上一页</el-button><el-button :disabled="history.length < 20 || loading" @click="page++; load()">下一页</el-button></div>
    </section>
  </AppPage>
</template>
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Wrench, FolderOpen, Tag, Images, Copy, Trash2, Clock3, ChevronRight } from 'lucide-vue-next'
import AppPage from '@/components/ui/AppPage.vue'
import { workflowApi, type ToolKind, type ToolPlan } from '@/api/toolboxWorkflows'
import { useToolboxStore } from '@/stores/toolbox'
const router = useRouter(), store = useToolboxStore()
const titles: Record<string, string> = { organize: '影像整理', rename: '批量重命名', album: '相册归类', cleanup: '照片清理', metadata: '拍摄信息修复', undo: '恢复原路径' }
const paths: Record<ToolKind, string> = { organize: '/toolbox/organize', rename: '/toolbox/rename', album: '/toolbox/albums', cleanup: '/toolbox/duplicate', metadata: '/toolbox/time-from-filename' }
const labels: Record<string, string> = { queued: '排队中', running: '处理中', completed: '完成', partial: '部分失败', failed: '失败', stopped: '已停止' }
const mainTools = [
  { path: '/toolbox/organize', title: '影像整理', desc: '只整理选中的影像，按日期、地点、人物或分类归档。', note: '移动或复制实际文件', icon: FolderOpen },
  { path: '/toolbox/rename', title: '批量重命名', desc: '统一文件名，记住常用模板，执行前核对真实变化。', note: '仅修改原文件名', icon: Tag },
]
const otherTools = [
  { path: '/toolbox/duplicate', title: '重复照片', desc: '相同内容，手动确认保留', icon: Copy },
  { path: '/toolbox/similar', title: '相似照片', desc: '相近画面，先比较再清理', icon: Images },
  { path: '/toolbox/cleanup', title: '低质量照片', desc: '评分候选，不自动删除', icon: Trash2 },
  { path: '/toolbox/time-from-filename', title: '修正拍摄信息', desc: '选择范围，写入时间与设备', icon: Clock3 },
]
const history = ref<ToolPlan[]>([]), page = ref(1), loading = ref(false), error = ref(''), templateError = ref(false)
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
  } catch { if (version === loadVersion) error.value = '操作记录加载失败；请确认已执行本次数据库迁移后重试。' }
  finally { if (version === loadVersion) loading.value = false }
}
const open = (plan: ToolPlan) => router.push({ path: paths[plan.kind === 'undo' ? plan.request.config.kind : plan.kind], query: { plan: plan.id } })
const dateLabel = (value: string) => new Date(value.endsWith('Z') ? value : value + 'Z').toLocaleString()
let timer: ReturnType<typeof setTimeout> | undefined, disposed = false
const poll = () => { timer = setTimeout(async () => { if (!disposed && active.value.length) await load(); if (!disposed) poll() }, 4000) }
onMounted(async () => { await load(); try { await store.load() } catch { templateError.value = true } poll() })
onBeforeUnmount(() => { disposed = true; clearTimeout(timer) })
</script>
