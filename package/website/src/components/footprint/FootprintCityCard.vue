<template>
  <button
    type="button"
    class="ts-surface group block w-full overflow-hidden rounded-2xl text-left transition-shadow hover:shadow-[var(--ts-shadow-floating)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
    :aria-label="`查看${city.name}的足迹详情`"
    data-testid="footprint-city-card"
    @click="emit('open', city)"
  >
    <div class="relative aspect-video w-full overflow-hidden bg-gray-100 dark:bg-gray-800">
      <img
        v-if="city.cover_id"
        :src="thumbnailUrl(city.cover_id, 'medium')"
        :alt="`${city.name}的旅行记忆`"
        class="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
        loading="lazy"
      />
      <div v-else class="flex h-full w-full items-center justify-center" aria-hidden="true">
        <MapPin class="h-10 w-10 text-gray-300 dark:text-gray-600" />
      </div>
      <span class="absolute bottom-2 left-2 rounded-full bg-black/55 px-2.5 py-1 text-xs font-medium text-white backdrop-blur-sm">
        {{ format(city.photo_count) }} 张照片
      </span>
    </div>
    <div class="p-4">
      <div class="flex items-center justify-between gap-2">
        <h2 class="ts-card-title truncate text-gray-900 dark:text-white">{{ city.name }}</h2>
        <ChevronRight class="h-4 w-4 shrink-0 text-gray-300 transition-colors group-hover:text-primary-500 dark:text-gray-600" aria-hidden="true" />
      </div>
      <p class="mt-2 flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
        <CalendarDays class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span class="truncate">{{ dateLabel(city.first_at) }} — {{ dateLabel(city.last_at) }}</span>
      </p>
      <p class="mt-1.5 flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
        <MapPin class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span class="truncate">{{ region || '地点未知' }}</span>
      </p>
      <div class="mt-3 flex items-center gap-4 border-t border-gray-100 pt-3 text-xs dark:border-gray-800">
        <span class="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
          <Footprints class="h-3.5 w-3.5 text-primary-500" aria-hidden="true" />
          {{ format(city.visit_count) }} 次到访
        </span>
        <span class="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
          <Images class="h-3.5 w-3.5 text-primary-500" aria-hidden="true" />
          {{ format(city.photo_count) }} 张照片
        </span>
      </div>
    </div>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CalendarDays, ChevronRight, Footprints, Images, MapPin } from 'lucide-vue-next'
import { thumbnailUrl } from '@/utils/mediaUrl'
import type { FootprintCity } from '@/types/footprint'

const props = defineProps<{ city: FootprintCity }>()
const emit = defineEmits<{ open: [city: FootprintCity] }>()

const region = computed(() => [props.city.province, props.city.country].filter(Boolean).join(' · '))
const format = (value?: number) => (value || 0).toLocaleString('zh-CN')
const dateLabel = (value: string | null) => value ? value.slice(0, 10).replaceAll('-', '.') : '时间未知'
</script>