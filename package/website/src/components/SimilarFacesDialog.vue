<template>
  <ResponsiveDialog :model-value="visible" title="查找相似人脸" description="以选中的这张脸查找，确认后批量更正"
    max-width="60rem" mobile-mode="fullscreen" mobile-back history :glass="false"
    :before-close="beforeClose" @update:model-value="emit('update:visible', $event)">
    <div class="space-y-4">
      <section class="ts-surface flex items-center gap-3 p-3">
        <button v-if="reference" type="button" class="sample-face relative shrink-0 rounded-xl ts-focus-ring"
          :aria-pressed="isSelected(reference)" aria-label="选择或取消当前样本人脸"
          :disabled="submitting || !canSelect(reference)" @click="toggle(reference)">
          <FaceThumbnail :face="reference" class="h-16 w-16 rounded-xl" alt="查找样本人脸" />
          <span class="face-check" :class="{ checked: isSelected(reference) }"><Check v-if="isSelected(reference)" class="h-3 w-3" /></span>
        </button>
        <FaceThumbnail v-else :face="props.reference" class="h-16 w-16 shrink-0 rounded-xl" alt="查找样本人脸" />
        <div class="min-w-0 flex-1">
          <p class="text-sm font-semibold">以这张脸查找</p>
          <p class="ts-muted mt-1 truncate text-xs">当前：{{ (reference ? reference.identity_name : props.reference.identity_name) || '未标记' }}</p>
          <p v-if="reference" class="ts-muted mt-1 text-xs">{{ lowSimilarity ? '仅作查找参照，不参与本次更正' : isSelected(reference) ? '已包含当前人脸' : '未选择当前人脸' }}</p>
        </div>
      </section>

      <div class="grid gap-3 sm:grid-cols-2">
        <label class="min-w-0 space-y-1 text-xs"><span class="ts-muted">更正方式</span>
          <el-select v-model="assignmentMode" aria-label="更正方式" :disabled="submitting" class="w-full">
            <el-option label="移到其他人物" value="person" />
            <el-option label="释放为未标记人脸" value="unassigned" />
          </el-select>
        </label>
        <label v-if="assignmentMode === 'person'" class="min-w-0 space-y-1 text-xs"><span class="ts-muted">更正为</span>
          <button type="button" class="ts-button ts-button-secondary w-full min-w-0 justify-between"
            :disabled="submitting" @click="selectorVisible = true">
            <span class="truncate">{{ target?.identity_name || '选择正确人物' }}</span><ChevronDown class="h-4 w-4 shrink-0" />
          </button>
        </label>
      </div>
      <p v-if="assignmentMode === 'unassigned'" class="ts-muted text-xs">仅解除选中人脸的人物归属，不删除照片或人脸；以后可重新标记或识别。</p>
      <div class="scope-filters grid grid-cols-2 gap-3">
        <label class="min-w-0 space-y-1 text-xs"><span class="ts-muted">查找范围</span>
          <el-select v-model="scope" aria-label="查找范围" :disabled="submitting" class="w-full">
            <el-option label="全部人物" value="all" />
            <el-option label="当前人物" value="current" />
            <el-option label="当前人物 · 低相似" value="current_low" :disabled="!(reference ? reference.identity_id : props.reference.identity_id)" />
            <el-option label="非当前人物" value="other" />
            <el-option label="未标记" value="unassigned" />
          </el-select>
        </label>
        <label class="min-w-0 space-y-1 text-xs"><span class="ts-muted">{{ lowSimilarity ? '排查范围' : '匹配范围' }}</span>
          <el-select v-model="match" :aria-label="lowSimilarity ? '排查范围' : '匹配范围'" :disabled="submitting" class="w-full">
            <el-option :label="lowSimilarity ? '差异明显' : '更相似'" value="strict" />
            <el-option :label="lowSimilarity ? '较低相似' : '较相似'" value="balanced" />
            <el-option :label="lowSimilarity ? '扩大排查' : '扩大查找'" value="broad" />
          </el-select>
        </label>
      </div>
      <p v-if="lowSimilarity" class="ts-muted text-xs">只排查样本所属人物，差异最大的人脸优先显示。角度、年龄、光线也会影响相似度，请核对头像和原图后再更正。</p>
      <el-checkbox v-if="target && assignmentMode === 'person'" v-model="hideAssigned" :disabled="submitting">隐藏已属于“{{ target.identity_name }}”的人脸</el-checkbox>

      <div v-if="successMessage" class="ts-surface p-3" role="status">
        <p class="text-sm font-medium">{{ successMessage }}</p>
        <button v-if="undoToken" type="button" class="ts-button ts-button-ghost mt-1 text-primary-600"
          :disabled="submitting" @click="undo">撤销本次更正</button>
        <p v-if="undoToken" class="ts-muted mt-1 text-xs">15 分钟内可撤销；关闭此窗口后不再保留撤销入口。</p>
      </div>
      <p v-if="actionError" class="ts-surface p-3 text-sm" role="alert">{{ actionError }}</p>

      <div class="ts-divider flex flex-wrap items-center gap-2 border-b pb-2">
        <p class="ts-muted min-w-0 flex-1 text-xs" aria-live="polite">
          {{ showSelected ? `已选 ${selectedCount} 张人脸` : `找到 ${faceCount} 张${lowSimilarity ? '低相似' : '相似'}人脸，来自 ${photoCount} 张照片` }}
        </p>
        <button type="button" class="ts-button ts-button-ghost ts-button-sm" :aria-pressed="showSelected"
          :disabled="submitting" @click="showSelected = !showSelected">{{ showSelected ? '返回结果' : `查看已选 (${selectedCount})` }}</button>
      </div>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="ts-button ts-button-secondary ts-button-sm"
          :disabled="loading || submitting || showSelected || !visibleItems.length" @click="selectPage">
          {{ isMobile ? '选择本批' : '选择本页' }}
        </button>
        <button type="button" class="ts-button ts-button-ghost ts-button-sm"
          :disabled="submitting || !selectedCount" @click="clearSelection">取消选择</button>
      </div>

      <div v-if="loadError && !showSelected" class="ts-surface space-y-3 p-6 text-center" role="alert">
        <p class="text-sm">{{ loadError }}</p>
        <button type="button" class="ts-button ts-button-secondary" :disabled="loading || submitting" @click="load()">重新查找</button>
      </div>
      <div v-else-if="loading && !appending && !showSelected" class="face-grid" role="status" aria-label="正在查找相似人脸">
        <div v-for="n in 12" :key="n" class="face-skeleton aspect-square animate-pulse rounded-xl" />
      </div>
      <div v-else-if="!visibleItems.length" class="ts-muted py-12 text-center text-sm" role="status">
        {{ showSelected ? '还没有选择人脸' : lowSimilarity ? '没有找到低相似人脸，可以扩大排查范围再试试' : '没有找到相似人脸，可以扩大查找范围再试试' }}
      </div>
      <div v-else class="face-grid">
        <article v-for="item in visibleItems" :key="item.id" class="candidate-card"
          :class="{ 'candidate-selected': isSelected(item) }">
          <button type="button" class="relative block w-full text-left ts-focus-ring rounded-t-xl"
            :aria-label="`${item.identity_name || '未标记'}，${dateLabel(item.photo_time)}，选择人脸`"
            :aria-pressed="isSelected(item)" :disabled="submitting || !canSelect(item)" @click="toggle(item)">
            <FaceThumbnail :face="item" class="aspect-square w-full rounded-t-xl" :alt="item.identity_name || '未标记的人脸'" />
            <span class="face-check" :class="{ checked: isSelected(item) }"><Check v-if="isSelected(item)" class="h-3 w-3" /></span>
          </button>
          <div class="space-y-1 px-2 pt-2">
            <p class="truncate text-xs font-medium" :title="item.identity_name || '未标记'">当前：{{ item.identity_name || '未标记' }}</p>
            <p class="ts-muted text-xs">{{ dateLabel(item.photo_time) }}</p>
            <p v-if="lowSimilarity" class="ts-muted text-xs">相似度 {{ Math.round(item.similarity * 100) }}% · 待核对</p>
            <p v-if="item.manually_confirmed" class="text-xs text-amber-700 dark:text-amber-400">人工确认</p>
            <p v-else-if="assignmentMode === 'person' && item.identity_id === target?.id" class="ts-muted text-xs">已属于目标人物</p>
            <p v-else-if="!lowSimilarity" class="ts-muted text-xs">{{ item.similarity >= .65 ? '更相似' : '待确认' }}</p>
          </div>
          <button type="button" class="ts-button ts-button-ghost ts-button-sm w-full text-xs"
            :disabled="submitting" @click="preview = item"><Expand class="h-3.5 w-3.5" />查看原图</button>
        </article>
      </div>

      <div v-if="!showSelected && (!loading || appending) && !loadError" class="flex items-center justify-center gap-3">
        <button v-if="!isMobile && page > 0" type="button" class="ts-button ts-button-secondary"
          :disabled="submitting" @click="load(page - 1)">上一页</button>
        <span v-if="!isMobile && faceCount > 60" class="ts-muted text-xs">第 {{ page + 1 }} 页</span>
        <button v-if="hasMore" ref="loadMoreButton" type="button" class="ts-button ts-button-secondary"
          :disabled="submitting || loading" @click="load(page + 1, isMobile)">{{ loading ? '正在加载…' : isMobile ? '加载更多' : '下一页' }}</button>
      </div>
    </div>
    <template #footer>
      <div class="flex flex-wrap items-center gap-3">
        <div class="min-w-0 flex-1">
          <p class="text-sm font-semibold">已选 {{ selectedCount }} 张人脸</p>
          <p class="ts-muted mt-1 text-xs">仅修改人脸归属，不影响照片中的其他人</p>
        </div>
        <button type="button" class="ts-button ts-button-primary" :disabled="!canSubmit" @click="confirmVisible = true">
          {{ submitting ? '正在保存…' : `${assignmentMode === 'unassigned' ? '释放' : '更正'} ${selectedCount} 张人脸` }}
        </button>
      </div>
    </template>
  </ResponsiveDialog>

  <PersonSelector v-model:visible="selectorVisible" title="选择正确人物" :submitting="submitting" @select="selectTarget" />

  <ResponsiveDialog v-model="confirmVisible" title="确认批量更正" max-width="28rem" :before-close="() => !submitting">
    <p class="text-sm leading-7">{{ assignmentMode === 'unassigned' ? `将选中的 ${selectedCount} 张人脸释放为未标记人脸，照片和人脸仍然保留。` : `将选中的 ${selectedCount} 张人脸更正为“${target?.identity_name}”。` }}</p>
    <p v-if="reassignCount" class="ts-muted mt-3 text-sm">其中 {{ reassignCount }} 张已有归属，{{ manualCount }} 张曾人工确认，请核对头像。</p>
    <p class="ts-muted mt-3 text-sm">不会合并整个分组，也不会修改其他未选中的人脸。</p>
    <template #footer>
      <div class="flex justify-end gap-2">
        <button type="button" class="ts-button ts-button-secondary" :disabled="submitting" @click="confirmVisible = false">返回核对</button>
        <button type="button" class="ts-button ts-button-primary" :disabled="!canSubmit" @click="confirmAndApply">{{ assignmentMode === 'unassigned' ? '确认释放' : '确认更正' }}</button>
      </div>
    </template>
  </ResponsiveDialog>

  <ResponsiveDialog v-model="discardVisible" title="放弃本次选择？" max-width="28rem">
    <p class="text-sm leading-7">选中的人脸还没有保存。关闭后将放弃本次选择，照片和人脸归属不会改变。</p>
    <template #footer>
      <div class="flex justify-end gap-2">
        <button type="button" class="ts-button ts-button-secondary" @click="discardVisible = false">继续核对</button>
        <button type="button" class="ts-button ts-button-primary" @click="discardSelection">放弃并关闭</button>
      </div>
    </template>
  </ResponsiveDialog>

  <ResponsiveDialog :model-value="!!preview" title="核对原图" max-width="60rem" mobile-mode="fullscreen" mobile-back :glass="false"
    @update:model-value="value => { if (!value) preview = null }">
    <div v-if="preview" class="space-y-3">
      <p class="ts-muted text-sm">框选的是这张候选人脸，照片中的其他人不会被更正。</p>
      <div class="preview-photo relative flex h-[55dvh] w-full items-center justify-center overflow-hidden rounded-xl">
        <img ref="previewImage" :key="preview.id" :src="toServerUrl(`/api/medias/${preview.photo_id}/file`)"
          alt="候选人脸所在原图" class="h-full w-full object-contain" @load="previewLoaded = true" @error="previewFailed = true" />
        <span v-if="previewBox && !previewFailed" class="pointer-events-none absolute rounded-lg border-2 border-primary-500"
          :style="{ left: `${previewBox.x}px`, top: `${previewBox.y}px`, width: `${previewBox.width}px`, height: `${previewBox.height}px` }" />
        <p v-if="previewFailed" role="alert" class="ts-surface absolute p-4 text-sm">原图加载失败，请返回后重试</p>
      </div>
      <p class="text-sm">当前：{{ preview.identity_name || '未标记' }} · {{ dateLabel(preview.photo_time) }}</p>
    </div>
    <template #footer>
      <button v-if="preview" type="button" class="ts-button ts-button-primary w-full" :disabled="submitting || !canSelect(preview)"
        @click="toggle(preview)">{{ isSelected(preview) ? '取消选择这张人脸' : '选择这张人脸' }}</button>
    </template>
  </ResponsiveDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, ChevronDown, Expand } from 'lucide-vue-next'
