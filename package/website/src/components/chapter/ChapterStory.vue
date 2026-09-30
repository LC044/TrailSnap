<template>
  <section class="diary-reader mt-6 outline-none" tabindex="0" aria-label="影像日记本，支持左右方向键翻页" @keydown="onKeydown">
    <div class="mb-5 flex flex-wrap items-center justify-between gap-3">
      <p class="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400"><BookOpen :size="17" />影像日记本<span class="hidden sm:inline">· {{ chapter.years.length }} 个年份，慢慢翻阅</span></p>
      <button class="flex min-h-11 items-center gap-2 rounded-lg px-3 text-sm text-primary-600 hover:bg-primary-50 dark:text-primary-400 dark:hover:bg-primary-900/20" @click="$emit('write', selectedYear)"><Feather :size="16" />{{ selectedYear ? '写这一年的日记' : '写扉页简介' }}</button>
    </div>
    <nav class="sticky top-0 z-10 mb-5 flex gap-1 overflow-x-auto bg-gray-50/95 py-2 backdrop-blur dark:bg-gray-900/95" aria-label="日记年份目录">
      <button v-for="year in [null, ...chapter.years]" :key="year ?? 'cover'" class="min-h-11 shrink-0 rounded-lg px-4 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" :class="selectedYear === year ? 'bg-primary-500 text-white' : 'text-gray-600 hover:bg-primary-50 dark:text-gray-300 dark:hover:bg-primary-900/20'" :aria-current="selectedYear === year ? 'page' : undefined" :disabled="bookBusy" @click="$emit('selectYear', year)">{{ year ?? '扉页' }}</button>
    </nav>
    <ChapterBook id="chapter-year-content" :title="chapter.title" :ready="!loading" @busy="bookBusy = $event" class="scroll-mt-6" :page-key="selectedYear ?? 'cover'" :direction="turnDirection" :cover="selectedYear === null" :aria-busy="loading && selectedYear !== null">
        <section class="diary-page diary-left">
          <div class="diary-page-content"><div class="diary-running"><span>行影集 · 人生章节</span><span>{{ selectedYear || dateRange }}</span></div>
          <template v-if="selectedYear === null">
            <figure class="diary-cover-photo">
              <div class="diary-tape" aria-hidden="true" />
              <div class="aspect-[4/5] overflow-hidden bg-gray-100 dark:bg-gray-800"><DiaryPhoto v-if="chapter.cover_photo_id" :id="chapter.cover_photo_id" :alt="chapter.title + '的封面'" size="medium" :contain="true" /><div v-else class="flex h-full min-h-64 items-center justify-center gap-2 text-sm text-gray-500 dark:text-gray-400"><Image :size="22" />为这段时光选一张封面</div></div>
              <figcaption class="mt-4 text-center font-serif text-xs text-gray-500 dark:text-gray-400">{{ chapter.title }} · 时光留在照片里</figcaption>
            </figure>
            <p class="mt-6 text-center text-xs leading-6 text-gray-500 dark:text-gray-400">{{ chapter.photo_count }} 张影像，{{ chapter.event_count }} 段记忆<br />按拍摄日期收录，后续照片会继续汇入。</p>
          </template>
          <template v-else>
            <div class="mb-5 flex items-end justify-between gap-3"><h2 class="font-serif text-5xl text-gray-900 dark:text-gray-100">{{ selectedYear }}</h2><span class="pb-1 text-xs text-gray-500 dark:text-gray-400">{{ loading ? '正在整理…' : photoTotal + ' 张影像' }}</span></div>
            <div v-if="loading" class="aspect-[4/3] animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
            <div v-else-if="error" class="flex min-h-72 flex-col items-center justify-center gap-4 text-sm text-gray-500 dark:text-gray-400">这一年的影像暂时无法打开<button class="min-h-11 rounded-lg border border-primary-200 px-4 text-primary-600 dark:border-primary-800 dark:text-primary-400" @click="$emit('retry')">重新加载</button></div>
            <template v-else-if="photos.length">
              <figure class="diary-photo-frame">
                <button class="block aspect-[4/3] w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" :aria-label="'查看 ' + photoDate(photos[0]) + ' 的照片'" @click="$emit('openPhoto', photos[0].id)"><DiaryPhoto :id="photos[0].id" :alt="photos[0].filename" size="medium" :contain="true" /></button>
                <figcaption class="mt-3 flex justify-between text-xs text-gray-500 dark:text-gray-400"><span>{{ photoDate(photos[0]) }}</span><span>{{ photos[0].file_type === 'video' ? '视频画面' : '这一年的一帧' }}</span></figcaption>
              </figure>
              <div class="mt-5 grid grid-cols-2 gap-4"><figure v-for="photo in photos.slice(1, 3)" :key="photo.id" class="diary-small-photo"><button class="block aspect-[4/3] w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" :aria-label="'查看 ' + photoDate(photo) + ' 的照片'" @click="$emit('openPhoto', photo.id)"><DiaryPhoto :id="photo.id" :alt="photo.filename" /></button><figcaption class="mt-2 text-center text-[11px] text-gray-500 dark:text-gray-400">{{ photoDate(photo) }}</figcaption></figure></div>
            </template>
            <div v-else class="flex min-h-72 items-center justify-center border border-dashed border-gray-300 px-6 text-center text-sm leading-7 text-gray-500 dark:border-gray-600 dark:text-gray-400">这一年还没有有效影像。<br />写下的日记会保留在这里。</div>
          </template>
          </div><span class="diary-page-number" aria-hidden="true">{{ String(pageIndex * 2 + 1).padStart(2, '0') }}</span>
        </section>
        <section class="diary-page diary-right">
          <div class="diary-page-content"><div class="diary-running"><span>{{ selectedYear ? '这一年的故事' : '写在时光的前面' }}</span><Feather :size="14" /></div>
          <template v-if="selectedYear === null">
            <p class="mb-4 text-xs tracking-widest text-primary-600 dark:text-primary-400">我的影像日记</p>
            <h1 class="break-words font-serif text-3xl leading-snug text-gray-900 dark:text-gray-100 sm:text-4xl">{{ chapter.title }}</h1>
            <p class="mt-4 text-xs text-gray-500 dark:text-gray-400">{{ dateRange }}</p>
            <div class="diary-writing mt-7"><p class="whitespace-pre-wrap break-words font-serif text-base leading-8 text-gray-700 dark:text-gray-200">{{ chapter.summary || '这本日记收录了 ' + chapter.photo_count + ' 张影像。沿着年份翻阅，重看照片里的片刻，也为这些日子留下自己的文字。' }}</p></div>
            <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">{{ chapter.summary ? chapter.summary_source === 'ai' ? 'AI 起草 · 已保存' : '你写在扉页上的话' : '根据照片整理 · 可以手写或让 AI 起草简介' }}</p>
            <div class="mt-8"><h2 class="mb-3 flex items-center gap-2 font-serif text-lg text-gray-900 dark:text-gray-100"><BookOpen :size="17" />翻开这一章</h2><button v-for="year in chapter.years" :key="year" class="flex min-h-12 w-full items-center gap-4 border-b border-gray-200 py-3 text-left text-sm hover:text-primary-600 dark:border-gray-700 dark:hover:text-primary-400" @click="$emit('selectYear', year)"><span class="font-serif text-lg text-primary-600 dark:text-primary-400">{{ year }}</span><span class="min-w-0 flex-1 truncate text-gray-700 dark:text-gray-200">{{ chapter.diary_entries?.[String(year)]?.title || '照片与记忆' }}</span><ArrowRight :size="15" /></button><p v-if="!chapter.years.length" class="text-sm leading-7 text-gray-500 dark:text-gray-400">这段时间还没有照片，先为日记写个开头吧。</p></div>
          </template>
          <template v-else>
            <p class="mb-3 text-xs tracking-widest text-primary-600 dark:text-primary-400">{{ selectedYear }} · 岁月的一页</p>
            <h2 class="break-words font-serif text-2xl leading-snug text-gray-900 dark:text-gray-100 sm:text-3xl">{{ entry?.title || selectedYear + ' 年的影像与记忆' }}</h2>
            <div class="diary-writing mt-5"><p v-if="entry?.body" class="whitespace-pre-wrap break-words font-serif text-base leading-8 text-gray-700 dark:text-gray-200">{{ entry.body }}</p><p v-else class="font-serif text-base leading-8 text-gray-500 dark:text-gray-400">{{ loading ? '正在翻开这一年的照片……' : photoTotal ? '这一年留下了 ' + photoTotal + ' 张影像' + (eventTotal ? '，还有 ' + eventTotal + ' 段已确认的记忆' : '') + '。从左页的照片开始回看，挑一个片刻，为这一年留几句话。' : '照片之外，也可以记下你想留住的这一年。' }}</p></div>
            <div class="mt-3 flex flex-wrap items-center justify-between gap-2"><p class="text-xs text-gray-500 dark:text-gray-400">{{ entry?.body ? entry.source === 'ai' ? 'AI 起草 · 已保存' : '你写下的年度日记' : '这一页等你来写' }}</p><button class="flex min-h-11 items-center gap-1 text-sm text-primary-600 dark:text-primary-400" @click="$emit('write', selectedYear)"><Feather :size="15" />{{ entry?.body ? '修改文字' : '手写 / AI 起草' }}</button></div>
            <div v-if="photos.length > 3 && !loading" class="mt-5 grid grid-cols-3 gap-2"><button v-for="photo in photos.slice(3, 6)" :key="photo.id" class="diary-small-photo aspect-square focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" :aria-label="'查看 ' + photoDate(photo) + ' 的照片'" @click="$emit('openPhoto', photo.id)"><DiaryPhoto :id="photo.id" :alt="photo.filename" /></button></div>
            <div v-if="events.length && !loading" class="mt-6"><h3 class="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">记得这些片刻吗</h3><RouterLink v-for="event in events.slice(0, 3)" :key="event.id" :to="'/memories/' + event.id" class="flex min-h-11 items-center justify-between gap-3 border-b border-gray-200 py-2 text-sm text-gray-700 hover:text-primary-600 dark:border-gray-700 dark:text-gray-200 dark:hover:text-primary-400"><span class="line-clamp-2">{{ event.title }}</span><ArrowRight :size="14" class="shrink-0" /></RouterLink></div>
            <button v-if="photoTotal && !loading" class="mt-6 flex min-h-11 items-center gap-2 text-sm text-primary-600 dark:text-primary-400" :aria-expanded="galleryOpen" @click="galleryOpen = !galleryOpen"><Images :size="16" />{{ galleryOpen ? '收起全部影像' : '查看这一年的全部 ' + photoTotal + ' 张影像' }}<ChevronDown :size="15" :class="galleryOpen ? 'rotate-180' : ''" /></button>
          </template>
          </div><span class="diary-page-number" aria-hidden="true">{{ String(pageIndex * 2 + 2).padStart(2, '0') }}</span>
        </section>
    </ChapterBook>
    <div class="mt-5 flex items-center justify-between gap-2">
      <button class="diary-turn" :disabled="pageIndex === 0 || bookBusy" @click="turn(-1)"><ArrowLeft :size="17" /><span>上一页</span></button>
      <span class="text-center text-xs text-gray-500 dark:text-gray-400">{{ selectedYear ?? '扉页' }} · {{ pageIndex + 1 }} / {{ chapter.years.length + 1 }}</span>
      <button class="diary-turn" :disabled="pageIndex === chapter.years.length || bookBusy" @click="turn(1)"><span>下一页</span><ArrowRight :size="17" /></button>
    </div>
    <section v-if="galleryOpen && selectedYear" class="mt-8 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800 sm:p-6" aria-label="年度全部影像">
      <h3 class="mb-4 font-serif text-xl text-gray-900 dark:text-white">{{ selectedYear }} · 全部影像</h3>
      <div class="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6"><button v-for="photo in galleryPhotos" :key="photo.id" class="aspect-square overflow-hidden rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" :aria-label="'查看 ' + photoDate(photo) + ' 的照片'" @click="$emit('openPhoto', photo.id)"><DiaryPhoto :id="photo.id" :alt="photo.filename" /></button></div>
      <button v-if="hasMorePhotos" class="mt-4 min-h-11 rounded-lg border border-primary-200 px-4 text-sm text-primary-600 disabled:opacity-50 dark:border-primary-800 dark:text-primary-400" :disabled="loadingMore" @click="$emit('morePhotos')">{{ loadingMore ? '正在加载…' : '继续浏览（已载入 ' + galleryPhotos.length + ' / ' + photoTotal + '）' }}</button>
      <div v-if="events.length > 3" class="mt-6"><h3 class="mb-2 text-sm text-gray-700 dark:text-gray-200">这一年的全部记忆</h3><RouterLink v-for="event in events.slice(3)" :key="event.id" :to="'/memories/' + event.id" class="block min-h-11 py-2 text-sm text-primary-600 dark:text-primary-400">{{ event.title }} →</RouterLink></div>
      <button v-if="eventTotal > events.length" class="mt-3 min-h-11 text-sm text-primary-600 dark:text-primary-400" @click="$emit('moreEvents')">查看更多记忆</button>
    </section>
    <section class="mt-10 border-t border-gray-200 pt-6 dark:border-gray-700">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-2"><h2 class="font-serif text-xl text-gray-900 dark:text-gray-100">日记里的线索</h2><p class="text-xs text-gray-500 dark:text-gray-400">人物和地点来自章内照片记录</p></div>
      <div class="grid gap-4 sm:grid-cols-2">
        <div class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800"><h3 class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200"><Users :size="16" />照片里的人</h3><div v-if="chapter.people.length" class="mt-3 flex flex-wrap gap-2"><RouterLink v-for="person in chapter.people.slice(0, 6)" :key="person.id" :to="'/album/people/' + person.id" class="min-h-11 rounded-full bg-gray-50 px-3 py-2.5 text-xs text-gray-700 dark:bg-gray-900 dark:text-gray-200">{{ person.name }} · {{ person.photo_count }} 张</RouterLink></div><p v-else class="mt-3 text-xs text-gray-500 dark:text-gray-400">还没有已识别的人物</p></div>
        <div class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800"><h3 class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200"><MapPin :size="16" />记录过的地方</h3><div v-if="chapter.places.length" class="mt-3 flex flex-wrap gap-2"><RouterLink v-for="place in chapter.places.slice(0, 4)" :key="place.name" :to="{ path: '/album/location/' + encodeURIComponent(place.name.split(' · ').at(-1) || place.name), query: { level: 'city', startDate: chapter.start_date, ...(chapter.end_date ? { endDate: chapter.end_date } : {}) } }" class="min-h-11 rounded-full bg-gray-50 px-3 py-2.5 text-xs text-gray-700 dark:bg-gray-900 dark:text-gray-200">{{ place.name }}</RouterLink></div><p v-else class="mt-3 text-xs text-gray-500 dark:text-gray-400">还没有照片定位</p></div>
      </div>
    </section>
  </section>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight, BookOpen, ChevronDown, Feather, Image, Images, MapPin, Users } from 'lucide-vue-next'
