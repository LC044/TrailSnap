<template>
  <AppPage size="content" bottom-safe class="toolbox-workflow py-5 md:py-8">
    <ScrollGlassHeader :enabled="kind === 'cleanup' && step < 3" class="journal-index-header mb-4 flex min-w-0 flex-wrap items-center justify-between gap-3" :class="kind === 'cleanup' && 'px-2 py-2'">
      <div class="flex min-w-0 items-start gap-3">
        <BackButton label="返回工具箱" @click="goBack" />
        <div class="min-w-0"><h1 class="ts-page-title">{{ kind === 'cleanup' ? ({ duplicate: '重复照片', similar: '相似照片', quality: '低质量照片' })[config.cleanup_mode] : titles[kind] }}</h1></div>
      </div>
      <div class="ml-auto flex flex-wrap gap-2">
        <el-button :disabled="busy || executing" @click="planListOpen = true">计划列表</el-button>
        <el-button v-if="plan" :disabled="busy || executing" @click="newPlan">新建计划</el-button>
      </div>
    </ScrollGlassHeader>
    <ol class="workflow-stages mb-4" aria-label="操作阶段">
      <li :aria-current="step < 3 ? 'step' : undefined">配置范围与规则</li>
      <li :aria-current="step === 3 ? 'step' : undefined">核对结果</li>
    </ol>
    <p v-if="error" role="alert" class="mb-4 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
    <div class="space-y-5">
      <div v-loading="busy || (checking && !scopeDialog)" :element-loading-text="checking ? '正在核对照片范围…' : '正在加载预览…'" :aria-busy="busy || checking" class="ts-surface min-w-0 p-4 md:p-6">
        <div v-if="step < 3" class="ts-divider mb-4 flex flex-wrap justify-end gap-2 border-b pb-4">
          <el-button :loading="checking" :disabled="!scopeValid || busy" @click="checkScope(true)">查看</el-button>
          <el-button type="primary" :loading="busy || checking" :disabled="!scopeValid || !configValid" @click="preview">{{ kind === 'cleanup' ? (forceCleanupScan ? '重新查找' : '查找') : '预览' }}</el-button>
        </div>
        <MediaScopeSelector v-if="step < 3" v-model:scope="scope" :count="scopeCount" :checking="checking" @check="checkScope(true)" />
        <div v-if="step < 3" class="ts-divider mt-6 space-y-5 border-t pt-6">
          <template v-if="['organize', 'rename', 'album'].includes(kind)">
            <OrganizeRuleEditor v-if="kind === 'organize' || kind === 'album'" v-model="config" :scope="scope" />
            <RenameTemplateEditor v-else v-model="config" />

          </template>
          <el-form v-else-if="kind === 'cleanup' && config.cleanup_mode !== 'duplicate'" label-position="top">
            <h2 class="ts-section-title mb-4">查找设置</h2>
            <el-form-item v-if="config.cleanup_mode === 'similar'" label="相似度阈值"><el-slider v-model="config.similarity" :min=".8" :max="1" :step=".01" show-input /></el-form-item>
            <el-form-item v-if="config.cleanup_mode === 'quality'" label="综合评分上限（0–200）"><el-input-number v-model="config.quality_max" :min="0" :max="200" /></el-form-item>
          </el-form>
          <el-form v-else-if="kind === 'metadata'" label-position="top">
            <h2 class="ts-section-title mb-4">修正拍摄信息</h2>
            <el-form-item label="时间处理"><el-select v-model="config.time_mode" class="w-full max-w-md">
              <el-option label="自动识别" value="auto" /><el-option label="指定时间" value="custom" /><el-option label="仅修改设备" value="none" />
            </el-select></el-form-item>
            <el-form-item v-if="config.time_mode === 'custom'" label="指定拍摄时间"><UnifiedDatePicker v-model="config.custom_time" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" class="w-full max-w-md" /></el-form-item>
            <el-form-item label="设备品牌"><el-input v-model="config.make" maxlength="100" placeholder="留空不修改" class="max-w-md" /></el-form-item>
            <el-form-item label="设备型号"><el-input v-model="config.model" maxlength="100" placeholder="留空不修改" class="max-w-md" /></el-form-item>
            <el-checkbox v-model="config.only_missing_metadata">仅处理缺少设备信息的照片</el-checkbox>
          </el-form>
        </div>
        <ToolPlanPreview v-else-if="plan" :plan="plan" :executing="executing" @execute="execute" @back="backToConfig" @rescan="editCleanupSearch(plan)"
          @stop="stop" @recover="recover" @again="again" />
      </div>

    </div>
    <ResponsiveDialog v-model="scopeDialog" title="选择的照片" max-width="60rem" mobile-mode="fullscreen" mobile-back>
      <div class="scope-actions sticky top-0 z-10 mb-4 flex flex-wrap justify-end gap-2 py-2">
        <el-button v-if="scope.excluded_ids.length" :disabled="checking" @click="scope.excluded_ids = []; checkScope(false)">恢复</el-button>
        <el-button type="primary" @click="scopeDialog = false">完成</el-button>
      </div>
      <p v-if="scopeError" role="alert" class="mb-3 text-sm text-red-600 dark:text-red-400">{{ scopeError }} <el-button @click="checkScope(false, scopeRows.length > 0 && scopeCount !== null)">重试</el-button></p>
      <p v-if="scopeCount !== null && !checking" class="ts-muted mb-4 text-sm" aria-live="polite">
        共 {{ scopeCount.toLocaleString() }} 张
      </p>
      <div v-loading="checking && !scopeRows.length" element-loading-text="正在加载照片…" :aria-busy="checking" class="grid min-h-32 grid-cols-2 gap-3 sm:grid-cols-4">
        <article v-for="photo in scopeRows" :key="photo.id" class="ts-divider min-w-0 rounded-xl border p-2">
          <ToolboxPhotoPreview :photo-id="photo.id" :alt="photo.filename" class="aspect-square w-full rounded-lg object-cover" />
          <p class="my-2 truncate text-xs" :title="photo.filename">{{ photo.filename }}</p>
          <el-button size="small" class="w-full" :disabled="checking" @click="exclude(photo.id)">排除</el-button>
        </article>
      </div>
      <p v-if="!scopeRows.length && !checking" class="ts-muted py-6 text-center">没有符合条件的影像</p>
      <p v-if="checking && scopeRows.length" role="status" class="ts-muted py-3 text-center text-sm">正在加载更多照片…</p>
      <AutoLoadSentinel v-if="scopeDialog && !checking && !scopeError && scopeRows.length < (scopeCount || 0)" @load="checkScope(false, true)" />
    </ResponsiveDialog>
    <ToolPlanList v-if="planListOpen" :filter="planFilter" @close="planListOpen = false"
      @open="openFromList" @deleted="refreshAfterDelete" />
  </AppPage>
