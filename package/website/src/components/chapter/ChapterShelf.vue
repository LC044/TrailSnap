<template>
  <section class="chapter-shelf" aria-labelledby="chapter-shelf-title">
    <header>
      <h2 id="chapter-shelf-title">人生章节</h2>
      <div class="chapter-shelf-links">
        <RouterLink v-if="candidateCount" to="/chapters?tab=candidate" class="chapter-shelf-suggestions">{{ candidateCount }} 条章节建议</RouterLink>
        <RouterLink to="/chapters">查看全部<ChevronRight aria-hidden="true" /></RouterLink>
      </div>
    </header>
    <div v-if="loading" class="chapter-shelf-loading" role="status" aria-label="正在加载章节"></div>
    <div v-else-if="chapters.length" class="chapter-shelf-grid">
      <RouterLink v-for="(chapter, index) in chapters" :key="chapter.id" :to="`/chapters/${chapter.id}`" class="chapter-shelf-cover" :class="{ 'chapter-shelf-cover--photo': hasCover(chapter) }">
        <img v-if="hasCover(chapter)" :src="thumbnailUrl(chapter.cover_photo_id, 'medium')" :loading="index === 0 ? 'eager' : 'lazy'" alt="" @error="coverFailures.add(chapter.id)" />
        <div class="chapter-shelf-caption">
          <p v-if="!chapter.title.includes(chapterYears(chapter))">{{ chapterYears(chapter) }}</p>
          <h3>{{ chapter.title }}</h3>
          <span>{{ chapter.photo_count.toLocaleString('zh-CN') }} 张影像</span>
        </div>
        <ArrowUpRight aria-hidden="true" />
      </RouterLink>
    </div>
    <RouterLink v-else to="/chapters/new" class="chapter-shelf-empty">
      <BookOpen aria-hidden="true" />
      <span><strong>创建人生章节</strong><span>把一段岁月的照片收进属于它的日记本。</span></span>
      <ArrowUpRight aria-hidden="true" />
    </RouterLink>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowUpRight, BookOpen, ChevronRight } from 'lucide-vue-next'
import { chapterApi } from '@/api/chapter'
import { thumbnailUrl } from '@/utils/mediaUrl'
import type { ChapterItem } from '@/types/chapter'

const chapters = ref<ChapterItem[]>([])
const candidateCount = ref(0)
const loading = ref(true)
const coverFailures = ref(new Set<string>())
function hasCover(chapter: ChapterItem): chapter is ChapterItem & { cover_photo_id: string } {
  return !!chapter.cover_photo_id && !coverFailures.value.has(chapter.id)
}

function chapterYears(chapter: ChapterItem) {
  const first = chapter.start_date.slice(0, 4)
  const last = chapter.end_date?.slice(0, 4)
  return first === last ? first : `${first} — ${last || '至今'}`
}

onMounted(async () => {
  const loadChapter = chapterApi.list('confirmed', false, 0, 2)
    .then(({ items }) => { chapters.value = items })
    .finally(() => { loading.value = false })
  const loadCount = chapterApi.count('candidate')
    .then(count => { candidateCount.value = count })
  await Promise.allSettled([loadChapter, loadCount])
})
</script>

<style scoped>
.chapter-shelf header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 9px; }
.chapter-shelf h2 { font: 700 23px/1.25 var(--ts-journal-serif); }
.chapter-shelf-links { display: flex; align-items: center; gap: 12px; }
.chapter-shelf-links a { display: flex; align-items: center; gap: 4px; min-height: 44px; color: var(--ts-journal-accent-text); font-size: 13px; font-weight: 600; white-space: nowrap; }
.chapter-shelf-links .chapter-shelf-suggestions { color: var(--ts-color-text-secondary); font-size: 12px; font-weight: 400; }
.chapter-shelf a:focus-visible { outline: 2px solid var(--ts-journal-focus); outline-offset: 3px; }
.chapter-shelf a:hover { text-decoration: underline; }
.chapter-shelf svg { width: 16px; height: 16px; flex-shrink: 0; }
.chapter-shelf-grid { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: 14px; }
.chapter-shelf-cover, .chapter-shelf-loading { position: relative; display: flex; align-items: end; min-height: clamp(190px, 19vw, 270px); overflow: hidden; border-radius: 14px; background: var(--ts-color-surface-muted); }
.chapter-shelf-cover img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; transition: transform 360ms ease; }
.chapter-shelf-cover:hover img { transform: scale(1.035); }
.chapter-shelf-caption { position: relative; width: 100%; padding: 32px clamp(14px, 2vw, 28px) 18px; }
.chapter-shelf-cover--photo .chapter-shelf-caption { background: linear-gradient(to top, rgb(0 0 0 / 86%), transparent); color: white; }
.chapter-shelf-caption h3 { display: -webkit-box; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow-wrap: anywhere; font: 700 clamp(21px, 2.25vw, 31px)/1.22 var(--ts-journal-serif); }
.chapter-shelf-caption p, .chapter-shelf-caption span { font-size: 12px; }
.chapter-shelf-caption p { margin-bottom: 5px; }
.chapter-shelf-caption span { display: block; margin-top: 6px; }
.chapter-shelf-cover > svg { position: absolute; top: 10px; right: 10px; box-sizing: content-box; padding: 8px; border-radius: 9px; background: var(--ts-color-surface); color: var(--ts-color-text); }
.chapter-shelf-empty { display: flex; align-items: center; gap: 14px; min-height: 115px; padding: 16px; border: 1px dashed var(--ts-color-border); border-radius: 14px; background: var(--ts-color-surface); color: var(--ts-color-text-secondary); font-size: 13px; }
.chapter-shelf-empty > svg:first-child { width: 24px; height: 24px; color: var(--ts-journal-accent-text); }
.chapter-shelf-empty > svg:last-child { margin-left: auto; }
.chapter-shelf-empty strong { display: block; margin-bottom: 4px; color: var(--ts-color-text); font-size: 16px; font-weight: 650; }

@media (min-width: 768px) {
  .chapter-shelf-grid > .chapter-shelf-cover--photo:only-child {
    display: grid;
    grid-template-columns: minmax(0, .9fr) minmax(0, 1.4fr);
    align-items: center;
    min-height: 0;
    border: 1px solid var(--ts-color-border);
    background: var(--ts-color-surface);
  }
  .chapter-shelf-cover--photo:only-child img { position: relative; grid-area: 1 / 2; height: clamp(190px, 19vw, 270px); }
  .chapter-shelf-cover--photo:only-child .chapter-shelf-caption { grid-area: 1 / 1; background: transparent; color: var(--ts-color-text); padding-block: 20px; }
}
@media (max-width: 639px) {
  .chapter-shelf h2 { font-size: 21px; }
  .chapter-shelf-cover, .chapter-shelf-loading { min-height: 168px; }
  .chapter-shelf-grid > :not(:first-child) { display: none; }
}
@media (max-width: 359px) {
  .chapter-shelf-links { gap: 7px; }
  .chapter-shelf-links a { font-size: 12px; }
}
@media (prefers-reduced-motion: reduce) {
  .chapter-shelf-cover img { transition: none; }
}
</style>
