<template>
  <ResponsiveDialog :model-value="modelValue" :title="`${day} · ${draftMode ? '调整候选' : '选择这一帧'}`"
    description="照片展示一秒，动态素材保留你选择的一秒。" max-width="64rem" placement="right" mobile-mode="fullscreen" mobile-back
    :close-on-backdrop="false" :close-on-escape="false" @update:model-value="requestClose">
    <div ref="body" class="space-y-4">
      <p v-if="error" class="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300" role="alert">{{ error }}</p>
      <div v-if="loading" role="status" class="py-16 text-center text-gray-500 dark:text-gray-400">正在加载当天的素材…</div>
      <div v-else class="grid gap-5 md:grid-cols-2">
        <section class="space-y-3">
          <p v-if="current?.date_changed" class="text-sm text-amber-700 dark:text-amber-300">拍摄日期已调整，此选帧仍保留在原日期。</p>
          <p v-if="current && !current.removed && !current.available" class="text-sm text-amber-700 dark:text-amber-300">{{ current.reason }}</p>
          <div v-if="current?.photo_id && selected?.id !== current.photo_id && !current.removed" class="flex items-center gap-3 text-sm text-gray-600 dark:text-gray-300">
            <img :src="thumbnailUrl(current.photo_id)" alt="原选帧" class="h-12 w-12 rounded-lg object-cover" />
            <span>原选帧 → 下方新选帧，保存后替换</span>
          </div>
          <div class="flex min-h-56 items-center justify-center overflow-hidden rounded-xl bg-gray-100 dark:bg-gray-950">
            <span v-if="mediaLoading" class="text-sm text-gray-500 dark:text-gray-400">加载预览…</span>
            <video v-else-if="source && selection.mode === 'motion'" ref="video" :src="source" muted playsinline preload="metadata"
              class="max-h-[45vh] w-full object-contain" @loadedmetadata="onMetadata" @timeupdate="stopAtEnd" @error="mediaFailed" />
            <img v-else-if="source" :src="source" alt="选帧完整画面预览" class="max-h-[45vh] w-full object-contain" @error="mediaFailed" />
            <span v-else class="px-5 text-center text-sm text-gray-500 dark:text-gray-400">{{ selected ? '预览暂不可用' : '从右侧选择一个瞬间' }}</span>
          </div>
          <div v-if="selected" class="space-y-3">
            <div v-if="selected.file_type === 'live_photo'" class="flex flex-wrap gap-2">
              <button type="button" class="df-button" :aria-pressed="selection.mode === 'still'" @click="setMode('still')">使用静态照片</button>
              <button type="button" class="df-button" :disabled="!selected.has_motion" :aria-pressed="selection.mode === 'motion'" @click="setMode('motion')">使用动态片段</button>
              <p v-if="!selected.has_motion" class="w-full text-xs text-amber-700 dark:text-amber-300">动态片段不可用，将使用照片。</p>
            </div>
            <template v-if="selection.mode === 'motion'">
              <label class="block text-sm text-gray-600 dark:text-gray-300">一秒片段起点：{{ selection.start_seconds.toFixed(1) }} 秒</label>
              <input v-model.number="selection.start_seconds" type="range" min="0" :max="maxStart" step="0.1" aria-label="一秒片段起点" class="w-full accent-[var(--theme-primary)]" @input="seek" />
              <div class="flex items-center gap-2">
                <input v-model.number="selection.start_seconds" type="number" min="0" :max="maxStart" step="0.1" aria-label="片段起点秒数" class="df-input !w-28" @change="seek" />
                <button type="button" class="df-button" :disabled="!source || mediaError" @click="playSnippet">播放这一秒</button>
                <span class="text-xs text-gray-500 dark:text-gray-400">静音片段</span>
              </div>
              <p v-if="duration > 0 && duration < 1" class="text-xs text-amber-700 dark:text-amber-300">素材不足一秒，影片会保持最后一帧补足。</p>
            </template>
            <p v-else class="text-xs text-gray-500 dark:text-gray-400">这张照片将在影片中展示 1 秒。</p>
            <button v-if="mediaError" class="df-button" type="button" @click="loadSource">重试预览</button>
            <label class="block text-sm text-gray-700 dark:text-gray-200">一句话（可选）
              <input v-model="selection.caption" maxlength="30" placeholder="例如：晚风刚刚好" class="df-input mt-2" />
            </label>
            <p class="text-right text-xs text-gray-500 dark:text-gray-400">{{ [...selection.caption].length }}/30</p>
          </div>
        </section>
        <section>
          <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h3 class="text-sm font-medium text-gray-800 dark:text-gray-100">当天素材 · {{ total }} 个</h3>
            <select v-model="kind" class="df-input !w-auto" aria-label="素材类型" @change="loadCandidates(true)">
              <option value="all">全部</option><option value="still">照片</option><option value="motion">动态素材</option>
            </select>
          </div>
          <div class="grid grid-cols-3 gap-2 sm:grid-cols-4">
            <button v-for="asset in candidates" :key="asset.id" type="button" :disabled="!asset.available" class="relative aspect-square overflow-hidden rounded-lg border-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-40"
              :class="selected?.id === asset.id ? 'border-primary-500' : 'border-transparent'" :aria-label="`${asset.photo_time || '素材'}，${asset.file_type}${asset.reason || ''}`" :aria-pressed="selected?.id === asset.id" @click="choose(asset)">
              <img :src="thumbnailUrl(asset.id)" alt="" loading="lazy" class="h-full w-full object-cover" />
              <span class="absolute inset-x-0 bottom-0 bg-black/60 px-1 py-1 text-[10px] text-white">{{ asset.photo_time?.slice(11, 16) }} {{ asset.file_type === 'live_photo' ? 'LIVE' : asset.file_type === 'video' ? `视频 ${Math.round(asset.duration * 10) / 10}s` : '' }}</span>
            </button>
          </div>
          <div v-if="!candidates.length" class="py-10 text-center text-sm text-gray-500 dark:text-gray-400">
            <p>这一天没有{{ kind === 'all' ? '可选' : kind === 'still' ? '照片' : '动态' }}素材。</p>
            <RouterLink to="/photos" class="mt-3 inline-block text-primary-600 dark:text-primary-400" @click.prevent="goToPhotos">前往图库导入照片</RouterLink>
          </div>
          <button v-if="candidates.length < total" type="button" class="df-button mt-3 w-full" :disabled="candidateLoading" @click="loadCandidates(false)">{{ candidateLoading ? '加载中…' : '加载更多' }}</button>
        </section>
      </div>
    </div>
    <template #footer>
      <div class="flex flex-wrap items-center gap-2">
        <button v-if="current && !current.removed && !draftMode" type="button" class="df-button text-red-600 dark:text-red-400" :disabled="saving" @click="remove">移除选帧</button>
        <button v-if="undoVersion !== null" type="button" class="df-button" :disabled="saving" @click="undo">撤销移除</button>
        <span class="flex-1" />
        <button type="button" class="df-button" :disabled="saving" @click="requestClose(false)">取消</button>
        <button type="button" class="df-primary" :disabled="!selected || saving || mediaLoading || mediaError" @click="save">{{ saving ? '保存中…' : draftMode ? '使用这个候选' : current && !current.removed && current.photo_id !== selected?.id ? '替换当天一帧' : '保存这一帧' }}</button>
      </div>
    </template>
  </ResponsiveDialog>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import { dailyFrameApi, dailyFrameError } from '@/api/dailyFrame'
