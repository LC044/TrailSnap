<template>
  <div class="min-h-full bg-gray-50 px-4 pb-28 pt-5 dark:bg-gray-900 md:px-8 md:py-7">
    <div class="mx-auto max-w-6xl">
      <div class="flex items-center justify-between gap-3"><RouterLink to="/chapters" class="text-sm text-primary-600 dark:text-primary-400">← 人生章节</RouterLink><div v-if="chapter" class="flex gap-2"><RouterLink :to="`/chapters/${chapter.id}/edit${chapter.is_hidden ? '?manage=1' : ''}`" class="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800">编辑</RouterLink><button class="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800" @click="menuVisible = true">更多</button></div></div>
      <div v-if="loading" class="py-24 text-center text-gray-500 dark:text-gray-400">正在打开章节…</div>
      <template v-else-if="chapter">
        <div v-if="chapter.status === 'candidate'" class="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/30"><strong class="text-amber-800 dark:text-amber-200">系统建议 · 待你确认</strong><p class="mt-1 text-sm text-amber-800 dark:text-amber-200">照片只能提供时间和地点线索，章节的意义由你定义。</p><div v-for="(e, index) in chapter.evidence" :key="index" class="mt-3 text-sm text-gray-700 dark:text-gray-300"><p>• {{ e.summary }}</p><div v-if="e.photo_ids?.length" class="mt-2 flex gap-2 overflow-x-auto" aria-label="建议依据照片"><img v-for="id in e.photo_ids" :key="id" :src="thumbnailUrl(id, 'small')" alt="建议依据照片" class="h-16 w-16 shrink-0 rounded object-cover" loading="lazy" /></div></div><div class="mt-4 flex gap-2"><button class="rounded-lg border border-gray-300 px-4 py-2 text-sm dark:border-gray-600" @click="perform('ignore')">忽略</button><RouterLink :to="`/chapters/${chapter.id}/edit`" class="rounded-lg border border-primary-300 px-4 py-2 text-sm text-primary-600 dark:border-primary-700 dark:text-primary-400">调整名称与时间</RouterLink><button class="rounded-lg bg-primary-500 px-4 py-2 text-sm text-white" @click="perform('confirm')">确认并保存</button></div></div>
        <div v-if="chapter.is_hidden" class="mt-5 rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">该章节已隐藏，原照片和记忆仍在各自页面。<button class="ml-2 text-primary-600 dark:text-primary-400" @click="perform('unhide')">恢复显示</button></div>
        <nav class="mt-5 flex gap-2 border-b border-gray-200 pb-3 dark:border-gray-700" aria-label="日记阅读视图">
          <button class="min-h-11 rounded-lg px-4 text-sm" :class="readerView === 'days' ? 'bg-primary-500 text-white' : 'text-gray-600 dark:text-gray-300'" :aria-pressed="readerView === 'days'" @click="changeView('days')">每日日记</button>
          <button class="min-h-11 rounded-lg px-4 text-sm" :class="readerView === 'book' ? 'bg-primary-500 text-white' : 'text-gray-600 dark:text-gray-300'" :aria-pressed="readerView === 'book'" @click="changeView('book')">扉页与年度回顾</button>
        </nav>
        <ChapterDays v-if="readerView === 'days' && !chapter.is_hidden" ref="daysReader" :chapter="chapter" @open-photo="openDailyPhoto" @book="changeView('book')" @manage="menuVisible = true" />
        <ChapterStory v-else :chapter="chapter" :selected-year="currentYear" :photos="diaryPhotos" :gallery-photos="yearPhotos" :events="yearEvents" :photo-total="yearTotal" :has-more-photos="yearOffset < yearTotal" :event-total="yearEventTotal" :loading="yearLoading" :loading-more="loadingMore" :error="yearError" @select-year="selectYear" @open-photo="openPhoto" @write="writePage" @more-photos="loadMore" @more-events="loadMoreEvents" @retry="loadYear" />
        <ChapterDiaryComposer v-model:visible="composerVisible" :chapter="chapter" :year="writingYear" @saved="load" />
      </template>
    </div>
    <PhotoLightbox v-if="lightboxIndex >= 0" :visible="lightboxIndex >= 0" :image="lightboxImages[lightboxIndex] || null" :images="lightboxImages" :current-index="lightboxIndex" :has-prev="lightboxIndex > 0" :has-next="lightboxIndex < lightboxImages.length - 1" @prev="lightboxIndex--" @next="lightboxIndex++" @close="lightboxIndex = -1" />
    <el-dialog v-model="menuVisible" title="章节管理" width="min(92vw, 460px)"><div class="flex flex-col gap-2 text-left"><button v-if="chapter?.status === 'confirmed' || chapter?.status === 'candidate'" class="rounded-lg border border-gray-200 p-3 dark:border-gray-700" @click="openSplit">拆分章节</button><button v-if="chapter?.status === 'confirmed' || chapter?.status === 'candidate'" class="rounded-lg border border-gray-200 p-3 dark:border-gray-700" @click="openMerge">合并章节</button><button v-if="chapter?.status === 'confirmed'" class="rounded-lg border border-gray-200 p-3 dark:border-gray-700" @click="perform(chapter.is_hidden ? 'unhide' : 'hide')">{{ chapter.is_hidden ? '恢复显示' : '隐藏章节' }}</button><button class="rounded-lg border border-red-200 p-3 text-red-600" @click="remove">删除章节</button></div></el-dialog>
    <el-dialog v-model="splitVisible" title="拆分章节" width="min(94vw, 680px)">
      <p class="mb-4 text-sm text-gray-500 dark:text-gray-400">选择分界日。当天归入后一章，原照片和记忆不会被修改。</p>
      <div class="space-y-4">
        <div v-if="splitMonths.length"><p class="mb-2 text-xs text-gray-500 dark:text-gray-400">按月份定位分界</p><div class="flex h-20 items-end gap-1 overflow-x-auto border-b border-gray-200 dark:border-gray-700"><button v-for="month in splitMonths" :key="month.month" type="button" class="flex h-full min-w-3 flex-1 items-end disabled:opacity-30" :title="`${month.month}：${month.count} 张，点击从这个月开始拆分`" :aria-label="`从 ${month.month} 开始拆分`" :disabled="`${month.month}-01` < splitMinDate || `${month.month}-01` > splitMaxDate" @click="splitForm.split_date = `${month.month}-01`"><span class="w-full rounded-t" :class="month.month === splitForm.split_date.slice(0, 7) ? 'bg-primary-600' : 'bg-primary-300 dark:bg-primary-700'" :style="{ height: `${Math.max(8, month.count / splitMaxMonthCount * 100)}%` }" /></button></div><p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{{ splitMonths[0]?.month }} — {{ splitMonths[splitMonths.length - 1]?.month }}</p></div>
        <label class="block text-sm text-gray-700 dark:text-gray-200">分界日<UnifiedDatePicker v-model="splitForm.split_date" type="date" :min="splitMinDate" :max="splitMaxDate" class="mt-1 w-full" value-format="YYYY-MM-DD" /></label>
        <div v-if="splitPreviewing" class="text-sm text-gray-500 dark:text-gray-400">正在计算两章影像…</div>
        <div v-if="splitPreview" class="grid gap-3 sm:grid-cols-2">
          <div class="rounded-xl bg-gray-50 p-4 dark:bg-gray-800"><p class="text-xs text-gray-500 dark:text-gray-400">前一章 · {{ chapter?.start_date }} — {{ splitBeforeDate }}</p><p class="mt-2 text-xl font-semibold text-gray-900 dark:text-white">{{ splitPreview.first.photo_count }} 张影像</p><div class="mt-3 flex gap-1"><img v-for="id in splitPreview.first.preview_photo_ids.slice(0, 3)" :key="id" :src="thumbnailUrl(id, 'small')" alt="前一章照片样例" class="aspect-square w-16 rounded object-cover" /></div></div>
          <div class="rounded-xl bg-gray-50 p-4 dark:bg-gray-800"><p class="text-xs text-gray-500 dark:text-gray-400">后一章 · {{ splitForm.split_date }} — {{ chapter?.end_date || '至今' }}</p><p class="mt-2 text-xl font-semibold text-gray-900 dark:text-white">{{ splitPreview.second.photo_count }} 张影像</p><div class="mt-3 flex gap-1"><img v-for="id in splitPreview.second.preview_photo_ids.slice(0, 3)" :key="id" :src="thumbnailUrl(id, 'small')" alt="后一章照片样例" class="aspect-square w-16 rounded object-cover" /></div></div>
        </div>
        <label class="block text-sm text-gray-700 dark:text-gray-200">前一章名称<input v-model="splitForm.first_title" class="mt-1 w-full rounded-lg border border-gray-300 bg-white p-2.5 dark:border-gray-600 dark:bg-gray-800" /></label>
        <label class="block text-sm text-gray-700 dark:text-gray-200">后一章名称<input v-model="splitForm.second_title" class="mt-1 w-full rounded-lg border border-gray-300 bg-white p-2.5 dark:border-gray-600 dark:bg-gray-800" /></label>
      </div>
      <template #footer><button class="rounded-lg bg-primary-500 px-4 py-2 text-white disabled:opacity-40" :disabled="!splitPreview || splitPreviewing || !splitForm.first_title.trim() || !splitForm.second_title.trim()" @click="splitChapter">确认拆分</button></template>
    </el-dialog>
    <el-dialog v-model="mergeVisible" title="合并章节" width="min(94vw, 680px)">
      <p class="mb-4 text-sm text-gray-500 dark:text-gray-400">选择另一章，查看合并后的完整时间范围和影像样例。</p>
      <div class="max-h-48 space-y-2 overflow-y-auto">
        <button v-for="item in mergeOptions" :key="item.id" class="flex w-full items-center gap-3 rounded-xl border p-2 text-left dark:border-gray-700" :class="mergeTargetId === item.id ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20' : 'border-gray-200'" @click="mergeTargetId = item.id">
          <img v-if="item.cover_photo_id" :src="thumbnailUrl(item.cover_photo_id, 'small')" :alt="item.title" class="h-14 w-14 rounded-lg object-cover" />
          <span><strong class="block text-sm text-gray-900 dark:text-white">{{ item.title }}</strong><span class="text-xs text-gray-500 dark:text-gray-400">{{ item.start_date }} — {{ item.end_date || '至今' }} · {{ item.photo_count }} 张</span></span>
        </button>
      </div>
      <label class="mt-4 block text-sm text-gray-700 dark:text-gray-200">新章节名称<input v-model="mergeTitle" class="mt-1 w-full rounded-lg border border-gray-300 bg-white p-2.5 dark:border-gray-600 dark:bg-gray-800" /></label>
      <div v-if="mergePreview" class="mt-4 rounded-xl bg-primary-50 p-4 text-sm text-gray-700 dark:bg-primary-900/20 dark:text-gray-200"><p>合并后：{{ mergeStart }} — {{ mergeEnd || '至今' }} · {{ mergePreview.photo_count }} 张影像</p><p class="mt-1 text-xs text-gray-500 dark:text-gray-400">两章原计数相加为 {{ mergeSourceTotal }} 张，重叠范围会去重<span v-if="mergeGapCount !== null">；中间空档新纳入 {{ mergeGapCount }} 张</span>。</p><div class="mt-3 flex gap-2"><img v-for="id in mergePreview.preview_photo_ids.slice(0, 5)" :key="id" :src="thumbnailUrl(id, 'small')" alt="合并后照片样例" class="aspect-square w-14 rounded object-cover" /></div></div>
      <template #footer><button class="mr-2 rounded-lg border px-4 py-2 dark:border-gray-600" :disabled="!mergeTargetId" @click="previewMerge">预览结果</button><button class="rounded-lg bg-primary-500 px-4 py-2 text-white disabled:opacity-40" :disabled="!mergePreview || !mergeTitle.trim()" @click="mergeChapter">确认合并</button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import UnifiedDatePicker from '@/components/ui/UnifiedDatePicker.vue'
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { chapterApi } from '@/api/chapter'
import type { ChapterDetail, ChapterEvent, ChapterItem, ChapterPhoto } from '@/types/chapter'
import type { AlbumImage } from '@/types/album'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { toServerUrl } from '@/config/server'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import ChapterStory from '@/components/chapter/ChapterStory.vue'
import ChapterDays from '@/components/chapter/ChapterDays.vue'
import ChapterDiaryComposer from '@/components/chapter/ChapterDiaryComposer.vue'

