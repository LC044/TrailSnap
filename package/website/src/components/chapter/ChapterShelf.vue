<template>
  <section class="mt-7">
    <div class="mb-4 flex items-center justify-between"><div><h2 class="font-serif text-xl text-gray-900 dark:text-white">人生章节</h2><p class="mt-1 text-xs text-gray-500 dark:text-gray-400">把多年照片，翻成自己的日记本。</p></div><RouterLink to="/chapters" class="text-sm text-primary-600 dark:text-primary-400">查看全部 →</RouterLink></div>
    <div v-if="loading" class="h-44 animate-pulse rounded-xl bg-gray-200 dark:bg-gray-800" />
    <div v-else-if="items.length" class="relative">
      <div ref="shelf" class="flex snap-x snap-mandatory gap-4 overflow-x-auto pb-3" @scroll.passive="rememberPosition">
      <RouterLink v-for="item in items" :key="item.id" :to="`/chapters/${item.id}`" class="group relative h-56 min-w-[74%] snap-start overflow-hidden rounded-xl bg-gray-200 shadow-sm dark:bg-gray-800 sm:min-w-[32%]">
        <img v-if="item.cover_photo_id" :src="thumbnailUrl(item.cover_photo_id, 'medium')" :alt="item.title" class="h-full w-full object-cover transition group-hover:scale-105" loading="lazy" />
        <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent p-5 pt-16 text-white"><p class="text-xs">{{ item.start_date }} — {{ item.end_date || '至今' }}</p><h3 class="mt-1 font-serif text-xl">{{ item.title }}</h3><p class="mt-1 text-xs text-gray-200">{{ item.photo_count }} 张影像 · {{ item.event_count }} 段事件</p></div>
      </RouterLink>
      </div>
      <div v-if="items.length > 1" class="mt-1 flex justify-end gap-2"><button class="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200" aria-label="向前浏览章节" @click="scrollShelf(-1)">←</button><button class="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200" aria-label="向后浏览章节" @click="scrollShelf(1)">→</button></div>
    </div>
    <RouterLink v-else to="/chapters" class="block rounded-xl border border-dashed border-primary-200 bg-primary-50 p-6 text-sm text-primary-700 dark:border-primary-800 dark:bg-primary-900/20 dark:text-primary-300">给这些年的照片写一个目录　→</RouterLink>
    <RouterLink v-if="candidateCount" to="/chapters?tab=candidate" class="mt-2 block text-sm text-primary-600 dark:text-primary-400">有 {{ candidateCount }} 条章节建议，等你定义这些阶段 →</RouterLink>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { chapterApi } from '@/api/chapter'
import { thumbnailUrl } from '@/utils/mediaUrl'
import type { ChapterItem } from '@/types/chapter'

const items = ref<ChapterItem[]>([])
const candidateCount = ref(0)
const loading = ref(true)
const shelf = ref<HTMLElement | null>(null)
function rememberPosition() { if (shelf.value) sessionStorage.setItem('chapter-shelf-scroll', String(shelf.value.scrollLeft)) }
function scrollShelf(direction: number) { shelf.value?.scrollBy({ left: direction * (shelf.value.clientWidth * .8), behavior: 'smooth' }) }
onMounted(async () => {
  try { items.value = (await chapterApi.list('confirmed', false, 0, 8)).items }
  catch { items.value = [] }
  try { candidateCount.value = (await chapterApi.list('candidate', false, 0, 1)).total }
  catch { candidateCount.value = 0 }
  finally { loading.value = false }
  await nextTick()
  if (shelf.value) shelf.value.scrollLeft = Number(sessionStorage.getItem('chapter-shelf-scroll') || 0)
})
</script>