import { useIntersectionObserver, useResizeObserver, useWindowSize } from '@vueuse/core'
import type { PhotoFace, SimilarFaceCandidate } from '@/api/face'
import type { FaceIdentity } from '@/types/album'
import { useSimilarFaces } from '@/composables/useSimilarFaces'
import { containFaceRect } from '@/utils/photoFaces'
import { toServerUrl } from '@/config/server'
import ResponsiveDialog from './ui/ResponsiveDialog.vue'
import PersonSelector from './PersonSelector.vue'
import FaceThumbnail from './FaceThumbnail.vue'

const props = defineProps<{ visible: boolean; reference: PhotoFace }>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  applied: [photoIds: string[]]
}>()
const {
  reference, target, assignmentMode, lowSimilarity, scope, match, hideAssigned, showSelected, page,
  faceCount, photoCount, hasMore, loading, appending, submitting, loadError, actionError,
  successMessage, undoToken, selectedItems, selectedCount, visibleItems, reassignCount, manualCount,
  canSubmit, load, isSelected, canSelect, toggle, selectPage, clearSelection, chooseTarget, apply, undo,
} = useSimilarFaces(props, photoIds => emit('applied', photoIds))
const { width } = useWindowSize()
const isMobile = computed(() => width.value < 768)
watch(isMobile, () => { if (props.visible && !submitting.value) void load() })
const selectorVisible = ref(false)
const confirmVisible = ref(false)
const discardVisible = ref(false)
const preview = ref<SimilarFaceCandidate | null>(null)
const previewLoaded = ref(false)
const previewFailed = ref(false)
const previewImage = ref<HTMLImageElement | null>(null)
const previewSize = ref({ width: 0, height: 0 })
useResizeObserver(previewImage, () => {
  previewSize.value = { width: previewImage.value?.clientWidth || 0, height: previewImage.value?.clientHeight || 0 }
})
const previewBox = computed(() => !previewLoaded.value || !preview.value || !previewImage.value ? null
  : containFaceRect(preview.value.face_rect, previewSize.value.width, previewSize.value.height,
    previewImage.value.naturalWidth, previewImage.value.naturalHeight))
