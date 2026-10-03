<template>
  <section ref="reader" class="photo-diary mx-auto max-w-5xl scroll-mt-24 py-4 md:pr-16" aria-label="照片日记本" tabindex="0" @keydown="onKeydown">
    <div v-if="days.length" class="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <BookOpen class="h-5 w-5 text-primary-500" />
        <div>
          <h2 class="font-serif text-lg text-gray-900 dark:text-gray-100">我的影像日记</h2>
          <p class="text-xs text-gray-500 dark:text-gray-400">把照片和这一天的故事，珍藏在同一页</p>
        </div>
      </div>
      <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
        <CalendarDays class="h-4 w-4" />
        <span class="sr-only">选择日记日期</span>
        <select v-model="selectedKey" :disabled="turning || saving" class="min-h-11 max-w-48 rounded-lg border border-gray-200 bg-white px-3 dark:border-gray-700 dark:bg-gray-900">
          <option v-for="day in days" :key="day.key" :value="day.key">{{ day.label }} · {{ day.count }} 张</option>
        </select>
      </label>
    </div>

    <div v-if="error" role="alert" class="mb-4 rounded-xl bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">
      {{ error }}
      <button class="ml-3 min-h-11 underline" @click="retry">重新加载</button>
    </div>

    <ChapterBook v-if="currentDay" :page-key="currentDay.key" :direction="direction" :ready="!waitingForPhotos" title="我的影像日记" @busy="turning = $event">
      <section class="diary-page diary-left">
        <div class="diary-page-content">
          <div class="diary-running"><span>行影集 · 影像日记</span><span>{{ currentDay.label }}</span></div>
          <h3 class="mb-1 font-serif text-3xl text-gray-900 dark:text-gray-100">{{ currentDay.month }}月{{ currentDay.day }}日</h3>
          <p class="mb-5 text-xs text-gray-500 dark:text-gray-400">{{ weekday }} · {{ currentDay.count }} 张影像</p>
          <div v-if="waitingForPhotos" role="status" class="grid grid-cols-2 gap-3">
            <div v-for="n in 4" :key="n" class="aspect-[4/5] animate-pulse rounded-sm bg-gray-200 dark:bg-gray-700" />
            <span class="sr-only">正在加载这一天的照片</span>
          </div>
          <div v-else-if="visiblePhotos.length" class="grid gap-3" :class="visiblePhotos.length === 1 ? 'grid-cols-1' : 'grid-cols-2'">
            <button v-for="(photo, index) in visiblePhotos" :key="photo.id" type="button" :data-photo-id="photo.id"
              class="diary-photo-frame relative overflow-hidden rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
              :class="visiblePhotos.length === 1 ? 'aspect-[4/5]' : 'aspect-square'" :aria-label="'查看照片 ' + photo.filename" @click="$emit('click-photo', photo)">
              <img :src="photo.preview || photo.thumbnail" :alt="photo.filename" :loading="index === 0 ? 'eager' : 'lazy'" class="h-full w-full object-cover" />
              <span v-if="photo.file_type === 'video'" class="absolute bottom-4 right-4 rounded bg-black/60 px-2 py-1 text-xs text-white">视频</span>
            </button>
          </div>
          <button v-if="visiblePhotos.length < dayPhotos.length" type="button" class="mt-4 min-h-11 w-full rounded-lg border border-primary-200 px-3 text-sm text-primary-600 hover:bg-primary-50 dark:border-primary-800 dark:text-primary-400 dark:hover:bg-primary-900/20" @click="visiblePhotoCount += 12">显示更多 · 还有 {{ dayPhotos.length - visiblePhotos.length }} 张</button>
          <p v-if="!waitingForPhotos && !visiblePhotos.length" class="py-10 text-sm text-gray-500 dark:text-gray-400">这一天的影像尚未加载。</p>
        </div>
        <span class="diary-page-number" aria-hidden="true">{{ String(dayIndex * 2 + 1).padStart(2, '0') }}</span>
      </section>
      <section class="diary-page diary-right">
        <div class="diary-page-content">
          <div class="diary-running"><span>{{ currentDay.year }} · 这一天的故事</span><Feather class="h-4 w-4" /></div>
          <h3 class="mb-3 font-serif text-2xl text-gray-900 dark:text-gray-100">{{ locationMap[currentDay.key]?.primary || '值得记住的一天' }}</h3>
          <div class="mb-5 flex flex-wrap items-center gap-3">
            <span v-if="caption" class="text-xs text-gray-500 dark:text-gray-400">{{ caption.source === 'manual' ? '亲笔记录' : caption.streaming ? '正在写下这一天…' : 'AI 记录' }}</span>
            <button class="min-h-11 text-xs text-primary-600 dark:text-primary-400" :disabled="captionLoading || generating || turning" @click="startEditing"><span>{{ caption?.caption ? '编辑文字' : '写下这一天' }}</span></button>
            <button v-if="!caption?.caption || caption.source !== 'manual'" class="flex min-h-11 items-center gap-1 text-xs text-primary-600 disabled:opacity-50 dark:text-primary-400" :disabled="captionLoading || generating || turning || !canGenerate" @click="generateEntry"><Sparkles class="h-3.5 w-3.5" />{{ generating ? '正在生成…' : caption?.caption ? '重新生成' : 'AI 写日记' }}</button>
          </div>
          <p v-if="captionLoading" role="status" class="text-sm text-gray-500 dark:text-gray-400">正在读取日记…</p>
          <p v-else-if="caption?.caption" class="diary-writing whitespace-pre-wrap break-words font-serif text-base leading-8 text-gray-700 dark:text-gray-200">{{ caption.caption }}</p>
          <p v-else class="diary-writing min-h-48 font-serif text-base leading-8 text-gray-400 dark:text-gray-500">照片留下了这一刻。<br />写下几句话，让回忆更完整。</p>
          <p v-if="entryError" role="alert" class="mt-4 text-sm text-red-600 dark:text-red-400">{{ entryError }}</p>
        </div>
        <span class="diary-page-number" aria-hidden="true">{{ String(dayIndex * 2 + 2).padStart(2, '0') }}</span>
      </section>
    </ChapterBook>
    <div v-else-if="loading" role="status" class="rounded-xl bg-gray-100 py-20 text-center text-gray-500 dark:bg-gray-800 dark:text-gray-400">正在整理影像日记…</div>
    <slot v-else name="empty"><p class="py-20 text-center text-gray-500 dark:text-gray-400">还没有可以写进日记的照片</p></slot>

    <nav v-if="currentDay" class="mt-5 flex items-center justify-between gap-2" aria-label="日记翻页">
      <button class="diary-navigation" :disabled="!hasPrevious || navigationBusy" @click="turn(-1)"><ArrowLeft class="h-4 w-4" /><span>上一页</span></button>
      <p class="min-w-0 flex-1 text-center text-xs text-gray-500 dark:text-gray-400">{{ currentDay.label }} · {{ dayIndex + 1 }} / {{ days.length }} 天<br />最近的日子在前</p>
      <button class="diary-navigation" :disabled="!hasNext || navigationBusy" @click="turn(1)"><span>下一页</span><ArrowRight class="h-4 w-4" /></button>
    </nav>

    <el-dialog v-model="editorVisible" :title="editingLabel + ' · 写下这一天'" width="min(94vw, 560px)" append-to-body :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving">
      <label for="photo-diary-entry" class="sr-only">日记文字</label>
      <textarea id="photo-diary-entry" v-model="editText" rows="10" maxlength="1000" :disabled="saving" class="w-full resize-none rounded-lg border border-gray-200 bg-white p-3 font-serif leading-8 text-gray-800 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100" />
      <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">{{ editText.length }} / 1000 · 与朋友圈的当日文字同步</p>
      <p v-if="saveError" role="alert" class="mt-3 text-sm text-red-600 dark:text-red-400">{{ saveError }}</p>
      <template #footer><button class="mr-4 min-h-11 text-gray-600 dark:text-gray-300" :disabled="saving" @click="editorVisible = false">取消</button><button class="min-h-11 rounded-lg bg-primary-500 px-5 text-white hover:bg-primary-600 disabled:opacity-50" :disabled="saving || !editText.trim()" @click="saveEntry">{{ saving ? '正在保存…' : '保存' }}</button></template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight, BookOpen, CalendarDays, Feather, Sparkles } from 'lucide-vue-next'
