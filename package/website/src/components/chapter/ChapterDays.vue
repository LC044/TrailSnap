<template>
  <section class="mt-6 outline-none" tabindex="0" aria-label="每日日记本，支持左右方向键翻页" @keydown="onKeydown">
    <template v-if="!isMobile">
    <header class="mb-4 flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div><h1 class="flex items-center gap-2 font-serif text-xl text-gray-900 dark:text-gray-100"><BookOpen :size="20" />{{ chapter.title }} · 每日日记</h1><p class="mt-2 text-xs text-gray-500 dark:text-gray-400">一天一页，照片与文字留在一起。</p></div>
    <nav class="ml-auto flex flex-wrap items-center justify-end gap-2" aria-label="日记日期筛选">
      <label class="text-xs text-gray-600 dark:text-gray-300">年份<select :disabled="!!editing || turning" v-model="year" class="ml-2 min-h-11 rounded-lg border border-gray-200 bg-white px-2 dark:border-gray-700 dark:bg-gray-800"><option value="">全部年份</option><option v-for="item in chapter.years" :key="item" :value="String(item)">{{ item }} 年</option></select></label>
      <label class="text-xs text-gray-600 dark:text-gray-300">月份<select :disabled="!!editing || turning" v-model="month" class="ml-2 min-h-11 rounded-lg border border-gray-200 bg-white px-2 dark:border-gray-700 dark:bg-gray-800"><option value="">全部月份</option><option v-for="item in 12" :key="item" :value="String(item)">{{ item }} 月</option></select></label>
      <label v-if="days.length" class="text-xs text-gray-600 dark:text-gray-300">日期<select :value="pageIndex" :disabled="!!editing || turning" class="ml-2 min-h-11 rounded-lg border border-gray-200 bg-white px-2 dark:border-gray-700 dark:bg-gray-800" @change="jump(Number(($event.target as HTMLSelectElement).value))"><option v-for="(item, index) in days" :key="item.day" :value="index">{{ item.day }}</option></select></label>
    </nav>
    </header>
    <div v-if="loading" class="h-[540px] animate-pulse rounded-xl bg-gray-200 dark:bg-gray-800" aria-label="正在翻开日记" />
    <div v-else-if="loadError" class="rounded-xl border border-gray-200 p-12 text-center dark:border-gray-700"><p class="text-gray-500 dark:text-gray-400">日记暂时无法打开</p><button class="mt-4 min-h-11 text-primary-600 dark:text-primary-400" @click="load(false)">重新加载</button></div>
    <div v-else-if="!days.length" class="rounded-xl border border-dashed border-gray-300 p-12 text-center dark:border-gray-700"><BookOpen class="mx-auto mb-4 text-primary-500" :size="32" /><p class="font-serif text-xl text-gray-900 dark:text-gray-100">这段时光还没有影像</p><p class="mt-3 text-sm text-gray-500 dark:text-gray-400">换个日期看看，新的照片会自动汇入日记。</p></div>
    <template v-else-if="day">
      <div class="mb-3 flex gap-2 md:hidden" aria-label="日记纸页">
        <button class="min-h-11 rounded-lg px-4 text-sm" :class="mobileSide === 'photos' ? 'bg-primary-500 text-white' : 'text-gray-600 dark:text-gray-300'" :aria-pressed="mobileSide === 'photos'" @click="changeSide('photos')">影像页</button>
        <button class="min-h-11 rounded-lg px-4 text-sm" :class="mobileSide === 'writing' ? 'bg-primary-500 text-white' : 'text-gray-600 dark:text-gray-300'" :aria-pressed="mobileSide === 'writing'" @click="changeSide('writing')">文字页</button>
      </div>
      <div @touchstart.passive="touchStart" @touchend.passive="touchEnd">
        <ChapterBook class="daily-book" single-page :title="chapter.title" @busy="turning = $event" :page-key="day.day + ':' + textPage" :direction="direction" aria-live="polite">
          <section class="diary-page diary-left" :class="{ 'is-mobile-hidden': mobileSide !== 'photos' }">
            <div class="diary-page-content"><div class="diary-running"><span>行影集 · {{ chapter.title }}</span><span>{{ day.day.replaceAll('-', '.') }}</span></div>
            <header class="mb-5 flex items-end justify-between gap-3"><h2 class="font-serif text-4xl text-gray-900 dark:text-gray-100">{{ day.day.slice(5).replace('-', ' / ') }}</h2><span class="text-xs text-gray-500 dark:text-gray-400">{{ weekday(day.day) }} · {{ day.photo_count }} 张影像</span></header>
            <div class="day-photo-grid grid gap-2" :class="leftPhotos(day).length === 1 ? 'grid-cols-1 single-photo' : 'grid-cols-2'">
              <button v-for="(photo, index) in leftPhotos(day)" :key="photo.id" class="day-image diary-small-photo relative overflow-hidden rounded-sm bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:bg-gray-800" :class="index === 0 ? 'col-span-full' : ''" :aria-label="'查看 ' + day.day + ' 的照片 ' + (index + 1)" @click="openPhoto(day, photo.id)"><DiaryPhoto :id="photo.id" :alt="photo.filename" :size="index === 0 ? 'medium' : 'small'" :contain="day.photos.length === 1" /><span v-if="photo.file_type === 'video'" class="absolute bottom-2 right-2 rounded bg-black/60 px-2 py-1 text-xs text-white">视频</span></button>
            </div>
            <div class="mt-3 flex items-center justify-between gap-3 text-xs text-gray-500 dark:text-gray-400"><span>本日精选 · {{ day.photos.length }} 张</span><button class="min-h-11 text-primary-600 dark:text-primary-400" @click="showAll(day)">查看当天全部 {{ day.photo_count }} 张 →</button></div>

            </div><span class="diary-page-number" aria-hidden="true">{{ String(pageIndex * 2 + 1).padStart(2, '0') }}</span>
          </section>
          <section class="diary-page diary-right" :class="{ 'is-mobile-hidden': mobileSide !== 'writing' }">
            <div class="diary-page-content"><div class="diary-running"><span>{{ day.day.replaceAll('-', '.') }} · 这一天的故事</span><Feather :size="14" /></div>
            <p class="mb-3 text-xs tracking-widest text-primary-600 dark:text-primary-400">我的影像日记 · {{ weekday(day.day) }}</p>
            <h2 class="mb-3 break-words font-serif text-2xl text-gray-900 dark:text-gray-100">{{ day.places[0] || '时光的一页' }}</h2>
            <div ref="writingArea" class="day-writing-area">
              <p v-if="caption(day)" class="diary-writing whitespace-pre-wrap break-words font-serif text-base leading-8 text-gray-700 dark:text-gray-200">{{ textPages[textPage] }}</p>
              <p v-else-if="store.generating[key(day)]" class="flex items-center gap-2 text-sm text-primary-600 dark:text-primary-400" role="status"><Sparkles :size="16" class="animate-pulse" />AI 正在把照片整理成日记…</p>
              <p v-else class="font-serif leading-8 text-gray-500 dark:text-gray-400">{{ source(day) === 'manual' ? '这一天，留给照片来讲述。' : store.errors[key(day)] || '这一天的影像已收录，可以自己写下这一页，或点击 AI 整理文案。' }}</p>
            </div>
            <p :class="{ invisible: textPages.length === 1 }" class="text-xs text-gray-500 dark:text-gray-400">文字 {{ textPage + 1 }} / {{ textPages.length }} 页 · 翻页继续阅读</p>
              <div class="mt-4 flex flex-wrap items-center justify-between gap-2"><span class="text-xs text-gray-500 dark:text-gray-400">{{ caption(day) ? source(day) === 'manual' ? '你留下的文字' : 'AI 整理 · 已保存' : '影像自动收录' }}</span><div class="flex gap-3"><button v-if="day.needs_generation && source(day) !== 'manual' && !store.generating[key(day)]" class="min-h-11 text-xs text-primary-600 dark:text-primary-400" @click="retry(day)">{{ store.errors[key(day)] ? '重试整理' : caption(day) ? '更新 AI 文案' : 'AI 整理文案' }}</button><button class="flex min-h-11 items-center gap-1 text-xs text-primary-600 dark:text-primary-400" @click="edit(day)"><Feather :size="14" />修改文字</button></div></div>
              <p v-if="caption(day) && store.generating[key(day)]" class="mt-3 text-xs text-primary-600 dark:text-primary-400" role="status">正在更新这一页的文案…</p>
            <div v-if="day.people.length || day.tags.length" class="day-clues mt-3 flex flex-wrap gap-2 border-t border-gray-200 pt-3 dark:border-gray-700"><RouterLink v-for="person in day.people.slice(0, 2)" :key="person.id" :to="'/album/people/' + person.id" class="flex items-center gap-1 rounded-full bg-primary-50 px-3 py-2 text-xs text-primary-700 dark:bg-primary-900/20 dark:text-primary-300"><Users :size="12" />{{ person.name }}</RouterLink><span v-for="tag in day.tags.slice(0, Math.max(0, 3 - day.people.length))" :key="tag" class="rounded-full bg-gray-100 px-3 py-2 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-300"># {{ tag }}</span><button class="min-h-8 text-xs text-primary-600 dark:text-primary-400" @click="detailsVisible = true">人物与标签 · {{ day.people.length + day.tags.length }} →</button></div>
            <button v-if="day.events.length" class="mt-2 min-h-8 self-start text-xs text-primary-600 dark:text-primary-400" @click="detailsVisible = true">关联回忆 · {{ day.events.length }} →</button>

            <figure v-if="rightPhotos(day).length" class="day-mementos mt-auto pt-4">
              <figcaption class="mb-2 font-serif text-xs text-gray-500 dark:text-gray-400">这一天的片刻</figcaption>
              <div class="grid gap-3" :class="rightPhotos(day).length === 1 ? 'grid-cols-2' : rightPhotos(day).length === 2 ? 'grid-cols-2' : 'grid-cols-3'">
                <button v-for="(photo, index) in rightPhotos(day)" :key="photo.id" class="day-image diary-small-photo relative aspect-[4/5] overflow-hidden rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" :aria-label="'查看 ' + day.day + ' 的照片 ' + (index + 4)" @click="openPhoto(day, photo.id)"><DiaryPhoto :id="photo.id" :alt="photo.filename" /><span v-if="photo.file_type === 'video'" class="absolute bottom-2 right-2 rounded bg-black/60 px-2 py-1 text-xs text-white">视频</span></button>
              </div>
            </figure>
            </div><span class="diary-page-number" aria-hidden="true">{{ String(pageIndex * 2 + 2).padStart(2, '0') }}</span>
          </section>
        </ChapterBook>
      </div>
      <nav class="daily-pagination mt-5 flex items-center justify-between gap-2" aria-label="日记翻页">
        <button class="diary-turn" :disabled="(pageIndex === 0 && textPage === 0 && (!isMobile || mobileSide === 'photos')) || turning || saving" @click="turn(-1)"><ArrowLeft :size="17" /><span>上一页</span></button>
        <span class="min-w-0 text-center text-xs text-gray-500 dark:text-gray-400">{{ day.day }}<br />{{ pageIndex + 1 }} / {{ total }} 天</span>
        <button class="diary-turn" :disabled="(pageIndex + 1 >= total && textPage + 1 >= textPages.length && (!isMobile || mobileSide === 'writing')) || turning || saving" @click="turn(1)"><span>{{ loadingMore ? '加载中…' : '下一页' }}</span><ArrowRight :size="17" /></button>
      </nav>
      <p class="mt-3 text-center text-xs text-gray-500 dark:text-gray-400">最近的日子在前 · 左右翻页<span class="md:hidden">，轻扫翻过影像页和文字页</span></p>
    </template>
    </template>
    <MobileDiaryReader v-if="isMobile" :chapter="chapter" :day="day" :days="days" :index="pageIndex" :total="total" :caption="day ? caption(day) : ''" :source="day ? source(day) || null : null" :generation-error="day ? store.errors[key(day)] : undefined" :generating="!!(day && store.generating[key(day)])" :can-generate="!!(day && day.needs_generation && source(day) !== 'manual')" :loading="loading" :loading-more="loadingMore" :error="loadError" :year="year" :month="month" @move="moveMobileDay" @jump="jump" @filter="mobileFilter" @more="load(true)" @reload="load(false)" @photo="day && openPhoto(day, $event)" @all="day && showAll(day)" @edit="day && edit(day)" @generate="day && retry(day)" @book="$emit('book')" @manage="$emit('manage')" />
    <el-dialog v-model="mobileEditor" title="写下这一天" width="min(94vw, 460px)" append-to-body :before-close="closeMobileEditor">
      <label for="mobile-diary-text" class="text-sm">{{ day?.day }} · 日记文字</label>
      <textarea id="mobile-diary-text" v-model="editText" maxlength="1000" rows="9" class="mt-3 w-full resize-none rounded border border-gray-300 bg-white p-3 font-serif leading-8 text-gray-800 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" />
      <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">{{ editText.length }} / 1000 · AI 会保留你的修改。</p>
      <p v-if="saveError" class="mt-2 text-red-600 dark:text-red-400">{{ saveError }}</p>
      <template #footer><button class="mr-4 min-h-11" :disabled="saving" @click="cancelEdit">取消</button><button class="min-h-11 rounded bg-primary-500 px-4 text-white" :disabled="saving" @click="day && save(day)">{{ saving ? '正在保存…' : '保存文字' }}</button></template>
    </el-dialog>
    <el-dialog v-model="detailsVisible" title="这一天的人物、标签与回忆" width="min(94vw, 560px)" append-to-body>
      <div v-if="day" class="flex flex-wrap gap-3">
        <RouterLink v-for="person in day.people" :key="person.id" :to="'/album/people/' + person.id" class="rounded-full bg-primary-50 px-3 py-2 text-primary-700 dark:bg-primary-900/20 dark:text-primary-300">{{ person.name }}</RouterLink>
        <span v-for="tag in day.tags" :key="tag" class="rounded-full bg-gray-100 px-3 py-2 text-gray-600 dark:bg-gray-800 dark:text-gray-300"># {{ tag }}</span>
        <RouterLink v-for="event in day.events" :key="event.id" :to="'/memories/' + event.id" class="flex min-h-11 w-full items-center gap-2 text-primary-600 dark:text-primary-400"><BookOpen :size="14" />{{ event.title }}<ArrowUpRight :size="13" /></RouterLink>
      </div>
    </el-dialog>
    <el-dialog v-model="galleryVisible" :title="galleryDay + ' · 全部影像'" width="min(94vw, 900px)">
      <p v-if="galleryLoading" class="py-8 text-center">正在加载影像…</p><div class="grid grid-cols-3 gap-2 sm:grid-cols-5"><button v-for="photo in galleryPhotos" :key="photo.id" class="aspect-square overflow-hidden rounded-lg" :aria-label="'查看照片 ' + photo.filename" @click="$emit('openPhoto', photo.id, galleryPhotos)"><DiaryPhoto :id="photo.id" :alt="photo.filename" /></button></div><button v-if="galleryPhotos.length < galleryTotal" class="mt-5 min-h-11 text-primary-600 dark:text-primary-400" :disabled="galleryLoading" @click="loadGallery">{{ galleryLoading ? '正在加载…' : '继续加载影像' }}</button><p v-if="galleryError" class="mt-4 text-red-600 dark:text-red-400">影像加载失败<button class="ml-3 min-h-11" @click="loadGallery">重试</button></p>
    </el-dialog>
  </section>
