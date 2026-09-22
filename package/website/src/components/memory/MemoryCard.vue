<template>
  <article
    class="group overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg dark:border-gray-700 dark:bg-gray-800"
  >
    <button
      class="relative block aspect-[16/9] w-full overflow-hidden bg-gray-100 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-inset"
      :aria-label="`打开记忆：${memory.title}`"
      @click="$emit('open', memory)"
    >
      <img
        v-if="memory.cover_photo_id"
        :src="thumbnailUrl(memory.cover_photo_id, 'medium')"
        :alt="memory.title"
        class="h-full w-full object-cover transition duration-500 group-hover:scale-105"
        loading="lazy"
      />
      <div v-else class="flex h-full items-center justify-center text-gray-400 dark:text-gray-500">
        <ImageIcon class="h-10 w-10" />
      </div>
      <span
        v-if="memory.status === 'candidate'"
        class="absolute right-3 top-3 rounded-full bg-amber-100/95 px-2.5 py-1 text-xs font-semibold text-amber-800 shadow-sm dark:bg-amber-900/90 dark:text-amber-200"
      >待确认</span>
      <label v-if="selectable" class="absolute left-3 top-3" @click.stop>
        <input
          type="checkbox"
          class="h-5 w-5 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
          :checked="selected"
          :aria-label="`选择 ${memory.title}`"
          @change="$emit('toggle-select', memory.id)"
        />
      </label>
    </button>

    <div class="p-4">
      <button
        class="w-full rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
        @click="$emit('open', memory)"
      >
        <h2 class="line-clamp-1 text-lg font-bold text-gray-900 dark:text-gray-100">{{ memory.title }}</h2>
      </button>
      <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-gray-500 dark:text-gray-400">
        <span class="inline-flex items-center gap-1"><CalendarDays class="h-4 w-4" />{{ dateRange }}</span>
        <span v-if="memory.places[0]" class="inline-flex items-center gap-1"><MapPin class="h-4 w-4" />{{ memory.places[0].name }}</span>
        <span class="inline-flex items-center gap-1"><Images class="h-4 w-4" />{{ memory.photo_count }} 张</span>
      </div>

      <div v-if="memory.people.length" class="mt-3 flex items-center gap-1.5">
        <span
          v-for="person in memory.people.slice(0, 3)"
          :key="person.id"
          class="flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-primary-100 text-xs font-semibold text-primary-700 dark:border-gray-800 dark:bg-primary-900/40 dark:text-primary-300"
          :title="person.name"
        >{{ person.name.slice(0, 1) }}</span>
        <span class="ml-1 text-xs text-gray-500 dark:text-gray-400">{{ memory.people.map(item => item.name).slice(0, 3).join('、') }}</span>
      </div>

      <div
        v-if="memory.status === 'candidate' && memory.evidence[0]"
        class="mt-3 flex items-start gap-2 rounded-xl bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:bg-gray-900/60 dark:text-gray-300"
      >
        <Sparkles class="mt-0.5 h-4 w-4 shrink-0 text-primary-500" />
        <span class="line-clamp-2">{{ memory.evidence[0].summary }}</span>
      </div>

      <p v-else-if="memory.story" class="mt-3 line-clamp-2 text-sm text-gray-600 dark:text-gray-300">{{ memory.story }}</p>

      <div class="mt-4 flex items-center gap-2">
        <template v-if="memory.status === 'candidate'">
          <button class="flex-1 rounded-lg bg-primary-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="$emit('confirm', memory)">确认记忆</button>
          <button class="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="$emit('open', memory)">查看并整理</button>
          <button class="rounded-lg px-2 py-2 text-sm text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" aria-label="忽略候选" @click="$emit('ignore', memory)">忽略</button>
        </template>
        <template v-else-if="memory.status === 'ignored'">
          <button class="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="$emit('restore', memory)">恢复为待确认</button>
        </template>
        <template v-else>
          <button class="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="$emit('open', memory)">打开记忆</button>
        </template>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CalendarDays, Image as ImageIcon, Images, MapPin, Sparkles } from 'lucide-vue-next'
import type { MemoryItem } from '@/types/memory'
import { thumbnailUrl } from '@/utils/mediaUrl'

const props = withDefaults(defineProps<{
  memory: MemoryItem
  selectable?: boolean
  selected?: boolean
}>(), { selectable: false, selected: false })

defineEmits<{
  open: [memory: MemoryItem]
  confirm: [memory: MemoryItem]
  ignore: [memory: MemoryItem]
  restore: [memory: MemoryItem]
  'toggle-select': [id: string]
}>()

const dateRange = computed(() => {
  if (!props.memory.start_time) return '时间待确认'
  const start = new Date(props.memory.start_time)
  const end = props.memory.end_time ? new Date(props.memory.end_time) : start
  const startText = `${start.getFullYear()}.${String(start.getMonth() + 1).padStart(2, '0')}.${String(start.getDate()).padStart(2, '0')}`
  const endText = `${end.getFullYear()}.${String(end.getMonth() + 1).padStart(2, '0')}.${String(end.getDate()).padStart(2, '0')}`
  return startText === endText ? startText : `${startText} — ${endText}`
})
</script>