import ChapterBook from '@/components/chapter/ChapterBook.vue'
import { useMomentCaptions } from '@/composables/useMomentCaptions'
import type { CaptionState } from '@/composables/useMomentCaptions'
import { useMomentLocations } from '@/composables/useMomentLocations'
import type { AlbumImage, TimelineItem } from '@/types/album'

interface DiaryStore {
  loadPhotosByMonth: (year: number, month: number, albumId?: string, refresh?: boolean) => Promise<void>
}
const props = withDefaults(defineProps<{ photos: AlbumImage[]; timeline: TimelineItem[]; store: DiaryStore; loading?: boolean; error?: string | null; initialDate?: string }>(), { loading: false, error: null, initialDate: '' })
const emit = defineEmits<{ 'click-photo': [photo: AlbumImage]; 'active-date': [date: string]; 'entry-update': [entry: { key: string; state: CaptionState }]; retry: [] }>()
const reader = ref<HTMLElement>()
const selectedKey = ref(''), visiblePhotoCount = ref(4), direction = ref(1), turning = ref(false), monthLoading = ref(false), captionLoading = ref(false)
const editorVisible = ref(false), editingKey = ref(''), editingLabel = ref(''), editText = ref(''), saving = ref(false), saveError = ref(''), entryError = ref('')
const { captionMap, loadingDays, loadMonth, generate, save, abortAll } = useMomentCaptions()
const { locationMap, loadMonth: loadLocations } = useMomentLocations()
let loadSequence = 0
const dateKey = (date: Date) => `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`
const days = computed(() => {
  const timeline = props.timeline.length ? props.timeline : [...props.photos.reduce((map, photo) => {
    const date = new Date(photo.timestamp), key = dateKey(date)
    if (!Number.isFinite(date.getTime())) return map
    const day = map.get(key) || { year: date.getFullYear(), month: date.getMonth() + 1, day: date.getDate(), count: 0 }
    day.count++
    map.set(key, day)
    return map
  }, new Map<string, TimelineItem>()).values()]
  return timeline.filter(day => day.count > 0 && day.year > 0 && day.month >= 1 && day.month <= 12 && day.day > 0)
    .map(day => ({ ...day, key: `${day.year}-${day.month}-${day.day}`, label: `${day.year}-${String(day.month).padStart(2, '0')}-${String(day.day).padStart(2, '0')}` }))
    .sort((a, b) => b.year - a.year || b.month - a.month || b.day - a.day)
})
const dayIndex = computed(() => days.value.findIndex(day => day.key === selectedKey.value))
const currentDay = computed(() => days.value[dayIndex.value])
const dayPhotos = computed(() => props.photos.filter(photo => dateKey(new Date(photo.timestamp)) === selectedKey.value).sort((a, b) => b.timestamp - a.timestamp))
const visiblePhotos = computed(() => dayPhotos.value.slice(0, visiblePhotoCount.value))
const waitingForPhotos = computed(() => (monthLoading.value || props.loading) && dayPhotos.value.length === 0)
const caption = computed(() => captionMap[selectedKey.value])
const generating = computed(() => loadingDays.value.has(selectedKey.value))
const canGenerate = computed(() => dayPhotos.value.some(photo => photo.hasPhotoTime !== false))
const weekday = computed(() => currentDay.value ? new Date(currentDay.value.year, currentDay.value.month - 1, currentDay.value.day).toLocaleDateString('zh-CN', { weekday: 'long' }) : '')
const navigationBusy = computed(() => turning.value || monthLoading.value || saving.value || editorVisible.value)
const hasPrevious = computed(() => dayIndex.value > 0)
const hasNext = computed(() => dayIndex.value + 1 < days.value.length)
const isEditing = computed(() => editorVisible.value || generating.value)

