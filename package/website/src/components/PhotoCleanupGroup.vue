<template>
  <div class="rounded-2xl border border-gray-200/80 bg-white p-3 shadow-sm dark:border-gray-700 dark:bg-gray-800 md:p-4">
    <div class="mb-3 flex items-center justify-between gap-2">
      <span class="text-sm font-medium text-gray-600 dark:text-gray-300">{{ title }} ({{ photos.length }} 张)</span>
      <div class="flex items-center gap-1.5 sm:gap-3">
        <slot name="actions" />
        <button type="button" class="min-h-9 rounded-lg px-2 text-sm font-medium text-primary-600 transition-colors hover:bg-primary-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-primary-400 dark:hover:bg-primary-900/20" @click="$emit('toggle-group')">{{ allSelected ? '取消全选' : selectLabel }}</button>
      </div>
    </div>
    <div class="group/scroll relative">
      <button v-if="canScrollLeft" aria-label="向左滚动照片" class="absolute left-0 top-1/2 z-10 hidden -translate-y-1/2 items-center rounded-full bg-white/90 p-2 text-gray-700 shadow-md opacity-0 transition-opacity group-hover/scroll:opacity-100 dark:bg-gray-700/90 dark:text-gray-200 md:flex" @click="scroll(-1)"><i class="mgc_left_line" /></button>
      <button v-if="canScrollRight" aria-label="向右滚动照片" class="absolute right-0 top-1/2 z-10 hidden -translate-y-1/2 items-center rounded-full bg-white/90 p-2 text-gray-700 shadow-md opacity-0 transition-opacity group-hover/scroll:opacity-100 dark:bg-gray-700/90 dark:text-gray-200 md:flex" @click="scroll(1)"><i class="mgc_right_line" /></button>
      <div ref="container" class="grid grid-cols-2 gap-3 px-0.5 py-1 md:flex md:snap-x md:snap-mandatory md:gap-4 md:overflow-x-auto md:px-1 md:py-2" @scroll="update">
        <SelectablePhotoCard v-for="(photo, index) in photos" :key="photo.id" :photo="photo" :selected="selectedIds.has(photo.id)" :highlighted="highlightedIds?.has(photo.id)" :badge="index === 0 ? firstBadge : ''" :show-path="showPaths" @open="$emit('open-photo', index)" @toggle="$emit('toggle-photo', photo.id)">
          <slot name="photo-actions" :photo="photo" />
        </SelectablePhotoCard>
      </div>
    </div>
    <div v-if="selectedCount > 0" class="mt-3 flex justify-end border-t border-gray-100 pt-3 dark:border-gray-700">
      <button type="button" class="flex items-center gap-1 rounded-md bg-red-50 px-3 py-1.5 text-xs text-red-500 transition-colors hover:bg-red-100 dark:bg-red-900/20 dark:hover:bg-red-900/40" @click="$emit('delete-selection')"><i class="mgc_delete_2_line" />删除选中 ({{ selectedCount }}张)</button>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, watch } from 'vue'
import type { AlbumImage } from '@/types/album'
import SelectablePhotoCard from './SelectablePhotoCard.vue'
import { useHorizontalScroll } from '@/composables/useHorizontalScroll'
const props = withDefaults(defineProps<{
  title: string; photos: AlbumImage[]; selectedIds: ReadonlySet<string>; allSelected: boolean
  selectLabel?: string; firstBadge?: string; showPaths?: boolean; highlightedIds?: ReadonlySet<string>
}>(), { selectLabel: '全选', firstBadge: '', showPaths: false })
defineEmits<{ 'toggle-group': []; 'toggle-photo': [id: string]; 'open-photo': [index: number]; 'delete-selection': [] }>()
const selectedCount = computed(() => props.photos.filter(photo => props.selectedIds.has(photo.id)).length)
const { container, canScrollLeft, canScrollRight, update, scroll } = useHorizontalScroll()
watch(() => props.photos.length, () => nextTick(update), { immediate: true })
</script>
