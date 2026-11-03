<template>
  <section class="mt-7">
    <div class="mb-4 flex items-center justify-between"><div><h2 class="font-serif text-xl text-gray-900 dark:text-white">人生章节</h2><p class="mt-1 text-xs text-gray-500 dark:text-gray-400">把多年照片，翻成自己的日记本。</p></div><RouterLink to="/chapters" class="text-sm text-primary-600 dark:text-primary-400">查看全部 →</RouterLink></div>
    <div v-if="loading" class="h-44 animate-pulse rounded-xl bg-gray-200 dark:bg-gray-800" />
    <HorizontalStrip v-else-if="items.length" ref="shelf" label="章节" strip-class="flex snap-x snap-mandatory gap-4 overflow-x-auto pb-3" @scroll="rememberPosition">
      <RouterLink v-for="item in items" :key="item.id" :to="`/chapters/${item.id}`" class="group relative h-56 min-w-[74%] snap-start overflow-hidden rounded-xl bg-gray-200 shadow-sm dark:bg-gray-800 sm:min-w-[32%]">
        <img v-if="item.cover_photo_id" :src="thumbnailUrl(item.cover_photo_id, 'medium')" :alt="item.title" class="h-full w-full object-cover transition group-hover:scale-105" loading="lazy" />
        <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent p-5 pt-16 text-white"><p class="text-xs">{{ item.start_date }} — {{ item.end_date || '至今' }}</p><h3 class="mt-1 font-serif text-xl">{{ item.title }}</h3><p class="mt-1 text-xs text-gray-200">{{ item.photo_count }} 张影像 · {{ item.event_count }} 段事件</p></div>
      </RouterLink>
    </HorizontalStrip>
    <RouterLink v-else to="/chapters" class="block rounded-xl border border-dashed border-primary-200 bg-primary-50 p-6 text-sm text-primary-700 dark:border-primary-800 dark:bg-primary-900/20 dark:text-primary-300">给这些年的照片写一个目录　→</RouterLink>
    <RouterLink v-if="candidateCount" to="/chapters?tab=candidate" class="mt-2 block text-sm text-primary-600 dark:text-primary-400">有 {{ candidateCount }} 条章节建议，等你定义这些阶段 →</RouterLink>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { chapterApi } from '@/api/chapter'
import { thumbnailUrl } from '@/utils/mediaUrl'
import type { ChapterItem } from '@/types/chapter'
import HorizontalStrip from '@/components/ui/HorizontalStrip.vue'

const items = ref<ChapterItem[]>([])
const candidateCount = ref(0)
const loading = ref(true)
const shelf = ref<InstanceType<typeof HorizontalStrip> | null>(null)
function rememberPosition(event: Event) { sessionStorage.setItem('chapter-shelf-scroll', String((event.target as HTMLElement).scrollLeft)) }
onMounted(async () => {
  await Promise.all([
    (async () => {
      try { items.value = (await chapterApi.list('confirmed', false, 0, 8)).items }
      catch { items.value = [] }
      finally { loading.value = false }
      await nextTick()
      shelf.value?.setScrollLeft(Number(sessionStorage.getItem('chapter-shelf-scroll') || 0))
    })(),
    (async () => {
      try { candidateCount.value = await chapterApi.count('candidate') }
      catch { candidateCount.value = 0 }
    })(),
  ])
})
</script>
