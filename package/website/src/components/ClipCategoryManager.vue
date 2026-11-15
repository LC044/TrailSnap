<template>
  <ResponsiveDialog v-model="visible" title="分类规则" description="保留原有 YOLO 分类，按文字和参考图片增加 CLIP 标签" max-width="1000px" mobile-mode="fullscreen" mobile-back>
    <p v-if="error" class="mb-4 text-sm text-red-600 dark:text-red-400" role="alert">{{ error }} <button class="underline" @click="load">重试</button></p>
    <div class="mb-5 flex flex-wrap items-center gap-3">
      <el-input v-model="search" placeholder="搜索分类" aria-label="搜索分类" class="!w-48" clearable />
      <button class="ts-button ts-button-primary" @click="edit()"><Plus class="h-4 w-4" />新建分类</button>
      <button class="ts-button ts-button-secondary" :disabled="busy || !categories.some(c => c.enabled)" @click="rebuild()">更新历史照片</button>
      <span class="text-xs text-gray-500 dark:text-gray-400">已启用 {{ categories.filter(c => c.enabled).length }} 个</span>
    </div>
    <p v-if="loading" class="text-sm text-gray-500 dark:text-gray-400">正在加载分类…</p>
    <section v-for="group in filteredGroups" :key="group.name" class="mb-6">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 class="font-semibold text-[var(--ts-color-text)]">{{ group.name }}</h3>
        <button class="ts-button ts-button-ghost ts-button-sm" :disabled="busy" @click="enableGroup(categories.filter(c => c.groups.includes(group.name)))">{{ categories.filter(c => c.groups.includes(group.name)).every(c => c.enabled) ? '停用本组' : '启用本组' }}</button>
      </div>
      <div class="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <button v-for="category in group.items" :key="category.id" class="flex min-h-16 items-center justify-between gap-3 rounded-xl border border-[var(--ts-color-border)] bg-[var(--ts-color-surface)] p-3 text-left hover:border-primary-500 focus-visible:ring-2 focus-visible:ring-primary-500" @click="edit(category)">
          <span class="min-w-0"><span class="block truncate text-sm font-medium text-[var(--ts-color-text)]">{{ category.name }}</span><span class="text-xs text-gray-500 dark:text-gray-400">{{ category.count }} 张 · {{ category.enabled ? '自动分类已开启' : '未启用' }}</span></span>
          <Settings2 class="h-4 w-4 shrink-0 text-gray-500 dark:text-gray-400" />
        </button>
      </div>
    </section>
    <p v-if="!loading && !filteredGroups.length" class="py-8 text-center text-gray-500 dark:text-gray-400">没有找到分类</p>
  </ResponsiveDialog>

  <ResponsiveDialog v-model="editing" :title="selected ? '编辑分类' : '新建分类'" max-width="760px" mobile-mode="fullscreen" mobile-back>
    <div class="space-y-5">
      <label class="block text-sm text-[var(--ts-color-text)]">分类名称<el-input v-model="draft.name" class="mt-2" maxlength="50" placeholder="例如：露营" /></label>
      <div>
        <label class="mb-2 block text-sm text-[var(--ts-color-text)]" for="clip-group">展示分组</label>
        <el-select id="clip-group" v-model="draft.groups" multiple filterable allow-create default-first-option :multiple-limit="3" class="!w-full" aria-label="展示分组" placeholder="选择分组，或输入新名称后回车"><el-option v-for="group in groups" :key="group" :label="group" :value="group" /></el-select>
        <p class="ts-muted mt-1 text-xs">最多选择或创建 3 个分组，新分组随分类保存。</p>
      </div>
      <div>
        <p class="text-sm text-[var(--ts-color-text)]">文字描述（最多 5 条）</p>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">文字和参考图片至少填写一种。每条文字、每张图片等权合并，形成同一个分类特征。</p>
        <div v-for="(_, index) in draft.descriptions" :key="index" class="mt-2 flex items-start gap-2">
          <el-input v-model="draft.descriptions[index]" type="textarea" :rows="2" :maxlength="100" show-word-limit :aria-label="`分类描述 ${index + 1}`" />
          <button class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-gray-500 dark:text-gray-400" :aria-label="`移除描述 ${index + 1}`" @click="changeDescriptions(index)"><Trash2 class="h-4 w-4" /></button>
        </div>
        <button v-if="draft.descriptions.length < 5" class="mt-2 min-h-11 text-sm text-primary-600 dark:text-primary-400" @click="changeDescriptions()">＋添加描述</button>
      </div>
      <div>
        <p class="text-sm text-[var(--ts-color-text)]">参考图片（{{ draft.reference_images.length }}/5）</p>
        <p class="ts-muted mt-1 text-xs">上传或从图库选择，可逐张截取目标区域。支持 20 MB 以内的图片，裁剪仅用于分类，不修改原图。</p>
        <div class="mt-3 flex flex-wrap gap-2">
          <button class="ts-button ts-button-secondary" :disabled="busy || imageLoading || draft.reference_images.length >= 5" @click="fileInput?.click()"><Upload class="h-4 w-4" />上传图片</button>
          <button class="ts-button ts-button-secondary" :disabled="busy || imageLoading || draft.reference_images.length >= 5" @click="showPicker = true"><Images class="h-4 w-4" />从图库选择</button>
          <input ref="fileInput" class="hidden" type="file" accept="image/*" multiple aria-label="上传分类参考图片" @change="selectFiles" />
        </div>
        <p v-if="imageLoading" class="ts-muted mt-2 text-sm" role="status">正在加载参考图片…</p>
        <div class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div v-for="(image, index) in draft.reference_images" :key="index" class="overflow-hidden rounded-xl border border-[var(--ts-color-border)]">
            <img :src="image" :alt="`参考图片 ${index + 1}`" class="aspect-square w-full object-contain bg-[var(--ts-color-surface-muted)]" />
            <div class="flex justify-between gap-1 p-1">
              <button class="ts-button ts-button-ghost ts-button-sm" :disabled="busy || imageLoading" :aria-label="`重新截取参考图片 ${index + 1}`" @click="recrop(index)">截取</button>
              <button class="ts-button ts-button-ghost ts-button-sm" :disabled="busy || imageLoading" :aria-label="`移除参考图片 ${index + 1}`" @click="draft.reference_images.splice(index, 1)"><Trash2 class="h-4 w-4" /></button>
            </div>
          </div>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <label class="text-sm text-[var(--ts-color-text)]">匹配严格程度</label>
        <el-select v-model="draft.strictness" class="!w-32" aria-label="匹配严格程度"><el-option label="宽松" value="relaxed" /><el-option label="标准" value="standard" /><el-option label="严格" value="strict" /></el-select>
        <el-switch v-model="draft.enabled" active-text="自动分类" />
      </div>
      <details>
        <summary class="cursor-pointer text-sm text-gray-500 dark:text-gray-400">高级设置：模型匹配阈值</summary>
        <label v-for="(_, model) in draft.thresholds" :key="model" class="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-[var(--ts-color-text)]">{{ model }}<el-input-number v-model="draft.thresholds[model]" :min="-1" :max="1" :step="0.005" :precision="3" :aria-label="`${model} 匹配阈值`" /></label>
        <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">分数是照片与分类特征的相似度。更高阈值收录更严格；使用参考图后建议重新预览调整，其他模型需单独校准。</p>
        <div class="mt-3 flex flex-wrap gap-2">
          <el-input v-model="newModel" placeholder="其他模型的 runtimeName" aria-label="其他模型名称" class="!w-64" />
          <button class="ts-button ts-button-secondary" :disabled="!newModel.trim()" @click="addModel">添加模型阈值</button>
        </div>
      </details>
      <p class="text-xs text-gray-500 dark:text-gray-400">{{ calibrationHint }}</p>
      <p v-if="!selected" class="text-xs text-gray-500 dark:text-gray-400">新建并启用后会自动对全部历史照片分类。</p>
      <el-checkbox v-if="selected" v-model="draft.apply_history" :disabled="!draft.enabled">保存后同时更新历史照片</el-checkbox>
      <p v-if="editError" class="text-sm text-red-600 dark:text-red-400" role="alert">{{ editError }}</p>
      <section v-if="preview">
        <p class="text-sm text-[var(--ts-color-text)]">已检查 {{ preview.checked }} 张，命中 {{ preview.matched_count }} 张，阈值 {{ preview.threshold.toFixed(3) }}</p>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">当前模型可用 {{ preview.available }} 张；{{ preview.missing }} 张缺少兼容向量。预览不会修改标签。</p>
        <div v-for="section in [{ title: '匹配结果', items: preview.matches }, { title: '阈值附近', items: preview.boundary }]" :key="section.title" class="mt-4">
          <h4 class="mb-2 text-sm font-medium text-[var(--ts-color-text)]">{{ section.title }}</h4>
          <div class="grid grid-cols-3 gap-2 sm:grid-cols-6">
            <div v-for="item in section.items" :key="item.photo.id" class="min-w-0"><img :src="mapPhotoToImage(item.photo).thumbnail" alt="分类预览照片" class="aspect-square w-full rounded-lg object-cover" loading="lazy" /><p class="mt-1 text-center text-xs text-gray-500 dark:text-gray-400">{{ item.score.toFixed(3) }} · {{ item.matched ? '收录' : '未收录' }}</p></div>
          </div>
          <p v-if="!section.items.length" class="text-xs text-gray-500 dark:text-gray-400">暂无结果</p>
        </div>
      </section>
    </div>
    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <button v-if="selected" class="ts-button ts-button-secondary mr-auto text-red-600 dark:text-red-400" :disabled="busy" @click="remove">删除规则</button>
        <button class="ts-button ts-button-secondary" :disabled="busy || imageLoading" @click="runPreview">{{ busy ? '处理中…' : '预览结果' }}</button>
        <button v-if="selected" class="ts-button ts-button-secondary" :disabled="busy || !selected.enabled" @click="rebuild([selected.id])">重新分类此类别</button>
        <button class="ts-button ts-button-primary" :disabled="busy || imageLoading" @click="save">保存</button>
      </div>
    </template>
  </ResponsiveDialog>
  <ResponsiveDialog v-model="showPicker" title="选择分类参考图片" max-width="64rem" mobile-mode="fullscreen" mobile-back panel-class="clip-reference-picker">
    <div class="min-h-0 flex-1"><PhotoSelector v-if="showPicker" :store="pickerStore" enable-filters :allowed-file-types="['image', 'live_photo']" is-selector embedded @select="selectPhotos" @cancel="showPicker = false" /></div>
  </ResponsiveDialog>
  <ClipReferenceCropper :model-value="cropping" :source="cropSource" @update:model-value="cancelCrop" @confirm="useCrop" />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Images, Plus, Settings2, Trash2, Upload } from 'lucide-vue-next'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import PhotoSelector from '@/components/PhotoSelector.vue'