</template>
<script setup lang="ts">
import { useMediaQuery, useResizeObserver } from '@vueuse/core'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { ArrowLeft, ArrowRight, ArrowUpRight, BookOpen, Feather, Sparkles, Users } from 'lucide-vue-next'
import { chapterApi } from '@/api/chapter'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { useChapterDaysStore } from '@/stores/chapterDaysStore'
import type { ChapterDay, ChapterDetail, ChapterPhoto } from '@/types/chapter'
import DiaryPhoto from './DiaryPhoto.vue'
import ChapterBook from './ChapterBook.vue'
import MobileDiaryReader from './MobileDiaryReader.vue'
const props = defineProps<{ chapter: ChapterDetail }>()
const emit = defineEmits<{ openPhoto: [id: string, photos: ChapterPhoto[]]; book: []; manage: [] }>()
const store = useChapterDaysStore()
const route = useRoute()
const router = useRouter()
const days = ref<ChapterDay[]>([])
const year = ref(props.chapter.years.includes(Number(route.query.diaryYear)) ? String(route.query.diaryYear) : '')
const month = ref(Number(route.query.diaryMonth) >= 1 && Number(route.query.diaryMonth) <= 12 ? String(route.query.diaryMonth) : '')
const total = ref(0), loading = ref(false), loadingMore = ref(false), loadError = ref(false)
const mobileEditor = ref(false), detailsVisible = ref(false)
const writingArea = ref<HTMLElement>()
const textPage = ref(0), writingWidth = ref(300), writingHeight = ref(160)
useResizeObserver(writingArea, ([entry]) => {
  if (!entry) return
  writingWidth.value = entry.contentRect.width
  writingHeight.value = entry.contentRect.height
})
const editing = ref(''), editText = ref(''), originalText = ref(''), saving = ref(false), saveError = ref('')
const galleryVisible = ref(false), galleryDay = ref(''), galleryPhotos = ref<ChapterPhoto[]>([]), galleryTotal = ref(0), galleryLoading = ref(false), galleryError = ref(false)
let epoch = 0, galleryEpoch = 0
const key = (day: ChapterDay) => store.key(props.chapter.id, day.day)
const caption = (day: ChapterDay) => store.text[key(day)]?.caption ?? day.caption
const source = (day: ChapterDay) => store.text[key(day)]?.source ?? day.source
const leftPhotos = (day: ChapterDay) => day.photos.slice(0, 3)
const rightPhotos = (day: ChapterDay) => day.photos.slice(3)
const isMobile = useMediaQuery('(max-width: 767px), (pointer: coarse) and (max-width: 1023px)')
const pageIndex = ref(0)
const day = computed(() => days.value[pageIndex.value])
// Reserve the measured paper area; continuation pages retain every character.
const textPages = computed(() => {
  const body = day.value ? caption(day.value) : ''
  if (!body) return ['']
  const context = document.createElement('canvas').getContext('2d')!
  context.font = writingArea.value ? getComputedStyle(writingArea.value.querySelector('p') || writingArea.value).font : '16px serif'
  const width = Math.max(80, writingWidth.value - 16)
  const rows = Math.max(1, Math.floor(writingHeight.value / 32) - 1)
  const pages: string[] = []; let part = '', line = '', count = 1
  for (const char of body) {
    const wraps = char === '\n' || (line && context.measureText(line + char).width > width)
    if (wraps) {
      count++
      if (count > rows) { pages.push(part); part = ''; count = 1 }
      line = ''
    }
    part += char
    if (char !== '\n') line += char
  }
  if (part) pages.push(part)
  return pages.length ? pages : ['']
})
let arrivingAtEnd = false
watch(() => day.value?.day, () => { textPage.value = arrivingAtEnd ? textPages.value.length - 1 : 0; arrivingAtEnd = false })
watch(() => textPages.value.length, n => { textPage.value = Math.min(textPage.value, n - 1) })
const direction = ref(1), turning = ref(false)
const mobileSide = ref<'photos' | 'writing'>('photos')
// Warm the adjacent day's paper images without issuing any model requests.
watch([pageIndex, () => days.value.length, isMobile], () => {
  for (const index of [pageIndex.value - 1, pageIndex.value, pageIndex.value + 1]) {
    days.value[index]?.photos.forEach((photo, photoIndex) => {
      const image = new Image()
      image.src = thumbnailUrl(photo.id, isMobile.value || photoIndex === 0 ? 'medium' : 'small')
    })
  }
})
let touchX = 0, touchY = 0, touchAllowed = false
async function moveMobileDay(delta: number) {
  if (loadingMore.value || !await canLeave()) return
  const next = pageIndex.value + delta
  if (next < 0 || next >= total.value) return
  const request = epoch
  if (next >= days.value.length) await load(true)
  if (request === epoch) await jump(next)
}
function mobileFilter(nextYear: string, nextMonth: string) { year.value = nextYear; month.value = nextMonth }
async function closeMobileEditor(done: () => void) { if (await canLeave()) { editing.value = ''; done() } }
async function jump(index: number, side: 'photos' | 'writing' = 'photos') {
  if (turning.value || index === pageIndex.value || !days.value[index] || !await canLeave()) return
  editing.value = ''
  direction.value = index >= pageIndex.value ? 1 : -1
  pageIndex.value = index
  mobileSide.value = side

}
async function turn(delta: number) {
  if (turning.value || loadingMore.value || !await canLeave()) return
  editing.value = ''
  if (!isMobile.value && textPage.value + delta >= 0 && textPage.value + delta < textPages.value.length) { direction.value = delta; textPage.value += delta; return }
  if (isMobile.value && ((delta > 0 && mobileSide.value === 'photos') || (delta < 0 && mobileSide.value === 'writing'))) {
    await changeSide(delta > 0 ? 'writing' : 'photos'); return
  }
  const index = pageIndex.value + delta
  if (index < 0 || index >= total.value) return
  const request = epoch
  if (index >= days.value.length) await load(true)
  if (request === epoch) { arrivingAtEnd = !isMobile.value && delta < 0; await jump(index, isMobile.value && delta < 0 ? 'writing' : 'photos') }
}
async function changeSide(side: 'photos' | 'writing') {
  if (mobileSide.value === side || turning.value || !await canLeave()) return
  editing.value = ''
  direction.value = side === 'writing' ? 1 : -1
  mobileSide.value = side

}
function onKeydown(event: KeyboardEvent) {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || (event.target as HTMLElement).closest('input,textarea,select,[contenteditable="true"]')) return
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); void turn(event.key === 'ArrowLeft' ? -1 : 1) }
}
function touchStart(event: TouchEvent) {
  touchAllowed = !editing.value && !(event.target as HTMLElement).closest('button,a,input,textarea,select') && event.touches.length === 1
  touchX = event.touches[0]?.clientX || 0; touchY = event.touches[0]?.clientY || 0
}
function touchEnd(event: TouchEvent) {
  const touch = event.changedTouches[0]
  if (!touchAllowed || !touch) return
  const dx = touch.clientX - touchX, dy = touch.clientY - touchY
  if (Math.abs(dx) > 65 && Math.abs(dx) > Math.abs(dy) * 1.5) void turn(dx < 0 ? 1 : -1)
}
function weekday(day: string) { return new Date(day + 'T12:00:00').toLocaleDateString('zh-CN', { weekday: 'long' }) }
async function load(more: boolean) {
  if (more && loadingMore.value) return
  const request = more ? epoch : ++epoch
  const id = props.chapter.id
  if (more) loadingMore.value = true
  else { loading.value = true; loadingMore.value = false; loadError.value = false; days.value = []; pageIndex.value = 0; turning.value = false }
  try {
    const result = await chapterApi.days(id, more ? days.value.length : 0, year.value ? Number(year.value) : undefined, month.value ? Number(month.value) : undefined)
    if (request !== epoch) return
    days.value.push(...result.items); total.value = result.total
    for (const day of result.items) {
      if (day.source) store.text[store.key(id, day.day)] = { caption: day.caption, source: day.source }
    }
  } catch { if (request === epoch) loadError.value = !more }
  finally { if (request === epoch) { loading.value = false; loadingMore.value = false } }
}
async function retry(day: ChapterDay) {
  // Only this explicit click authorizes a model request, never loading or turning pages.
  await store.generate(props.chapter.id, day.day)
  if (!store.errors[key(day)]) day.needs_generation = false
}
async function canLeave() {
  if (saving.value) return false
  if (!editing.value || editText.value === originalText.value) return true
  try { await ElMessageBox.confirm('这一天的文字还没有保存。', '离开编辑', { confirmButtonText: '放弃修改', cancelButtonText: '继续编辑' }); return true } catch { return false }
}
async function edit(day: ChapterDay) { if (!await canLeave()) return; editing.value = day.day; editText.value = originalText.value = caption(day); saveError.value = ''; mobileEditor.value = true }
async function cancelEdit() { if (await canLeave()) { editing.value = ''; mobileEditor.value = false } }
async function save(day: ChapterDay) {
  saving.value = true; saveError.value = ''
  try { await store.save(props.chapter.id, day.day, editText.value); editing.value = ''; mobileEditor.value = false }
  catch { saveError.value = '保存失败，你的修改仍在这里，请重试。' }
  finally { saving.value = false }
}
function openPhoto(day: ChapterDay, id: string) { emit('openPhoto', id, day.photos) }
async function showAll(day: ChapterDay) { galleryEpoch++; galleryDay.value = day.day; galleryPhotos.value = []; galleryTotal.value = day.photo_count; galleryLoading.value = false; galleryVisible.value = true; await loadGallery() }
async function loadGallery() {
  if (galleryLoading.value) return
  const request = galleryEpoch
  galleryLoading.value = true; galleryError.value = false
  try { const result = await chapterApi.dayPhotos(props.chapter.id, galleryDay.value, galleryPhotos.value.length); if (request === galleryEpoch) { galleryPhotos.value.push(...result.items); galleryTotal.value = result.total } }
  catch { if (request === galleryEpoch) galleryError.value = true }
  finally { if (request === galleryEpoch) galleryLoading.value = false }
}
watch([() => props.chapter.id, year, month], () => {
  void router.replace({ query: { ...route.query, diaryYear: year.value || undefined, diaryMonth: month.value || undefined } })
  void load(false)
}, { immediate: true })
onBeforeUnmount(() => { epoch++; galleryEpoch++ })
onBeforeRouteLeave(canLeave)
defineExpose({ canLeave })
</script>

