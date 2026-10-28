<template>
  <section ref="root" class="photo-time-overview grid grid-cols-1 gap-3 pb-8 md:grid-cols-3 md:gap-5 lg:grid-cols-4" :aria-label="granularity === 'year' ? '年视图' : '月视图'">
    <button v-for="bucket in buckets" :key="bucket.key" type="button"
      class="time-bucket ts-surface group relative aspect-[16/9] overflow-hidden md:aspect-[4/3] text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
      :class="{ 'ring-2 ring-primary-500': isAnchorBucket(bucket) }"
      :data-time-anchor="isAnchorBucket(bucket)" :data-time-bucket="bucket.key" :data-photo-id="cover(bucket).id"
      :aria-label="`${label(bucket)}，${bucket.count} 张照片，点击查看${granularity === 'year' ? '月份' : '照片'}`"
      @click="$emit('select', cover(bucket))">
      <img :src="cover(bucket).thumbnail" alt="" loading="lazy" decoding="async" class="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105 motion-reduce:transition-none" />
      <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-black/5 to-transparent" />
      <div class="absolute inset-x-0 bottom-0 p-3 text-white sm:p-4">
        <p class="text-xl font-semibold sm:text-2xl">{{ label(bucket) }}</p>
        <p class="mt-1 text-sm text-white/80">{{ bucket.count.toLocaleString() }} 张照片</p>
      </div>
    </button>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AlbumImage, TimelineMonth } from '@/types/album'
import { overviewBuckets, timelineParts } from '@/utils/photoTimeline'

const props = defineProps<{
  months: TimelineMonth[]
  granularity: 'year' | 'month'
  anchor: AlbumImage | null
  mapPhoto: (photo: TimelineMonth['cover']) => AlbumImage
}>()
defineEmits<{ (e: 'select', photo: AlbumImage): void }>()
const root = ref<HTMLElement | null>(null)
const buckets = computed(() => overviewBuckets(props.months, props.granularity))
const isAnchorBucket = (bucket: TimelineMonth) => {
  if (!props.anchor) return false
  const parts = timelineParts(props.anchor.timestamp)
  return parts.year === bucket.year && (props.granularity === 'year' || parts.month === bucket.month)
}
const cover = (bucket: TimelineMonth) => isAnchorBucket(bucket) && props.anchor ? props.anchor : props.mapPhoto(bucket.cover)
const label = (bucket: TimelineMonth) => !bucket.year ? '时间未知' : props.granularity === 'year' ? `${bucket.year}年` : `${bucket.year}年${bucket.month}月`
const capture = () => {
  const main = document.querySelector('main')
  const top = (main?.getBoundingClientRect().top ?? 0) + 70
  const elements = [...(root.value?.querySelectorAll<HTMLElement>('[data-time-bucket]') ?? [])]
  const current = elements.find(el => el.dataset.timeAnchor === 'true')
  const anchored = current && current.getBoundingClientRect().bottom > top && current.getBoundingClientRect().top < window.innerHeight ? current : null
  const element = anchored ?? elements.find(el => el.getBoundingClientRect().top >= top && el.getBoundingClientRect().top < window.innerHeight)
    ?? elements.find(el => el.getBoundingClientRect().bottom > top)
  const bucket = buckets.value.find(item => item.key === element?.dataset.timeBucket)
  return bucket ? cover(bucket) : props.anchor
}
const locate = (year: number, month: number, focus = true) => {
  const key = props.granularity === 'year' ? String(year) : `${year}-${month}`
  const element = root.value?.querySelector<HTMLElement>(`[data-time-bucket="${CSS.escape(key)}"]`)
  if (!element) return
  const main = document.querySelector('main')
  const header = document.querySelector<HTMLElement>('.unified-photo-page [data-photo-header]')
  const top = (main?.getBoundingClientRect().top ?? 0) + (header?.offsetHeight ?? 80) + 12
  main?.scrollBy({ top: element.getBoundingClientRect().top - top, behavior: 'auto' })
  if (focus) element.focus({ preventScroll: true })
}
defineExpose({ capture, locate })
</script>

<style scoped>
.time-bucket[data-time-anchor="true"] { outline: 2px solid var(--theme-primary); outline-offset: 3px; }
.time-bucket { content-visibility: auto; contain-intrinsic-size: auto 240px; }
</style>