const route = useRoute()
const router = useRouter()
const chapter = ref<ChapterDetail | null>(null)
const loading = ref(true)
const readerView = ref<'days' | 'book'>(route.query.view === 'book' || route.query.year ? 'book' : 'days')
const daysReader = ref<InstanceType<typeof ChapterDays> | null>(null)
const dailyPhotoPool = ref<ChapterPhoto[]>([])
async function changeView(view: 'days' | 'book') {
  if (daysReader.value && !await daysReader.value.canLeave()) return
  readerView.value = view
  lightboxIndex.value = -1
  await router.replace({ query: { ...route.query, view, year: view === 'days' ? undefined : route.query.year } })
  if (view === 'book') await loadYear()
}
function openDailyPhoto(id: string, photos: ChapterPhoto[]) {
  dailyPhotoPool.value = photos
  lightboxIndex.value = photos.findIndex(photo => photo.id === id)
}
const page = ref(0)
const yearPhotos = ref<ChapterPhoto[]>([])
const diaryPhotos = ref<ChapterPhoto[]>([])
const composerVisible = ref(false)
const writingYear = ref<number | null>(null)
const loadingMore = ref(false)
const loadingMoreEvents = ref(false)
const yearEvents = ref<ChapterEvent[]>([])
const yearEventTotal = ref(0)
const yearTotal = ref(0)
const yearOffset = ref(0)
const yearLoading = ref(false)
const yearError = ref(false)
let pendingScroll = 0
const lightboxIndex = ref(-1)
const menuVisible = ref(false)
const splitVisible = ref(false)
const mergeVisible = ref(false)
const splitForm = reactive({ split_date: '', first_title: '', second_title: '' })
const splitPreview = ref<{ first: Awaited<ReturnType<typeof chapterApi.preview>>; second: Awaited<ReturnType<typeof chapterApi.preview>> } | null>(null)
const splitTimeline = ref<Awaited<ReturnType<typeof chapterApi.preview>> | null>(null)
const splitPreviewing = ref(false)
const splitMinDate = computed(() => chapter.value ? addDays(chapter.value.start_date, 1) : '')
const splitMaxDate = computed(() => chapter.value?.end_date || localToday())
const splitBeforeDate = computed(() => splitForm.split_date ? addDays(splitForm.split_date, -1) : '')
const splitMonths = computed(() => splitTimeline.value?.month_counts || [])
const splitMaxMonthCount = computed(() => Math.max(1, ...splitMonths.value.map(month => month.count)))
const mergeOptions = ref<ChapterItem[]>([])
const mergeTargetId = ref('')
const mergeTitle = ref('')
const mergePreview = ref<Awaited<ReturnType<typeof chapterApi.preview>> | null>(null)
const mergeGapCount = ref<number | null>(null)
const currentYear = computed(() => chapter.value?.years[page.value - 1] || null)
const mergeTarget = computed(() => mergeOptions.value.find(item => item.id === mergeTargetId.value))
const mergeStart = computed(() => chapter.value && mergeTarget.value ? (chapter.value.start_date < mergeTarget.value.start_date ? chapter.value.start_date : mergeTarget.value.start_date) : '')
const mergeEnd = computed(() => chapter.value && mergeTarget.value ? (!chapter.value.end_date || !mergeTarget.value.end_date ? null : chapter.value.end_date > mergeTarget.value.end_date ? chapter.value.end_date : mergeTarget.value.end_date) : null)
const mergeSourceTotal = computed(() => (chapter.value?.photo_count || 0) + (mergeTarget.value?.photo_count || 0))
function addDays(value: string, days: number) {
  const date = new Date(`${value}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}
function localToday() {
  const today = new Date()
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
}
const allYearPhotos = computed(() => {
  const items = readerView.value === 'days' ? dailyPhotoPool.value : [...diaryPhotos.value, ...yearPhotos.value]
  return items.filter((photo, index) => items.findIndex(item => item.id === photo.id) === index)
})
function openPhoto(id: string) { lightboxIndex.value = allYearPhotos.value.findIndex(photo => photo.id === id) }
function writePage(year: number | null) { writingYear.value = year; composerVisible.value = true }
const lightboxImages = computed<AlbumImage[]>(() => allYearPhotos.value.map(photo => ({ id: photo.id,
  url: toServerUrl(`/api/medias/${photo.id}/file`), thumbnail: thumbnailUrl(photo.id, 'small'),
  preview: thumbnailUrl(photo.id, 'medium'), srcset: '', timestamp: new Date(photo.photo_time).getTime(),
  hasPhotoTime: true, albumIds: [], filename: photo.filename, width: photo.width || undefined,
  height: photo.height || undefined, file_type: photo.file_type as AlbumImage['file_type'] })))

async function load() {
  loading.value = true
  try {
    chapter.value = await chapterApi.detail(String(route.params.id), route.query.manage === '1')
    const rememberedYear = Number(route.query.year || sessionStorage.getItem(`chapter-year:${chapter.value.id}`))
    const rememberedIndex = chapter.value.years.indexOf(rememberedYear)
    page.value = rememberedIndex >= 0 ? rememberedIndex + 1 : 0
    if (!chapter.value.years.length) page.value = 0
    pendingScroll = Number(sessionStorage.getItem(`chapter-scroll:${chapter.value.id}`) || 0)
    await loadYear()
  }
  catch { ElMessage.error('章节不存在或已隐藏'); router.replace('/chapters') }
  finally { loading.value = false; await nextTick(); if (!yearLoading.value) await restoreScroll() }
}
function selectYear(year: number | null) {
  if (!chapter.value) return
  page.value = year === null ? 0 : chapter.value.years.indexOf(year) + 1
  sessionStorage.setItem(`chapter-year:${chapter.value.id}`, year === null ? 'cover' : String(year))
  void router.replace({ query: { ...route.query, year: year === null ? 'cover' : String(year) } })
  lightboxIndex.value = -1
}
let yearRequest = 0
async function loadYear() {
  const year = currentYear.value
  const chapterId = chapter.value?.id
  const requestId = ++yearRequest
  yearPhotos.value = []; diaryPhotos.value = []; yearEvents.value = []; yearTotal.value = 0; yearOffset.value = 0; yearEventTotal.value = 0
  loadingMore.value = false; loadingMoreEvents.value = false
  yearError.value = false
  yearLoading.value = false
  if (readerView.value === 'days' || !year || !chapterId) { if (!loading.value) await restoreScroll(); return }
  yearLoading.value = true
  try { const [result, memories] = await Promise.all([
    chapterApi.photos(chapterId, year, 0, 12, route.query.manage === '1'),
    chapterApi.events(chapterId, 0, 6, year, route.query.manage === '1'),
  ]); if (requestId === yearRequest) {
    yearPhotos.value = result.items
    diaryPhotos.value = result.representatives || result.items.slice(0, 6)
    yearOffset.value = result.items.length
    yearTotal.value = result.total; yearEvents.value = memories.items; yearEventTotal.value = memories.total
  } }
  catch { if (requestId === yearRequest) yearError.value = true }
  finally { if (requestId === yearRequest) { yearLoading.value = false; await nextTick(); if (!loading.value) await restoreScroll() } }
}
async function restoreScroll() {
  await nextTick()
  const main = document.querySelector('main')
  if (main && pendingScroll) main.scrollTop = pendingScroll
  else if (route.query.year && route.query.year !== 'cover') document.getElementById('chapter-year-content')?.scrollIntoView({ block: 'start' })
  else if (main) main.scrollTop = 0
  pendingScroll = 0
}
watch(currentYear, () => { if (!loading.value) void loadYear() })
async function loadMore() {
  if (!chapter.value || !currentYear.value || loadingMore.value) return
  const requestId = yearRequest
  loadingMore.value = true
  try { const result = await chapterApi.photos(chapter.value.id, currentYear.value, yearOffset.value, 30, route.query.manage === '1'); if (requestId !== yearRequest) return; yearOffset.value += result.items.length; const existing = new Set(yearPhotos.value.map(photo => photo.id)); yearPhotos.value.push(...result.items.filter(photo => !existing.has(photo.id))) }
  catch { ElMessage.error('加载照片失败') }
  finally { if (requestId === yearRequest) loadingMore.value = false }
}
async function loadMoreEvents() {
  if (!chapter.value || !currentYear.value || loadingMoreEvents.value) return
  const requestId = yearRequest
  loadingMoreEvents.value = true
  try { const result = await chapterApi.events(chapter.value.id, yearEvents.value.length, 20, currentYear.value, route.query.manage === '1'); if (requestId === yearRequest) yearEvents.value.push(...result.items) }
  catch { ElMessage.error('加载记忆失败') }
  finally { if (requestId === yearRequest) loadingMoreEvents.value = false }
}
async function perform(action: 'confirm' | 'ignore' | 'unhide' | 'hide') {
  if (!chapter.value) return
  if (action === 'hide') {
    try { await ElMessageBox.confirm('隐藏后，章节不会出现在常规入口和推荐中；原照片与记忆仍在各自页面。', '隐藏章节') }
    catch { return }
  }
  try {
    const result = await chapterApi.action(chapter.value.id, action, chapter.value.version)
    menuVisible.value = false
    if (action === 'ignore' || action === 'hide') router.replace('/chapters')
    else { chapter.value = await chapterApi.detail(result.id, action === 'unhide' ? false : route.query.manage === '1'); ElMessage.success('章节已更新') }
  } catch { ElMessage.error('操作失败，请刷新后重试') }
}
async function remove() {
  if (!chapter.value) return
  try { await ElMessageBox.confirm('仅删除章节定义，原照片与记忆仍会保留。', '删除章节') }
  catch { return }
  try { await chapterApi.remove(chapter.value.id, chapter.value.version); router.replace('/chapters') }
  catch { ElMessage.error('删除失败，请刷新后重试') }
}
function openSplit() {
  if (!chapter.value) return
  menuVisible.value = false
  const start = new Date(`${chapter.value.start_date}T00:00:00Z`).getTime()
  const end = new Date(`${splitMaxDate.value}T00:00:00Z`).getTime()
  splitForm.split_date = addDays(new Date(start + Math.max(86400000, Math.floor((end - start) / 2))).toISOString().slice(0, 10), 0)
  splitForm.first_title = `${chapter.value.title} · 前篇`
  splitForm.second_title = `${chapter.value.title} · 后篇`
  splitVisible.value = true
  splitTimeline.value = null
  void chapterApi.preview(chapter.value.start_date, chapter.value.end_date).then(result => { if (splitVisible.value) splitTimeline.value = result }).catch(() => { /* The date input remains available. */ })
  void previewSplit()
}
let splitTimer: ReturnType<typeof setTimeout> | null = null
let splitRequest = 0
watch(() => splitForm.split_date, () => {
  splitRequest++
  splitPreview.value = null
  if (splitTimer) clearTimeout(splitTimer)
  if (splitVisible.value) splitTimer = setTimeout(() => { void previewSplit() }, 300)
})
async function previewSplit() {
  if (!chapter.value || !splitForm.split_date || splitForm.split_date < splitMinDate.value || splitForm.split_date > splitMaxDate.value) return
  const requestId = ++splitRequest
  splitPreviewing.value = true
  try {
    const [first, second] = await Promise.all([
      chapterApi.preview(chapter.value.start_date, splitBeforeDate.value),
      chapterApi.preview(splitForm.split_date, chapter.value.end_date),
    ])
    if (requestId === splitRequest) splitPreview.value = { first, second }
  } catch { if (requestId === splitRequest) ElMessage.error('拆分预览失败') }
  finally { if (requestId === splitRequest) splitPreviewing.value = false }
}
async function splitChapter() {
  if (!chapter.value || !splitPreview.value) return
  try { const rows = await chapterApi.split(chapter.value.id, { ...splitForm, version: chapter.value.version }); splitVisible.value = false; await router.replace(`/chapters/${rows[0].id}`); ElMessage.success('章节已拆分') }
  catch { ElMessage.error('拆分失败，请检查日期和名称') }
}
async function openMerge() {
  if (!chapter.value) return
  menuVisible.value = false
  try { const result = await chapterApi.list(chapter.value.status === 'candidate' ? 'candidate' : 'confirmed', chapter.value.is_hidden, 0, 50, chapter.value.is_hidden); mergeOptions.value = result.items.filter(item => item.id !== chapter.value?.id); mergeTargetId.value = ''; mergePreview.value = null; mergeTitle.value = chapter.value.title; mergeVisible.value = true }
  catch { ElMessage.error('加载可合并章节失败') }
}
let mergeRequest = 0
watch(mergeTargetId, () => { mergeRequest++; mergePreview.value = null; mergeGapCount.value = null })
async function previewMerge() {
  if (!chapter.value || !mergeTarget.value) return
  const requestId = ++mergeRequest
  const first = chapter.value.start_date <= mergeTarget.value.start_date ? chapter.value : mergeTarget.value
  const second = first === chapter.value ? mergeTarget.value : chapter.value
  const gapStart = first.end_date ? addDays(first.end_date, 1) : null
  const gapEnd = addDays(second.start_date, -1)
  try {
    const [combined, gap] = await Promise.all([
      chapterApi.preview(mergeStart.value, mergeEnd.value),
      gapStart && gapStart <= gapEnd ? chapterApi.preview(gapStart, gapEnd) : Promise.resolve(null),
    ])
    if (requestId === mergeRequest) { mergePreview.value = combined; mergeGapCount.value = gap?.photo_count ?? null }
  }
  catch { ElMessage.error('预览合并范围失败') }
}
async function mergeChapter() {
  if (!chapter.value || !mergeTarget.value || !mergePreview.value || !mergeTitle.value.trim()) return
  try { const result = await chapterApi.merge({ chapter_ids: [chapter.value.id, mergeTarget.value.id],
    versions: { [chapter.value.id]: chapter.value.version, [mergeTarget.value.id]: mergeTarget.value.version },
    title: mergeTitle.value.trim(), summary: chapter.value.summary, start_date: mergeStart.value, end_date: mergeEnd.value, cover_photo_id: null }); mergeVisible.value = false; await router.replace(`/chapters/${result.id}`); ElMessage.success('章节已合并') }
  catch { ElMessage.error('合并失败，请刷新后重试') }
}
onMounted(() => { void load() })
onBeforeRouteLeave(() => {
  if (chapter.value) sessionStorage.setItem(`chapter-scroll:${chapter.value.id}`, String(document.querySelector('main')?.scrollTop || 0))
})
watch(() => route.params.id, () => { if (route.params.id) load() })
</script>