</template>
<script setup lang="ts">
import AutoLoadSentinel from '@/components/ui/AutoLoadSentinel.vue'
import ToolboxPhotoPreview from './ToolboxPhotoPreview.vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppPage from '@/components/ui/AppPage.vue'
import BackButton from '@/components/ui/BackButton.vue'
import ScrollGlassHeader from '@/components/ui/ScrollGlassHeader.vue'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import UnifiedDatePicker from '@/components/ui/UnifiedDatePicker.vue'
import MediaScopeSelector from './MediaScopeSelector.vue'
import OrganizeRuleEditor from './OrganizeRuleEditor.vue'
import RenameTemplateEditor from './RenameTemplateEditor.vue'
import ToolPlanPreview from './ToolPlanPreview.vue'
import ToolPlanList from './ToolPlanList.vue'
import { defaultConfig, emptyScope, renameTemplateError, workflowApi, type PlanFilter, type ResumableCleanupMode, type ScopeItem, type ToolKind, type ToolPlan } from '@/api/toolboxWorkflows'
import { useUserStore } from '@/stores/user'
import { useAppBack } from '@/composables/useAppBack'
import { readToolboxScope } from '@/utils/toolboxEntry'
const props = defineProps<{ kind: ToolKind; cleanupMode?: 'duplicate' | 'similar' | 'quality' }>()
const route = useRoute(), router = useRouter()
const goBack = useAppBack('/toolbox')
const kind = computed(() => props.kind)
const planFilter = computed<PlanFilter>(() => ({ kind: kind.value, cleanup_mode: props.cleanupMode }))
const resumeMode = computed<ResumableCleanupMode | null>(() =>
  kind.value === 'cleanup' && (props.cleanupMode === 'duplicate' || props.cleanupMode === 'similar') ? props.cleanupMode : null)
