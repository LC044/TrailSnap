<template>
  <AppPage size="content" bottom-safe class="toolbox-workflow py-5 md:py-8">
    <header class="journal-index-header mb-4 flex min-w-0 items-center justify-between gap-3">
      <div class="flex min-w-0 items-start gap-3">
        <BackButton label="返回工具箱" @click="goBack" />
        <div class="min-w-0"><h1 class="ts-page-title">{{ kind === 'cleanup' ? ({ duplicate: '重复照片', similar: '相似照片', quality: '低质量照片' })[config.cleanup_mode] : titles[kind] }}</h1></div>
      </div>
    </header>
    <ol class="workflow-stages mb-4" aria-label="操作阶段">
      <li :aria-current="step < 3 ? 'step' : undefined">配置范围与规则</li>
      <li :aria-current="step === 3 ? 'step' : undefined">核对结果</li>
    </ol>
    <p v-if="error" role="alert" class="mb-4 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
    <div class="space-y-5">
      <div v-loading="busy" class="ts-surface min-w-0 p-4 md:p-6">
        <MediaScopeSelector v-if="step < 3" v-model:scope="scope" :count="scopeCount" :checking="checking" @check="checkScope(true)" />
        <div v-if="step < 3" class="ts-divider mt-6 space-y-5 border-t pt-6">
          <template v-if="['organize', 'rename', 'album'].includes(kind)">
            <OrganizeRuleEditor v-if="kind === 'organize' || kind === 'album'" v-model="config" :scope="scope" />
            <RenameTemplateEditor v-else v-model="config" />

          </template>
          <el-form v-else-if="kind === 'cleanup' && config.cleanup_mode !== 'duplicate'" label-position="top">
            <h2 class="ts-section-title mb-4">查找设置</h2>
            <el-form-item v-if="config.cleanup_mode === 'similar'" label="相似度阈值"><el-slider v-model="config.similarity" :min=".8" :max="1" :step=".01" show-input /></el-form-item>
            <el-form-item v-if="config.cleanup_mode === 'quality'" label="评分上限"><el-input-number v-model="config.quality_max" :min="0" :max="200" /></el-form-item>
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
        <ToolPlanPreview v-else-if="plan" :plan="plan" :executing="executing" @execute="execute" @back="backToConfig"
          @stop="stop" @recover="recover" @again="again" />
        <div v-if="step < 3" class="ts-divider mt-6 flex justify-end gap-2 border-t pt-4">
          <el-button :loading="checking" :disabled="!scopeValid || busy" @click="checkScope(true)">查看</el-button>
          <el-button type="primary" :loading="busy || checking" :disabled="!scopeValid || !configValid" @click="preview">{{ kind === 'cleanup' ? '查找' : '预览' }}</el-button>
        </div>
      </div>

    </div>
    <ResponsiveDialog v-model="scopeDialog" title="选择的照片" max-width="60rem" mobile-mode="fullscreen" mobile-back>
      <p class="ts-muted mb-4 text-sm" aria-live="polite">
        <template v-if="scopeCount === null || checking">加载中…</template>
        <template v-else>共 {{ scopeCount.toLocaleString() }} 张</template>
      </p>
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <article v-for="photo in scopeRows" :key="photo.id" class="ts-divider min-w-0 rounded-xl border p-2">
          <img :src="thumbnailUrl(photo.id)" :alt="photo.filename" loading="lazy" class="aspect-square w-full rounded-lg object-cover" />
          <p class="my-2 truncate text-xs" :title="photo.filename">{{ photo.filename }}</p>
          <el-button size="small" class="w-full" @click="exclude(photo.id)">排除</el-button>
        </article>
      </div>
      <p v-if="!scopeRows.length" class="ts-muted py-6 text-center">没有符合条件的影像</p>
      <div class="mt-4 flex justify-center"><el-pagination v-model:current-page="scopePage" :page-size="40" :total="scopeCount || 0" layout="prev, pager, next" :pager-count="5" @current-change="checkScope(false)" /></div>
      <template #footer><div class="flex justify-end gap-2"><el-button v-if="scope.excluded_ids.length" @click="scope.excluded_ids = []; checkScope(false)">恢复</el-button><el-button type="primary" @click="scopeDialog = false">完成</el-button></div></template>
    </ResponsiveDialog>
  </AppPage>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppPage from '@/components/ui/AppPage.vue'