function findDate(date: string) {
  const [year, month, day] = date.split('-').map(Number)
  return days.value.find(item => item.year === year && (!month || item.month === month) && (!day || item.day === day))
}
watch(days, list => {
  if (!list.some(day => day.key === selectedKey.value)) selectedKey.value = findDate(props.initialDate)?.key || list[0]?.key || ''
}, { immediate: true })
watch(selectedKey, () => { visiblePhotoCount.value = 4; entryError.value = ''; void loadDay() }, { immediate: true })
async function loadDay(refresh = false) {
  const day = currentDay.value
  const sequence = ++loadSequence
  if (!day) return
  emit('active-date', day.label)
  monthLoading.value = true
  captionLoading.value = true
  const photosPromise = props.store.loadPhotosByMonth(day.year, day.month, undefined, refresh)
  const captionPromise = loadMonth(day.year, day.month, refresh).finally(() => { if (sequence === loadSequence) captionLoading.value = false })
  void loadLocations(day.year, day.month)
  try { await Promise.all([photosPromise, captionPromise]) }
  finally { if (sequence === loadSequence) monthLoading.value = false }
}
function retry() { if (currentDay.value) void loadDay(true); else emit('retry') }
function turn(value: number) {
  if (navigationBusy.value) return
  direction.value = value
  const next = days.value[dayIndex.value + value]
  if (next) selectedKey.value = next.key
}
function scrollToDate(date: string) {
  if (editorVisible.value || saving.value || turning.value) return
  const day = findDate(date)
  if (!day) return
  direction.value = days.value.indexOf(day) >= dayIndex.value ? 1 : -1
  selectedKey.value = day.key
  reader.value?.scrollIntoView({ block: 'start', behavior: 'smooth' })
}
function onKeydown(event: KeyboardEvent) {
  if ((event.target as HTMLElement).closest('input, textarea, select, [contenteditable="true"]') || editorVisible.value) return
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); turn(event.key === 'ArrowRight' ? 1 : -1) }
}
function startEditing() {
  editingKey.value = selectedKey.value
  editingLabel.value = currentDay.value?.label || ''
  editText.value = caption.value?.caption || ''
  saveError.value = ''
  editorVisible.value = true
}
async function saveEntry() {
  if (saving.value || !editText.value.trim()) return
  saving.value = true; saveError.value = ''
  try {
    await save(editingKey.value, editText.value.trim())
    emit('entry-update', { key: editingKey.value, state: captionMap[editingKey.value] })
    editorVisible.value = false
  }
  catch (error) { saveError.value = error instanceof Error ? error.message : '保存失败，请重试' }
  finally { saving.value = false }
}
async function generateEntry() {
  const key = selectedKey.value
  entryError.value = ''
  try { await generate(key); if (captionMap[key]) emit('entry-update', { key, state: captionMap[key] }) }
  catch (error) { if (selectedKey.value === key) entryError.value = error instanceof Error ? error.message : '生成失败，请重试' }
}
onMounted(async () => { await nextTick(); reader.value?.scrollIntoView({ block: 'start', behavior: 'auto' }) })
onBeforeUnmount(() => { loadSequence++; abortAll() })
defineExpose({ scrollToDate, isEditing })
</script>

<style scoped>
.diary-navigation { display:flex; flex-shrink:0; align-items:center; gap:8px; min-height:44px; padding:8px 16px; border:1px solid #e5e7eb; border-radius:8px; background:white; color:#4b5563; font-size:13px; white-space:nowrap; }
.diary-navigation:disabled { opacity:.4; cursor:default; }
:global(.dark) .diary-navigation { border-color:#374151; background:#111827; color:#d1d5db; }
.photo-diary :deep(.diary-page-content) { padding:26px 28px 56px; }
.photo-diary :deep(.diary-running) { margin-bottom:22px; }
@media(max-width:767px) { .photo-diary :deep(.diary-page-content) { padding:22px 20px 52px; } .diary-navigation { padding:8px 12px; } }
</style>
