<template>
  <ResponsiveDialog
    :model-value="visible"
    title="查找此人的更多照片"
    description="根据已识别的人脸查找，不会重新检测照片。"
    max-width="55rem" mobile-mode="fullscreen" mobile-back
    :before-close="() => !applying"
    @update:model-value="emit('update:visible', $event)"
  >
    <div class="mb-4 space-y-2">
      <div class="flex flex-wrap items-center gap-3">
        <label for="person-search-threshold" class="text-sm font-medium">最大匹配距离</label>
        <el-input-number :key="loading || applying ? 'busy' : 'ready'" id="person-search-threshold" v-model="threshold" :min="0" :max="1" :step="0.01" :disabled="loading || applying" />
        <button type="button" class="ts-button ts-button-secondary" :disabled="loading || applying || threshold == null" @click="loadPreview">重新查找</button>
      </div>
      <p class="ts-muted text-xs leading-5">数值越小越严格，数值越大候选越多。仅用于本次查找；修改后需重新查找。移出候选仍使用已保存的移出阈值。</p>
      <p v-if="thresholdChanged" class="ts-muted text-xs" role="status">阈值已修改，请重新查找后再应用。</p>
    </div>
    <div v-if="loading" class="flex min-h-72 flex-col items-center justify-center gap-3 text-gray-500 dark:text-gray-400">
      <RefreshCwIcon class="h-7 w-7 animate-spin text-primary-600" />
      <span>正在比对已识别的人脸…</span>
    </div>

    <div v-else-if="loadFailed" class="flex min-h-72 flex-col items-center justify-center gap-3 text-center">
      <p class="text-gray-600 dark:text-gray-300">查找失败，请稍后重试。</p>
      <button type="button" class="rounded-lg bg-primary-600 px-4 py-2 text-sm text-white hover:bg-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="loadPreview">
        重新查找
      </button>
    </div>

    <div v-else-if="preview" class="space-y-4">
      <div class="rounded-xl border border-gray-200 bg-gray-50 p-3 text-sm dark:border-gray-700 dark:bg-gray-800">
        <p v-if="preview.reason === 'no_reference_faces'" class="mb-2 text-sm">此人物还没有可用于比对的人脸。请先在照片中标记一张清晰人脸。</p>
        <p class="font-medium text-gray-800 dark:text-gray-100">
          找到 {{ preview.summary.add_count }} 个待新增、{{ preview.summary.remove_count }} 个待移出人脸
        </p>
        <p class="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">
          高相似度且未归属的新增项已默认选中；普通候选、从其他人物改归属及移出项需手动勾选。人工确认过的人脸不会被自动移出或改归属。
        </p>
      </div>

      <el-tabs v-model="activeTab">
        <el-tab-pane :label="`待新增 (${preview.add_candidates.length})`" name="add">
          <div class="mb-3 flex items-center justify-between">
            <span class="text-xs text-gray-500 dark:text-gray-400">包含未归属和可能属于其他人物的人脸</span>
            <button type="button" class="text-xs text-primary-600 hover:text-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="toggleAllAdds">
              {{ allAddsSelected ? '全部取消' : '全部选择' }}
            </button>
          </div>
          <CandidateGrid
            :items="preview.add_candidates"
            :selected-ids="selectedAddIds"
            :disabled="applying || thresholdChanged"
            empty-text="没有发现可新增的人脸"
            @toggle="toggleSelection(selectedAddIds, $event)"
          />
        </el-tab-pane>

        <el-tab-pane :label="`待移出 (${preview.remove_candidates.length})`" name="remove">
          <div class="mb-3 flex items-center justify-between">
            <span class="text-xs text-gray-500 dark:text-gray-400">这些人脸与可信参考人脸的距离较大</span>
            <button type="button" class="text-xs text-primary-600 hover:text-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="toggleAllRemoves">
              {{ allRemovesSelected ? '全部取消' : '全部选择' }}
            </button>
          </div>
          <CandidateGrid
            :items="preview.remove_candidates"
            :selected-ids="selectedRemoveIds"
            :disabled="applying || thresholdChanged"
            empty-text="没有发现需要移出的人脸"
            @toggle="toggleSelection(selectedRemoveIds, $event)"
          />
        </el-tab-pane>
      </el-tabs>
    </div>

    <template #footer>
      <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <el-button :disabled="applying" @click="emit('update:visible', false)">取消</el-button>
        <el-button type="primary" :loading="applying" :disabled="loading || thresholdChanged || !preview || selectedCount === 0" @click="applySelection">
          应用选中项（{{ selectedCount }}）
        </el-button>
      </div>
    </template>
  </ResponsiveDialog>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onBeforeUnmount, ref, watch, type PropType } from 'vue'