import ClipReferenceCropper from '@/components/ClipReferenceCropper.vue'
import { clipClassificationService, type ClipCategory, type ClipRuleDraft, type ClipPreview } from '@/api/classification'
import { mapPhotoToImage, useClipReferencePhotosStore } from '@/stores/photoStore'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; updated: [] }>()
const visible = computed({ get: () => props.modelValue, set: value => emit('update:modelValue', value) })
const categories = ref<ClipCategory[]>([])
const groups = ref<string[]>([])
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const editError = ref('')
const search = ref('')
const editing = ref(false)
const selected = ref<ClipCategory>()
const preview = ref<ClipPreview>()
const newModel = ref('')
let previewVersion = 0
const blank = (): ClipRuleDraft => ({ name: '', descriptions: [''], reference_images: [], groups: ['自定义'], strictness: 'standard', thresholds: { 'chinese-clip-ViT-B-16': 0.42 }, enabled: false, revision: 1, apply_history: false })
const draft = ref<ClipRuleDraft>(blank())
const filteredGroups = computed(() => groups.value.map(name => ({ name, items: categories.value.filter(c => c.groups.includes(name) && c.name.includes(search.value.trim())) })).filter(g => g.items.length))
const calibrationHint = computed(() => selected.value?.calibration.status === 'reviewed' ? '默认阈值经过开发图库抽样检查，建议先预览你的照片。' : '该分类样本有限或使用自定义规则，请预览后调整阈值。')
const message = (e: unknown) => e instanceof Error ? e.message : (e as { msg?: string })?.msg || '操作失败，请重试'
const pickerStore = useClipReferencePhotosStore()
const fileInput = ref<HTMLInputElement>()
const showPicker = ref(false)
const imageLoading = ref(false)
const cropping = ref(false)
const cropSource = ref('')
let cropIndex: number | undefined
let imageVersion = 0
let pendingImages: (File | string)[] = []
let objectUrl = ''
function releaseSource() { if (objectUrl) URL.revokeObjectURL(objectUrl); objectUrl = ''; cropSource.value = '' }
function cancelCrop() { imageVersion++; cropping.value = false; imageLoading.value = false; pendingImages = []; cropIndex = undefined; releaseSource() }
async function nextImage() {
  releaseSource()
  const source = pendingImages.shift()
  if (!source) { cropping.value = false; imageLoading.value = false; return }
  const version = ++imageVersion
  imageLoading.value = true
  try {
    const blob = typeof source === 'string' ? await clipClassificationService.referencePhoto(source) : source
    if (version !== imageVersion) return
    if (!blob.type.startsWith('image/') || !blob.size || blob.size > 20 * 1024 * 1024) throw new Error('请选择不超过 20 MB 的图片')
    objectUrl = URL.createObjectURL(blob); cropSource.value = objectUrl; cropping.value = true
  } catch (e) { if (version === imageVersion) { editError.value = message(e); cancelCrop() } }
  finally { if (version === imageVersion) imageLoading.value = false }
}
function selectFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || []); input.value = ''
  if (!files.length) return
  editError.value = ''
  if (files.length + draft.value.reference_images.length > 5) { editError.value = '最多添加 5 张参考图片'; return }
  if (files.some(file => !file.type.startsWith('image/') || !file.size || file.size > 20 * 1024 * 1024)) { editError.value = '请选择不超过 20 MB 的有效图片'; return }
  cropIndex = undefined; pendingImages = files; void nextImage()
}
function selectPhotos(ids: string[]) {
  showPicker.value = false; editError.value = ''
  if (!ids.length) return
  if (ids.length + draft.value.reference_images.length > 5) { editError.value = '最多添加 5 张参考图片，请减少选择数量'; return }
  cropIndex = undefined; pendingImages = ids; void nextImage()
}
function recrop(index: number) { cancelCrop(); cropIndex = index; cropSource.value = draft.value.reference_images[index]!; cropping.value = true }
function useCrop(image: string) {
  if (cropIndex !== undefined) draft.value.reference_images[cropIndex] = image
  else if (draft.value.reference_images.length < 5) draft.value.reference_images.push(image)
  cropIndex = undefined; void nextImage()
}
function payload(): ClipRuleDraft {
  const value = { ...draft.value, name: draft.value.name.trim(), descriptions: draft.value.descriptions.map(text => text.trim()).filter(Boolean), groups: [...new Set(draft.value.groups.map(group => group.trim()).filter(Boolean))] }
  if (!value.name) throw new Error('请填写分类名称')
  if (!value.groups.length) throw new Error('请至少选择或创建一个分组')
  if (value.groups.some(group => group.length > 100)) throw new Error('分组名称不能超过 100 字')
  if (!value.descriptions.length && !value.reference_images.length) throw new Error('请至少添加一条文字描述或一张参考图片')
  return value
}
async function load() {
  loading.value = true; error.value = ''
  try { const data = await clipClassificationService.list(); categories.value = data.categories; groups.value = data.groups }
  catch (e) { error.value = message(e) } finally { loading.value = false }
}
function edit(category?: ClipCategory) {
  cancelCrop()
  previewVersion++
  selected.value = category
  draft.value = category ? { name: category.name, groups: [...category.groups], descriptions: [...category.descriptions], reference_images: [...(category.reference_images || [])], strictness: category.strictness, thresholds: { ...category.thresholds }, enabled: category.enabled, revision: category.revision, apply_history: false } : blank()
  preview.value = undefined; editError.value = ''; editing.value = true
}
function changeDescriptions(index?: number) { if (index === undefined) draft.value.descriptions.push(''); else draft.value.descriptions.splice(index, 1) }
function addModel() {
  const model = newModel.value.trim()
  if (model) draft.value.thresholds[model] ??= 0.42
  newModel.value = ''
}
async function enableGroup(items: ClipCategory[]) {
  busy.value = true; error.value = ''
  try {
    await clipClassificationService.enable(items.map(c => c.id), !items.every(c => c.enabled))
    await load(); emit('updated')
  } catch (e) { error.value = message(e) } finally { busy.value = false }
}
async function runPreview() {
  busy.value = true; editError.value = ''; preview.value = undefined
  const version = ++previewVersion
  try {
    const result = await clipClassificationService.preview(payload())
    if (version === previewVersion) preview.value = result
  } catch (e) { if (version === previewVersion) editError.value = message(e) } finally { busy.value = false }
}
async function save() {
  busy.value = true; editError.value = ''
  try { await clipClassificationService.save(selected.value?.id, payload()); editing.value = false; await load(); emit('updated'); ElMessage.success('分类规则已保存') }
  catch (e) { editError.value = message(e) } finally { busy.value = false }
}
async function rebuild(categoryIds?: string[]) {
  busy.value = true
  try { await clipClassificationService.rebuild(categoryIds); ElMessage.success('已加入任务队列，可在任务管理中查看进度') } catch (e) { error.value = message(e) } finally { busy.value = false }
}
async function remove() {
  if (!selected.value) return
  try { await ElMessageBox.confirm('删除规则将移除该规则生成的 CLIP 结果，保留其他来源及人工标签。', '删除分类规则', { type: 'warning' }) } catch { return }
  busy.value = true
  try { await clipClassificationService.remove(selected.value.id); editing.value = false; await load(); emit('updated') } catch (e) { editError.value = message(e) } finally { busy.value = false }
}
watch(() => props.modelValue, value => { if (value) load() }, { immediate: true })
watch(() => [draft.value.descriptions, draft.value.reference_images, draft.value.strictness, draft.value.thresholds], () => { previewVersion++; preview.value = undefined }, { deep: true })
watch(editing, value => { if (!value) { previewVersion++; showPicker.value = false; cancelCrop() } }, { flush: 'sync' })
watch(showPicker, value => { if (value) pickerStore.selectedFilters.file_types = ['image', 'live_photo'] })
onBeforeUnmount(cancelCrop)
</script>

<style>
.clip-reference-picker .responsive-dialog-body { display: flex; flex-direction: column; overflow: hidden; padding: 0; }
</style>