import DiaryPhoto from './DiaryPhoto.vue'
import ChapterBook from './ChapterBook.vue'
import type { ChapterDetail, ChapterEvent, ChapterPhoto } from '@/types/chapter'
const props = defineProps<{ chapter: ChapterDetail; selectedYear: number | null; photos: ChapterPhoto[]; galleryPhotos: ChapterPhoto[]; events: ChapterEvent[]; photoTotal: number; hasMorePhotos: boolean; eventTotal: number; loading: boolean; loadingMore: boolean; error: boolean }>()
const emit = defineEmits<{ selectYear: [year: number | null]; openPhoto: [id: string]; morePhotos: []; moreEvents: []; retry: []; write: [year: number | null] }>()
const galleryOpen = ref(false)
const bookBusy = ref(false)
const turnDirection = ref(1)
const pageIndex = computed(() => props.selectedYear === null ? 0 : props.chapter.years.indexOf(props.selectedYear) + 1)
const entry = computed(() => props.selectedYear ? props.chapter.diary_entries?.[String(props.selectedYear)] : undefined)
const dateRange = computed(() => props.chapter.start_date.slice(0, 7).replace('-', '.') + ' — ' + (props.chapter.end_date?.slice(0, 7).replace('-', '.') || '至今'))
watch(pageIndex, (value, previous) => { turnDirection.value = value >= previous ? 1 : -1; galleryOpen.value = false })
function photoDate(photo: ChapterPhoto) { return photo.photo_time.slice(0, 10).replaceAll('-', '.') }
function turn(direction: number) {
  if (bookBusy.value) return
  const index = pageIndex.value + direction
  if (index >= 0 && index <= props.chapter.years.length) emit('selectYear', index === 0 ? null : props.chapter.years[index - 1])
}
function onKeydown(event: KeyboardEvent) {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || (event.target as HTMLElement).closest('input,textarea,select,[contenteditable="true"]')) return
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); turn(event.key === 'ArrowLeft' ? -1 : 1) }
}
</script>