import { ElCheckbox, ElMessage } from 'element-plus'
import { RefreshCw as RefreshCwIcon } from 'lucide-vue-next'
import { faceApi, type FaceRescanCandidate, type FaceRescanPreview } from '@/api/face'
import type { FaceIdentity } from '@/types/album'
import { thumbnailUrl } from '@/utils/mediaUrl'
import ResponsiveDialog from './ui/ResponsiveDialog.vue'

const props = defineProps<{ visible: boolean; identity: FaceIdentity | null }>()
const emit = defineEmits<{
  (event: 'update:visible', value: boolean): void
  (event: 'applied', result: any): void
}>()

const loading = ref(false)
const applying = ref(false)
const loadFailed = ref(false)
const preview = ref<FaceRescanPreview | null>(null)
const threshold = ref<number | undefined>()
const thresholdChanged = computed(() => !!preview.value && threshold.value !== preview.value.candidate_threshold)
let requestVersion = 0
let controller: AbortController | null = null
const selectedAddIds = ref<number[]>([])
const selectedRemoveIds = ref<number[]>([])
const activeTab = ref('add')
const selectedCount = computed(() => selectedAddIds.value.length + selectedRemoveIds.value.length)
const allAddsSelected = computed(() => !!preview.value?.add_candidates.length && selectedAddIds.value.length === preview.value.add_candidates.length)
const allRemovesSelected = computed(() => !!preview.value?.remove_candidates.length && selectedRemoveIds.value.length === preview.value.remove_candidates.length)

const toggleSelection = (selection: number[], faceId: number) => {
  if (applying.value || thresholdChanged.value) return
  const index = selection.indexOf(faceId)
  if (index >= 0) selection.splice(index, 1)
  else selection.push(faceId)
}

const toggleAllAdds = () => {
  if (!preview.value || applying.value || thresholdChanged.value) return
  selectedAddIds.value = allAddsSelected.value ? [] : preview.value.add_candidates.map(item => item.face_id)
}

const toggleAllRemoves = () => {
  if (!preview.value || applying.value || thresholdChanged.value) return
  selectedRemoveIds.value = allRemovesSelected.value ? [] : preview.value.remove_candidates.map(item => item.face_id)
}