const titles: Record<ToolKind, string> = { organize: '整理文件夹', rename: '批量修改文件名', album: '批量创建相册', cleanup: '照片清理', metadata: '修正拍摄信息' }
const user = useUserStore()
const initialConfig = () => {
  const value = defaultConfig(props.kind)
  if (props.cleanupMode) value.cleanup_mode = props.cleanupMode
  if (props.kind === 'organize' || props.kind === 'album') value.rules[0].granularity = 'month'
  return value
}
const scope = ref(emptyScope()), config = ref(initialConfig())
const step = ref(2), busy = ref(false), checking = ref(false), executing = ref(false), error = ref('')
const plan = ref<ToolPlan | null>(null)
const planListOpen = ref(false)
const forceCleanupScan = ref(false)
let workflowVersion = 0
const scopeCount = ref<number | null>(null), scopeRows = ref<ScopeItem[]>([]), scopeDialog = ref(false), scopeError = ref('')
const scopeValid = computed(() => {
  const s = scope.value
  return s.source === 'all' || (s.source === 'albums' && !!s.album_ids.length) || (s.source === 'folders' && !!s.folders.length)
    || (s.source === 'selected' && !!s.photo_ids.length) || (s.source === 'filter' && !!(s.start_date || s.end_date))
})
const configValid = computed(() => {
  const value = config.value
  if (value.kind === 'rename') return !renameTemplateError(value.template)
  if (value.kind === 'organize' && (!value.action || !value.target)) return false
  if (['organize', 'album'].includes(value.kind)) return value.rules.every(rule => rule.groups === null || rule.groups.length > 0)
  if (value.kind === 'metadata' && value.time_mode === 'custom') return !!value.custom_time
  if (value.kind === 'metadata' && value.time_mode === 'none') return !!(value.make || value.model)
  return true
})
const snapshot = () => JSON.stringify({ scope: scope.value, config: config.value })
watch(scope, () => { scopeCount.value = null; if (plan.value?.status === 'preview') plan.value = null }, { deep: true })
watch(config, () => { if (plan.value?.status === 'preview') plan.value = null }, { deep: true })
let scopeSequence = 0
const checkScope = async (open: boolean, append = false) => {
  if (!scopeValid.value || checking.value) return
  const version = ++scopeSequence
  const owner = user.userInfo?.id
  checking.value = true; scopeError.value = ''; error.value = ''
  if (!append) { scopeRows.value = []; scopeCount.value = null }
  const key = JSON.stringify(scope.value)
  try {
    const offset = append ? scopeRows.value.length : 0
    const result = await workflowApi.scope(scope.value, offset)
    if (version !== scopeSequence || owner !== user.userInfo?.id || key !== JSON.stringify(scope.value)) return
    scopeRows.value.push(...result.items)
    scopeCount.value = result.items.length ? result.total : offset
    if (open) scopeDialog.value = true
    return true
  } catch {
    if (version === scopeSequence) {
      const message = '范围核对失败，请检查选择并重试'
      if (scopeDialog.value) scopeError.value = message
      else error.value = message
    }
    return false
  }
  finally { if (version === scopeSequence) checking.value = false }
}
const exclude = async (id: string) => { scope.value.excluded_ids = [...new Set([...scope.value.excluded_ids, id])]; await checkScope(false) }
const preview = async () => {
  config.value.scan_mode = 'fast'
  config.value.compare_all = false
  if (busy.value || checking.value || !scopeValid.value || !configValid.value) return
  if (!await checkScope(false)) return
  if (!scopeCount.value) { ElMessage.warning('范围内没有影像，请调整条件'); return }
  busy.value = true; error.value = ''
  const version = workflowVersion
  const key = snapshot()
  const owner = user.userInfo?.id
  try {
    const result = await workflowApi.preview(scope.value, config.value, !!resumeMode.value && !forceCleanupScan.value)
    if (version !== workflowVersion || owner !== user.userInfo?.id || disposed) return
    if (key !== snapshot()) { ElMessage.info('配置已变化，请重新预览'); return }
    plan.value = result; step.value = 3; forceCleanupScan.value = false
    await router.replace({ query: { plan: result.id } })
    poll()
  } catch { if (version === workflowVersion) error.value = '预览失败，请检查规则、目标目录及页面提示后重试' }
  finally { if (version === workflowVersion) busy.value = false }
}
const execute = async (selected?: number[]) => {
  if (!plan.value || executing.value) return
  const id = plan.value.id, owner = user.userInfo?.id
  executing.value = true
  try {
    const result = await workflowApi.execute(plan.value, selected)
    if (owner !== user.userInfo?.id || plan.value?.id !== id || disposed) return
    plan.value = result
    ElMessage.success(kind.value === 'cleanup'
      ? '正在删除所选照片，完成后可继续选择删除' : '任务已接受，可以离开页面')
    await router.replace({ query: { plan: plan.value.id } })
    poll()
  } catch { error.value = '执行未确认成功，请刷新此计划核对状态，勿重复创建新计划' }
  finally { executing.value = false }
}
const backToConfig = async () => {
  workflowVersion++
  clearTimeout(pollTimer)
  plan.value = null
  step.value = 2
  await router.replace({ query: { new: '1' } })
}
const editCleanupSearch = (previous: ToolPlan) => {
  forceCleanupScan.value = true
  scope.value = JSON.parse(JSON.stringify(previous.request.scope))
  config.value = JSON.parse(JSON.stringify(previous.request.config))
  void backToConfig()
}
const stop = async () => {
  const id = plan.value?.id
  try {
    if (id) {
      const result = await workflowApi.stop(id)
      if (plan.value?.id === id && !disposed) plan.value = result
    }
  }
  catch { error.value = '停止请求未确认，请刷新任务状态后重试' }
}
const recover = async (mode: 'retry' | 'undo') => {
  if (!plan.value || busy.value) return
  const id = plan.value.id, owner = user.userInfo?.id
  busy.value = true
  try {
    const result = await workflowApi.recover(id, mode)
    if (owner !== user.userInfo?.id || plan.value?.id !== id || disposed) return
    plan.value = result; step.value = 3; await router.replace({ query: { plan: plan.value.id } })
  }
  catch { error.value = '无法生成恢复计划，请查看冲突或撤销窗口提示' }
  finally { busy.value = false }
}
const again = async () => {
  if (plan.value) config.value = JSON.parse(JSON.stringify(plan.value.request.config))
  scope.value = emptyScope()
  forceCleanupScan.value = false
  await backToConfig()
}
let pollTimer: ReturnType<typeof setTimeout> | undefined
let disposed = false
const poll = () => {
  clearTimeout(pollTimer)
  if (!plan.value || !['queued', 'running', 'scan_queued', 'scanning'].includes(plan.value.status) || disposed) return
  pollTimer = setTimeout(async () => {
    const id = plan.value?.id
    try {
      if (id) {
        const result = await workflowApi.plan(id)
        if (plan.value?.id === id && !disposed) {
          plan.value = result
          if (result.status === 'preview' && resumeMode.value) void checkFreshness(id)
        }
      }
    }
    catch { error.value = '任务状态暂不可用，正在重试' }
    poll()
  }, 2000)
}
const checkFreshness = async (id: string) => {
  const owner = user.userInfo?.id
  try {
    const result = await workflowApi.plan(id, true)
    if (!disposed && owner === user.userInfo?.id && plan.value?.id === id && plan.value.status === 'preview') {
      plan.value = { ...plan.value, cleanup_freshness: result.cleanup_freshness }
    }
  } catch {
    if (!disposed && owner === user.userInfo?.id && plan.value?.id === id && plan.value.status === 'preview') {
      plan.value = { ...plan.value, cleanup_freshness: 'unknown' }
    }
  }
}
const openPlan = async (id?: string) => {
  const owner = user.userInfo?.id, mode = resumeMode.value
  const version = ++workflowVersion
  const isCurrent = () => !disposed && version === workflowVersion && owner === user.userInfo?.id
  busy.value = true
  error.value = ''
  try {
    const loaded = id ? await workflowApi.plan(id) : (await workflowApi.history(0, 1, false, planFilter.value))[0]
    if (!isCurrent() || !loaded) return
    const loadedKind = loaded.kind === 'undo' ? loaded.request.config.kind : loaded.kind
    if (loadedKind !== kind.value || (mode && loaded.request.config.cleanup_mode !== mode)) throw new Error('计划类型不匹配')
    scope.value = loaded.request.scope; config.value = loaded.request.config
    await nextTick()
    if (!isCurrent()) return
    plan.value = loaded
    scopeCount.value = loaded.summary.total; step.value = 3
    forceCleanupScan.value = false
    if (route.query.plan !== loaded.id) await router.replace({ query: { plan: loaded.id } })
    poll()
    if (mode && loaded.status === 'preview') void checkFreshness(loaded.id)
  } catch {
    if (isCurrent()) error.value = id ? '无法读取这份计划，请从计划列表选择其他计划' : '无法读取上次结果，可从计划列表重试'
  } finally {
    if (isCurrent()) busy.value = false
  }
}
const openFromList = (id: string) => {
  planListOpen.value = false
  void openPlan(id)
}
const refreshAfterDelete = async (id: string) => {
  if (plan.value?.id !== id) return
  scope.value = emptyScope()
  config.value = initialConfig()
  const version = workflowVersion + 1
  await backToConfig()
  if (version === workflowVersion && !disposed) void openPlan()
}
const resetWorkflow = () => {
  workflowVersion++
  clearTimeout(pollTimer)
  scopeSequence++
  scope.value = emptyScope(); config.value = initialConfig()
  plan.value = null; scopeRows.value = []; scopeDialog.value = false
  planListOpen.value = false; forceCleanupScan.value = false
  step.value = 2; error.value = ''; checking.value = false; busy.value = false; executing.value = false
}
const newPlan = () => {
  resetWorkflow()
  void router.replace({ query: { new: '1' } })
}
const initialize = () => {
  if (typeof route.query.album === 'string') { scope.value.source = 'albums'; scope.value.album_ids = [route.query.album] }
  if (typeof route.query.context === 'string') {
    const selectedScope = readToolboxScope(route.query.context, user.userInfo?.id)
    if (selectedScope) scope.value = selectedScope
    else error.value = '原选择已失效，请重新选择范围'
  }
  if (typeof route.query.plan === 'string') void openPlan(route.query.plan)
  else if (!route.query.new && !route.query.album && !route.query.context) void openPlan()
}
watch([() => user.userInfo?.id, () => props.kind, () => props.cleanupMode], () => {
  resetWorkflow()
  initialize()
})
onMounted(initialize)
onBeforeUnmount(() => { disposed = true; clearTimeout(pollTimer) })
</script>

<style scoped>
.toolbox-workflow :deep(.el-button + .el-button) {
  margin-left: 0;
}
.scope-actions { background: var(--ts-color-surface); }
.workflow-stages { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 8px; }
.workflow-stages li { display: flex; gap: 9px; align-items: center; padding: 10px 12px; border: 1px solid var(--ts-color-border); border-radius: 10px; font-size: 13px; color: var(--ts-color-text-secondary); }
.workflow-stages li::before { content: ''; width: 7px; height: 7px; border: 1px solid currentColor; border-radius: 50%; }
.workflow-stages li[aria-current='step'] { color: var(--ts-color-text); background: var(--ts-journal-active); font-weight: 650; }
.workflow-stages li[aria-current='step']::before { background: var(--ts-journal-focus); border-color: var(--ts-journal-focus); }
</style>
