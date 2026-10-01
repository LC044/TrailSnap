<template>
  <div class="relative min-w-0 md:w-40 md:flex-shrink-0 md:snap-start">
    <div class="relative aspect-square cursor-pointer overflow-hidden rounded-xl border-2 bg-gray-100 transition-colors dark:bg-gray-700" :class="selected || highlighted ? 'border-primary-500' : 'border-transparent'" role="button" tabindex="0" :aria-label="`查看 ${photo.filename}`" @click="$emit('open')" @keydown.enter="$emit('open')">
      <img :src="photo.thumbnail" :alt="photo.filename" class="h-full w-full object-cover transition-transform duration-300 hover:scale-105" loading="lazy" />
      <div v-if="badge" class="absolute bottom-1 left-1 rounded bg-green-500/90 px-1.5 py-0.5 text-[10px] text-white shadow-sm backdrop-blur-sm">{{ badge }}</div>
      <button type="button" :aria-label="`${selected ? '取消选择' : '选择'} ${photo.filename}`" :aria-pressed="selected" class="absolute left-1.5 top-1.5 z-10 flex h-7 w-7 items-center justify-center rounded-full border-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white" :class="selected ? 'border-primary-500 bg-primary-500' : 'border-white bg-black/30 hover:bg-black/50'" @click.stop="$emit('toggle')" @keydown.enter.stop>
        <i v-if="selected" class="mgc_check_line text-sm text-white" />
      </button>
      <div v-if="photo.file_type === 'video'" class="pointer-events-none absolute right-2 top-1 z-10 flex items-center text-sm text-white">{{ photo.duration }}<PlayCircle class="h-4 w-4 drop-shadow-md" /></div>
      <span v-else-if="photo.file_type === 'live_photo'" class="icon-[tabler--live-photo] pointer-events-none absolute right-2 top-2 z-10 h-4 w-4 text-white drop-shadow-md" />
    </div>
    <div class="mt-1.5 px-1"><div class="truncate text-left text-xs font-medium text-gray-700 dark:text-gray-300">{{ photo.filename }}</div><slot /></div>
    <div v-if="showPath && photo.file_path" :title="photo.file_path" class="truncate px-1 text-left text-[11px] text-gray-500 dark:text-gray-400">{{ photo.file_path }}</div>
  </div>
</template>
<script setup lang="ts">
import { PlayCircle } from 'lucide-vue-next'
import type { AlbumImage } from '@/types/album'
withDefaults(defineProps<{ photo: AlbumImage; selected: boolean; highlighted?: boolean; badge?: string; showPath?: boolean }>(), { highlighted: false, badge: '', showPath: false })
defineEmits<{ open: []; toggle: [] }>()
</script>