const loadPreview = async () => {
  if (!props.identity || applying.value) return
  controller?.abort()
  controller = new AbortController()
  const version = ++requestVersion
  loading.value = true
  loadFailed.value = false
  preview.value = null
  selectedAddIds.value = []
  selectedRemoveIds.value = []
  try {
    const result = await faceApi.previewIdentityRescan(props.identity.id, threshold.value, controller.signal)
    if (version !== requestVersion || !props.visible) return
    preview.value = result
    threshold.value = result.candidate_threshold
    selectedAddIds.value = result.add_candidates
      .filter(item => item.recommended && item.assignment_type === 'unassigned')
      .map(item => item.face_id)
    selectedRemoveIds.value = []
    activeTab.value = result.add_candidates.length ? 'add' : 'remove'
  } catch (error) {
    if (version !== requestVersion || !props.visible) return
    console.error('Failed to preview face rescan', error)
    loadFailed.value = true
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

const applySelection = async () => {
  if (!props.identity || !selectedCount.value || applying.value || thresholdChanged.value || loading.value || !preview.value) return
  const version = requestVersion
  applying.value = true
  try {
    const result = await faceApi.applyIdentityRescan(props.identity.id, {
      add_face_ids: selectedAddIds.value,
      remove_face_ids: selectedRemoveIds.value,
      threshold: preview.value.candidate_threshold,
    })
    if (version !== requestVersion || !props.visible) return
    ElMessage.success(`已应用：新增 ${result.added_count ?? 0} 张，移出 ${result.removed_count ?? 0} 张`)
    emit('applied', result)
    emit('update:visible', false)
  } catch (error: any) {
    if (version !== requestVersion || !props.visible) return
    if (error?.response?.status === 409) {
      ElMessage.warning('候选结果已变化，请重新确认')
      applying.value = false
      await loadPreview()
    } else {
      console.error('Failed to apply face rescan', error)
      ElMessage.error('应用查找结果失败')
    }
  } finally {
    applying.value = false
  }
}

watch([() => props.visible, () => props.identity?.id], ([visible]) => {
  ++requestVersion
  controller?.abort()
  loading.value = false
  preview.value = null
  selectedAddIds.value = []
  selectedRemoveIds.value = []
  threshold.value = undefined
  if (visible) void loadPreview()
}, { immediate: true })
onBeforeUnmount(() => { ++requestVersion; controller?.abort() })

const CandidateGrid = defineComponent({
  name: 'CandidateGrid',
  props: {
    items: { type: Array as PropType<FaceRescanCandidate[]>, required: true },
    selectedIds: { type: Array as PropType<number[]>, required: true },
    emptyText: { type: String, required: true },
    disabled: { type: Boolean, default: false },
  },
  emits: ['toggle'],
  setup(candidateProps, { emit: emitCandidate }) {
    const cropStyle = (rect?: number[] | null) => {
      if (!rect || rect.length !== 4) return {}
      const [x1, y1, x2, y2] = rect
      const faceWidth = x2 - x1
      const faceHeight = y2 - y1
      if (faceWidth <= 0 || faceHeight <= 0) return {}
      const widthPercent = 100 / (faceWidth * 1.8)
      const heightPercent = 100 / (faceHeight * 1.8)
      const style: Record<string, string> = {
        left: '50%',
        top: '50%',
        transform: `translate(-${((x1 + x2) / 2 * 100).toFixed(2)}%, -${((y1 + y2) / 2 * 100).toFixed(2)}%)`,
      }
      if (widthPercent < heightPercent) {
        style.width = `${widthPercent.toFixed(2)}%`
        style.height = 'auto'
      } else {
        style.width = 'auto'
        style.height = `${heightPercent.toFixed(2)}%`
      }
      return style
    }
    return () => candidateProps.items.length
      ? h('div', { class: 'grid max-h-[48vh] grid-cols-2 gap-3 overflow-y-auto pr-1 sm:grid-cols-3 md:grid-cols-4' },
          candidateProps.items.map(item => h('button', {
            type: 'button',
            disabled: candidateProps.disabled,
            'aria-pressed': candidateProps.selectedIds.includes(item.face_id),
            class: [
              'relative overflow-hidden rounded-xl border bg-white text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:bg-gray-900',
              candidateProps.selectedIds.includes(item.face_id) ? 'border-primary-500 ring-1 ring-primary-500' : 'border-gray-200 dark:border-gray-700',
            ],
            onClick: () => emitCandidate('toggle', item.face_id),
          }, [
            h('div', { class: 'relative aspect-square overflow-hidden bg-gray-100 dark:bg-gray-800' }, [
              h('img', {
                src: thumbnailUrl(item.photo_id, 'medium'),
                class: item.face_rect?.length === 4 ? 'absolute max-w-none' : 'h-full w-full object-cover',
                style: cropStyle(item.face_rect),
                loading: 'lazy',
                alt: '人脸候选',
              }),
              h(ElCheckbox, {
                disabled: candidateProps.disabled,
                modelValue: candidateProps.selectedIds.includes(item.face_id),
                class: 'absolute left-2 top-2 rounded bg-white/90 px-1 dark:bg-gray-900/90',
                'onUpdate:modelValue': () => emitCandidate('toggle', item.face_id),
                onClick: (event: Event) => event.stopPropagation(),
              }),
            ]),
            h('div', { class: 'space-y-1 p-2' }, [
              h('p', { class: 'text-xs font-medium text-gray-800 dark:text-gray-100' }, `相似度 ${Math.round(item.confidence * 100)}%`),
              h('p', { class: `truncate text-[11px] ${item.assignment_type === 'reassign' ? 'text-amber-600 dark:text-amber-400' : 'text-gray-500 dark:text-gray-400'}` },
                item.assignment_type === 'reassign' ? `当前：${item.current_identity_name || '其他人物'}` : item.assignment_type === 'remove' ? '建议移出' : '当前未归属'),
            ]),
          ])))
      : h('div', { class: 'flex min-h-48 items-center justify-center rounded-xl border border-dashed border-gray-300 text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400' }, candidateProps.emptyText)
  },
})
</script>