<style scoped>
.daily-book :deep(.diary-page-content) { display:flex; flex-direction:column; overflow:hidden; padding:26px 32px 48px; }
.daily-book :deep(.diary-page-content > *) { flex-shrink:0; }
.daily-book :deep(.diary-running) { margin-bottom:20px; }
.day-photo-grid { flex:1; min-height:0; grid-template-rows:minmax(0, 2fr) minmax(0, 1fr); }
.day-photo-grid.single-photo { grid-template-rows:minmax(0, 1fr); }
.day-photo-grid .day-image { width:100%; height:100%; min-height:0; }
.day-writing-area { flex:1; min-height:32px; }
.day-clues > a, .day-clues > span { max-width:120px; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
.daily-book :deep(.diary-right .day-writing-area) { flex-shrink:1; }
.daily-book :deep(.diary-right h2) { font-size:clamp(18px, 1.8vw, 24px); }
.day-mementos { margin-top:0; }
.day-mementos .day-image { height:90px; aspect-ratio:auto; }
.daily-book :deep(.diary-right .diary-page-content > *) { flex-shrink:0; }
.daily-book :deep(.diary-right .diary-running) { margin-bottom:20px; }
.day-mementos .day-image { max-height:120px; }
.day-image > :deep(div) { position: absolute; inset: 6px; width: calc(100% - 12px); height: calc(100% - 12px); }
.diary-turn { display:flex; min-height:44px; align-items:center; gap:8px; padding:8px 16px; border:1px solid #e5e7eb; border-radius:8px; font-size:13px; color:#4b5563; background:white; }
.diary-turn:disabled { opacity:.35; cursor:default; }
.dark .diary-turn { border-color:#4b5563; background:#1f2937; color:#d1d5db; }
@media(max-width:767px) {
  .daily-book :deep(.is-mobile-hidden) { display: none; }
  
  .daily-book :deep(.diary-right) { border-top: 0; }
  .daily-pagination { padding:8px 0; }
  .day-image.col-span-full { max-height:200px; }
  .diary-turn { padding:8px 10px; }
}
</style>