import { thumbnailUrl } from '@/utils/mediaUrl'
import type { DailyFrame, DailyFrameAsset, DailyFrameSelection, DailyFrameSuggestion } from '@/types/dailyFrame'

const props = defineProps<{ modelValue: boolean; day: string; preferredPhoto?: string; draftMode?: boolean; initialSelection?: DailyFrameSuggestion }>()
const emit = defineEmits<{ 'update:modelValue': [boolean]; saved: []; selected: [DailyFrameSuggestion] }>()
const router = useRouter()
const body = ref<HTMLElement | null>(null)
const current = ref<DailyFrame | null>(null)
const candidates = ref<DailyFrameAsset[]>([])
const selected = ref<DailyFrameAsset | null>(null)
const total = ref(0), kind = ref('all'), loading = ref(false), saving = ref(false), candidateLoading = ref(false)
const error = ref(''), source = ref(''), mediaLoading = ref(false), mediaError = ref(false), duration = ref(0)
const video = ref<HTMLVideoElement | null>(null)
const selection = reactive<DailyFrameSelection>({ photo_id: '', mode: 'still', start_seconds: 0, caption: '', version: 0 })
const undoVersion = ref<number | null>(null)
const baseline = ref('')
const dirty = computed(() => JSON.stringify(selection) !== baseline.value)
const maxStart = computed(() => Math.floor(Math.max(0, duration.value - 1) * 10) / 10)
let epoch = 0, sourceRequest = 0, candidatesRequest = 0, openRequest = 0
let controller: AbortController | null = null
let stopTimer: ReturnType<typeof setTimeout> | undefined
let returnFocus: HTMLElement | null = null