watch(preview, () => { previewLoaded.value = false; previewFailed.value = false })
watch(() => props.visible, value => {
  if (!value) { preview.value = null; selectorVisible.value = false; confirmVisible.value = false; discardVisible.value = false }
})
const loadMoreButton = ref<HTMLElement | null>(null)
useIntersectionObserver(loadMoreButton, ([entry]) => {
  if (entry?.isIntersecting && isMobile.value && !loading.value && !submitting.value && hasMore.value && !showSelected.value) {
    void load(page.value + 1, true)
  }
})

function dateLabel(value: string | null) {
  return value ? value.slice(0, 10).replaceAll('-', '.') : '拍摄时间未知'
}
function selectTarget(person: FaceIdentity) {
  chooseTarget(person)
  selectorVisible.value = false
}
async function confirmAndApply() {
  confirmVisible.value = false
  await apply()
}
async function beforeClose() {
  if (submitting.value) return false
  if (selectedItems.value.some(item => item.id !== props.reference.id) || ((target.value || assignmentMode.value === 'unassigned') && selectedCount.value > 0)) {
    discardVisible.value = true
    return false
  }
  return true
}
function discardSelection() {
  clearSelection()
  discardVisible.value = false
  emit('update:visible', false)
}
</script>

<style scoped>
.face-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.face-skeleton, .preview-photo { background: var(--ts-color-surface-muted); }
.candidate-card { min-width: 0; overflow: hidden; border: 1px solid var(--ts-color-border); border-radius: 12px; background: var(--ts-color-surface); }
.candidate-selected { border-color: var(--theme-primary); box-shadow: 0 0 0 1px var(--theme-primary); }
.face-check { position: absolute; right: 6px; top: 6px; display: flex; width: 22px; height: 22px; align-items: center; justify-content: center; border: 1px solid var(--ts-color-border); border-radius: 50%; background: var(--ts-color-surface); color: white; }
.face-check.checked { background: var(--theme-primary); border-color: var(--theme-primary); }
.candidate-card button:disabled, .sample-face:disabled { cursor: not-allowed; }
@media (max-width: 359px) {
  .face-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .scope-filters { grid-template-columns: minmax(0, 1fr); }
}
@media (min-width: 640px) { .face-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; } }
@media (min-width: 1024px) { .face-grid { grid-template-columns: repeat(6, minmax(0, 1fr)); } }
</style>
