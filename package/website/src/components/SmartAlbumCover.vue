<template>
  <div class="relative h-full w-full overflow-hidden bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-800 dark:to-gray-900">
    <div v-if="loading" class="absolute inset-0 animate-pulse bg-gray-200/70 dark:bg-gray-800/70"></div>

    <component
      v-else-if="!hasContent"
      :is="icon"
      class="absolute left-1/2 top-1/2 h-[45%] w-[45%] -translate-x-1/2 -translate-y-1/2 text-gray-400 transition-colors duration-300 group-hover:text-primary-500"
      stroke-width="1.5"
    />

    <div v-else class="grid h-full w-full gap-px bg-gray-200 dark:bg-gray-800" :class="gridClass">
      <div
        v-for="(item, index) in displayRepresentatives"
        :key="`${item.entity_id}-${index}`"
        class="relative overflow-hidden bg-gray-100 dark:bg-gray-800"
      >
        <img
          v-if="item.photo_id"
          :src="thumbnailUrl(item.photo_id, 'medium')"
          :alt="`${altPrefix}：${item.name}`"
          :class="type === 'people' ? 'absolute max-w-none' : 'h-full w-full object-cover transition-transform duration-500 group-hover:scale-105'"
          :style="type === 'people' ? getFaceCropStyle(item) : undefined"
          loading="lazy"
          decoding="async"
        />
      </div>
    </div>

    <div
      v-if="hasContent"
      class="absolute bottom-1 right-1 flex h-5 w-5 items-center justify-center rounded-full bg-black/55 text-white shadow-sm backdrop-blur-sm"
    >
      <component :is="icon" class="h-3 w-3" stroke-width="2" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import type { SmartAlbumRepresentative, SmartAlbumSection } from '@/api/album'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { getFaceCropStyle } from '@/utils/faceCrop'

const props = withDefaults(defineProps<{
  type: 'people' | 'location' | 'classification'
  icon: Component
  data?: SmartAlbumSection | null
  loading?: boolean
  altPrefix?: string
}>(), {
  data: null,
  loading: false,
  altPrefix: '智能相册封面',
})

const availableRepresentatives = computed<SmartAlbumRepresentative[]>(() =>
  (props.data?.representatives ?? []).filter(item => item.photo_id),
)

const hasContent = computed(() => availableRepresentatives.value.length > 0)

const displayRepresentatives = computed<SmartAlbumRepresentative[]>(() => {
  const items = availableRepresentatives.value.slice(0, 4)
  // A three-item mosaic would leave a visible empty cell; repeat the first item.
  if (items.length === 3) return [...items, items[0]]
  return items
})

const gridClass = computed(() => {
  if (displayRepresentatives.value.length === 1) return 'grid-cols-1'
  if (displayRepresentatives.value.length === 2) return 'grid-cols-2'
  return 'grid-cols-2 grid-rows-2'
})
</script>