import BackButton from '@/components/ui/BackButton.vue'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import UnifiedDatePicker from '@/components/ui/UnifiedDatePicker.vue'
import MediaScopeSelector from './MediaScopeSelector.vue'
import OrganizeRuleEditor from './OrganizeRuleEditor.vue'
import RenameTemplateEditor from './RenameTemplateEditor.vue'
import ToolPlanPreview from './ToolPlanPreview.vue'
import { defaultConfig, emptyScope, renameTemplateError, workflowApi, type ScopeItem, type ToolKind, type ToolPlan } from '@/api/toolboxWorkflows'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { useUserStore } from '@/stores/user'
import { useAppBack } from '@/composables/useAppBack'
const props = defineProps<{ kind: ToolKind; cleanupMode?: 'duplicate' | 'similar' | 'quality' }>()
const route = useRoute(), router = useRouter()
const goBack = useAppBack('/toolbox')
const kind = computed(() => props.kind)
const titles: Record<ToolKind, string> = { organize: '整理文件夹', rename: '批量修改文件名', album: '批量创建相册', cleanup: '照片清理', metadata: '修正拍摄信息' }
const user = useUserStore()
const scope = ref(emptyScope()), config = ref(defaultConfig(props.kind))
if (props.cleanupMode) config.value.cleanup_mode = props.cleanupMode
if (props.kind === 'organize' || props.kind === 'album') config.value.rules[0].granularity = 'month'
const step = ref(2), busy = ref(false), checking = ref(false), executing = ref(false), error = ref('')
const plan = ref<ToolPlan | null>(null)
const scopeCount = ref<number | null>(null), scopeRows = ref<ScopeItem[]>([]), scopePage = ref(1), scopeDialog = ref(false)
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
const checkScope = async (open: boolean) => {
  if (!scopeValid.value) return
  const version = ++scopeSequence
  const owner = user.userInfo?.id
  checking.value = true; error.value = ''
  const key = JSON.stringify(scope.value)
  try {
    if (open) scopePage.value = 1
    const result = await workflowApi.scope(scope.value, (scopePage.value - 1) * 40)
    if (version !== scopeSequence || owner !== user.userInfo?.id || key !== JSON.stringify(scope.value)) return
    scopeCount.value = result.total; scopeRows.value = result.items
    if (open) scopeDialog.value = true
    return true
  } catch { if (version === scopeSequence) error.value = '范围核对失败，请检查选择并重试'; return false }
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
  const key = snapshot()
  const owner = user.userInfo?.id
  try {
    const result = await workflowApi.preview(scope.value, config.value)
    if (owner !== user.userInfo?.id) return
    if (key !== snapshot()) { ElMessage.info('配置已变化，请重新预览'); return }
    plan.value = result; step.value = 3
    if (kind.value === 'cleanup') { await router.replace({ query: { plan: result.id } }); poll() }
  } catch { error.value = '预览失败，请检查规则、目标目录及页面提示后重试' }
  finally { busy.value = false }
}
const execute = async (selected?: number[]) => {
  if (!plan.value || executing.value) return
  const id = plan.value.id, owner = user.userInfo?.id
  executing.value = true
  try {
    const result = await workflowApi.execute(plan.value, selected)
    if (owner !== user.userInfo?.id || plan.value?.id !== id || disposed) return
    plan.value = result
    ElMessage.success('任务已接受，可以离开页面')
    await router.replace({ query: { plan: plan.value.id } })
    poll()
  } catch { error.value = '执行未确认成功，请刷新此计划核对状态，勿重复创建新计划' }
  finally { executing.value = false }
}
const backToConfig = () => { plan.value = null; step.value = 2 }
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
  plan.value = null; scope.value = emptyScope(); step.value = 2; await router.replace({ query: {} })
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
        if (plan.value?.id === id && !disposed) plan.value = result
      }
    }
    catch { error.value = '任务状态暂不可用，正在重试' }
    poll()
  }, 2000)
}
watch(() => user.userInfo?.id, () => {
  clearTimeout(pollTimer)
  scopeSequence++
  scope.value = emptyScope(); config.value = defaultConfig(props.kind)
  plan.value = null; scopeRows.value = []; scopeDialog.value = false
  step.value = 2; error.value = ''; checking.value = false
})
onMounted(async () => {
  if (typeof route.query.album === 'string') { scope.value.source = 'albums'; scope.value.album_ids = [route.query.album] }
  if (typeof route.query.context === 'string') {
    try {
      const value = JSON.parse(sessionStorage.getItem(`trailsnap:toolbox:context:${route.query.context}`) || '{}')
      if (value.owner === user.userInfo?.id && Date.now() - value.created < 900000) scope.value = value.scope
    } catch { error.value = '原选择已失效，请重新选择范围' }
  }
  if (typeof route.query.plan === 'string') {
    const owner = user.userInfo?.id
    busy.value = true
    try {
      const loaded = await workflowApi.plan(route.query.plan)
      if (owner !== user.userInfo?.id || disposed) return
      scope.value = loaded.request.scope; config.value = loaded.request.config
      await nextTick()
      plan.value = loaded
      scopeCount.value = loaded.summary.total; step.value = 3; poll()
    } catch { error.value = '无法读取该操作记录，请返回工具箱重试' }
    finally { busy.value = false }
  }
})
onBeforeUnmount(() => { disposed = true; clearTimeout(pollTimer) })
</script>

<style scoped>
.toolbox-workflow :deep(.el-button + .el-button) {
  margin-left: 0;
}
.workflow-stages { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 8px; }
.workflow-stages li { display: flex; gap: 9px; align-items: center; padding: 10px 12px; border: 1px solid var(--ts-color-border); border-radius: 10px; font-size: 13px; color: var(--ts-color-text-secondary); }
.workflow-stages li::before { content: ''; width: 7px; height: 7px; border: 1px solid currentColor; border-radius: 50%; }
.workflow-stages li[aria-current='step'] { color: var(--ts-color-text); background: var(--ts-journal-active); font-weight: 650; }
.workflow-stages li[aria-current='step']::before { background: var(--ts-journal-focus); border-color: var(--ts-journal-focus); }
</style>