function revokeSource() { if (source.value.startsWith('blob:')) URL.revokeObjectURL(source.value); source.value = '' }
async function loadSource() {
  const request = ++sourceRequest
  controller?.abort(); controller = new AbortController()
  video.value?.pause(); clearTimeout(stopTimer); revokeSource()
  if (!selected.value) return
  mediaLoading.value = true; mediaError.value = false
  try {
    const url = selection.mode === 'motion' ? await dailyFrameApi.sourceUrl(selected.value.id, 'motion')
      : URL.createObjectURL(await dailyFrameApi.source(selected.value.id, 'still', controller.signal))
    if (request === sourceRequest) source.value = url
    else if (url.startsWith('blob:')) URL.revokeObjectURL(url)
  } catch (err) {
    if (request === sourceRequest && !(err as { code?: string }).code?.includes('CANCELED')) { mediaError.value = true; error.value = dailyFrameError(err) }
  } finally { if (request === sourceRequest) mediaLoading.value = false }
}

async function choose(asset: DailyFrameAsset, initial?: DailyFrameSelection) {
  const request = ++epoch
  error.value = ''; selected.value = asset
  selection.photo_id = asset.id
  selection.mode = initial?.mode || (asset.file_type === 'video' || asset.has_motion ? 'motion' : 'still')
  selection.start_seconds = initial?.start_seconds || 0
  duration.value = asset.duration
  try {
    const detail = await dailyFrameApi.asset(asset.id)
    if (request !== epoch) return
    selected.value = detail; duration.value = detail.duration
    await loadSource()
  } catch (err) { if (request === epoch) { mediaError.value = true; error.value = dailyFrameError(err) } }
}

async function loadCandidates(reset: boolean) {
  const request = ++candidatesRequest
  const offset = reset ? 0 : candidates.value.length
  candidateLoading.value = true
  try {
    const result = await dailyFrameApi.candidates(props.day, offset, kind.value)
    if (request !== candidatesRequest) return
    candidates.value = reset ? result.items : [...candidates.value, ...result.items]; total.value = result.total
  } catch (err) { if (request === candidatesRequest) error.value = dailyFrameError(err) }
  finally { if (request === candidatesRequest) candidateLoading.value = false }
}

async function open() {
  const request = ++openRequest
  epoch++; sourceRequest++; candidatesRequest++; controller?.abort(); revokeSource()
  returnFocus = document.activeElement as HTMLElement
  loading.value = true; error.value = ''; undoVersion.value = null; selected.value = null; kind.value = 'all'
  Object.assign(selection, { photo_id: '', mode: 'still', start_seconds: 0, caption: '', version: 0 })
  const day = props.day
  try {
    const row = await dailyFrameApi.day(day)
    if (!props.modelValue || props.day !== day || request !== openRequest) return
    current.value = row
    selection.version = row.version; selection.caption = row.caption || ''
    // Only copy editable fields, not suggestion metadata.
    if (props.initialSelection) Object.assign(selection, { photo_id: props.initialSelection.photo_id, mode: props.initialSelection.mode,
      start_seconds: props.initialSelection.start_seconds, caption: props.initialSelection.caption, version: props.initialSelection.version })
    const initial = props.initialSelection?.photo || (!row.removed ? row.photo : null)
    if (initial) { Object.assign(selection, { photo_id: initial.id, mode: props.initialSelection?.mode || row.mode,
      start_seconds: props.initialSelection?.start_seconds ?? row.start_seconds }); await choose(initial, { ...selection }) }
    if (!props.modelValue || request !== openRequest) return
    baseline.value = JSON.stringify(selection)
    if (props.preferredPhoto && props.preferredPhoto !== selected.value?.id) {
      const preferred = await dailyFrameApi.asset(props.preferredPhoto)
      if (!props.modelValue || request !== openRequest) return
      await choose(preferred)
    }
    if (!props.modelValue || request !== openRequest) return
    await loadCandidates(true)
  } catch (err) { if (request === openRequest) error.value = dailyFrameError(err) }
  finally { if (request === openRequest) { loading.value = false; await nextTick(); body.value?.closest('section[role="dialog"]')?.querySelector<HTMLButtonElement>('button')?.focus() } }
}

function setMode(mode: 'still' | 'motion') { selection.mode = mode; selection.start_seconds = 0; void loadSource() }
function onMetadata() {
  if (video.value) {
    // HTML media duration can include a longer audio track. Keep the probed
    // video duration used by the server when validating the final second.
    if (!duration.value) duration.value = video.value.duration
    seek()
  }
}
function seek() { selection.start_seconds = Math.max(0, Math.min(maxStart.value, Number(selection.start_seconds) || 0)); if (video.value) { video.value.pause(); video.value.currentTime = selection.start_seconds } }
function stopAtEnd() { if (video.value && video.value.currentTime >= selection.start_seconds + 1) video.value.pause() }
async function playSnippet() {
  if (!video.value) return
  video.value.currentTime = selection.start_seconds
  try { await video.value.play(); clearTimeout(stopTimer); stopTimer = setTimeout(() => video.value?.pause(), 1000) }
  catch { mediaFailed() }
}
function mediaFailed() { mediaError.value = true; error.value = '预览无法播放，请重试或更换素材。' }
async function confirmDiscard() {
  if (saving.value) return false
  if (!dirty.value || loading.value) return true
  try { await ElMessageBox.confirm('这次修改还未保存，是否放弃？', '未保存的选帧', { confirmButtonText: '放弃修改', cancelButtonText: '继续编辑' }); return true }
  catch { return false }
}
async function requestClose(value = false) { if (!value && await confirmDiscard()) emit('update:modelValue', false) }
async function goToPhotos() { if (await confirmDiscard()) { emit('update:modelValue', false); void router.push('/photos') } }
async function save() {
  if (!selected.value || saving.value) return
  if (props.draftMode) {
    emit('selected', { ...selection, day: props.day, photo: selected.value }); baseline.value = JSON.stringify(selection)
    emit('update:modelValue', false); return
  }
  saving.value = true; error.value = ''
  try {
    current.value = await dailyFrameApi.save(props.day, { ...selection })
    baseline.value = JSON.stringify(selection); emit('saved'); emit('update:modelValue', false)
    ElMessage.success('已保存这一天的瞬间')
  } catch (err) { error.value = dailyFrameError(err) }
  finally { saving.value = false }
}
async function remove() {
  try { await ElMessageBox.confirm('只移除这一日的选帧，原照片仍在图库中。', '移除选帧', { type: 'warning' }) } catch { return }
  saving.value = true
  try {
    const row = await dailyFrameApi.remove(props.day, current.value!.version)
    undoVersion.value = row.version; current.value = row; selection.version = row.version
    selected.value = null; selection.photo_id = ''; revokeSource(); baseline.value = JSON.stringify(selection); emit('saved')
  } catch (err) { error.value = dailyFrameError(err) } finally { saving.value = false }
}
async function undo() {
  saving.value = true
  try {
    const row = await dailyFrameApi.undo(props.day, undoVersion.value!)
    current.value = row; Object.assign(selection, { photo_id: row.photo_id, mode: row.mode, start_seconds: row.start_seconds, caption: row.caption, version: row.version })
    if (row.photo) await choose(row.photo, { ...selection })
    baseline.value = JSON.stringify(selection); undoVersion.value = null; emit('saved')
  } catch (err) { error.value = dailyFrameError(err) } finally { saving.value = false }
}
function keyboard(event: KeyboardEvent) {
  if (!props.modelValue || document.querySelector('.el-message-box__wrapper')) return
  if (event.key === 'Escape') { event.preventDefault(); void requestClose(false) }
  if (event.key === 'Tab') {
    const items = [...(body.value?.closest('section[role="dialog"]')?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select, a[href]') || [])].filter(el => el.offsetParent !== null)
    const first = items[0], last = items.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }
}
function beforeUnload(event: BeforeUnloadEvent) { if (props.modelValue && dirty.value) { event.preventDefault(); event.returnValue = '' } }
watch(() => [props.modelValue, props.day] as const, ([visible]) => {
  if (visible) { void open(); window.addEventListener('keydown', keyboard); window.addEventListener('beforeunload', beforeUnload) }
  else { openRequest++; epoch++; sourceRequest++; candidatesRequest++; controller?.abort(); revokeSource(); clearTimeout(stopTimer); window.removeEventListener('keydown', keyboard); window.removeEventListener('beforeunload', beforeUnload); returnFocus?.focus() }
}, { immediate: true })
onBeforeRouteLeave(async () => !props.modelValue || await confirmDiscard())
onBeforeUnmount(() => { openRequest++; epoch++; sourceRequest++; candidatesRequest++; controller?.abort(); revokeSource(); clearTimeout(stopTimer); window.removeEventListener('keydown', keyboard); window.removeEventListener('beforeunload', beforeUnload) })
</script>
