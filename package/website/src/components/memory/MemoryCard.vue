<template>
  <article class="memory-card" :class="{ 'memory-card--gallery': isGallery, 'memory-card--selected': selected }" :aria-busy="busy">
    <div class="memory-card-media" aria-hidden="true">
      <div class="memory-card-cover">
        <img v-if="coverId" :src="thumbnailUrl(coverId, isGallery ? 'medium' : 'small')" alt="" loading="lazy" @error="failedPhotos.add(coverId)" />
        <ImageIcon v-else />
      </div>
      <div v-if="extraPhotos.length" class="memory-card-strip">
        <img v-for="id in extraPhotos" :key="id" :src="thumbnailUrl(id)" alt="" loading="lazy" @error="failedPhotos.add(id)" />
      </div>
    </div>
    <div class="memory-card-copy">
      <h2>
        <RouterLink :to="`/memories/${memory.id}`" class="memory-card-link" :title="displayTitle">{{ displayTitle }}</RouterLink>
      </h2>
      <div class="memory-card-meta">
        <span v-if="showDate">{{ dateLabel }}</span>
        <span v-if="place"><MapPin aria-hidden="true" />{{ place }}</span>
        <span><Images aria-hidden="true" />{{ memory.photo_count.toLocaleString('zh-CN') }} 张</span>
        <span v-if="people"><UsersRound aria-hidden="true" /><span class="memory-card-people">{{ people }}</span></span>
      </div>
      <p v-if="excerpt" class="memory-card-excerpt">
        <Sparkles v-if="isCandidate" aria-hidden="true" />{{ excerpt }}
      </p>
    </div>

    <label v-if="selectable" class="memory-card-select">
      <input type="checkbox" :checked="selected" :aria-label="`选择 ${displayTitle}`" @change="$emit('toggle-select', memory.id)" />
    </label>
    <div v-else-if="!isGallery" class="memory-card-actions">
      <template v-if="isCandidate">
        <button type="button" class="memory-card-action memory-card-save" :disabled="busy" @click="$emit('confirm', memory)"><Check aria-hidden="true" />保存</button>
        <button type="button" class="memory-card-action memory-card-ignore" :disabled="busy" @click="$emit('ignore', memory)">忽略</button>
      </template>
      <button v-else class="memory-card-action memory-card-save" type="button" :disabled="busy" @click="$emit('restore', memory)"><Undo2 aria-hidden="true" />恢复</button>
    </div>
    <ArrowUpRight v-else class="memory-card-arrow" aria-hidden="true" />
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUpRight, Check, Image as ImageIcon, Images, MapPin, Sparkles, Undo2, UsersRound } from 'lucide-vue-next'
import type { MemoryItem } from '@/types/memory'
import { thumbnailUrl } from '@/utils/mediaUrl'

const props = defineProps<{
  memory: MemoryItem
  selectable?: boolean
  selected?: boolean
  busy?: boolean
}>()

defineEmits<{
  confirm: [memory: MemoryItem]
  ignore: [memory: MemoryItem]
  restore: [memory: MemoryItem]
  'toggle-select': [id: string]
}>()

const isGallery = computed(() => props.memory.status === 'confirmed')
const isCandidate = computed(() => props.memory.status === 'candidate')
const failedPhotos = ref(new Set<string>())
const availablePhotos = computed(() => {
  const ids = new Set([props.memory.cover_photo_id, ...(props.memory.preview_photo_ids ?? [])])
  return [...ids].filter((id): id is string => !!id && !failedPhotos.value.has(id))
})
const coverId = computed(() => availablePhotos.value[0])
const extraPhotos = computed(() => isGallery.value ? availablePhotos.value.slice(1, 3) : [])

const fullDate = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
const monthDay = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' })
function parseDate(value: string | null) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

const start = computed(() => parseDate(props.memory.start_time))
const end = computed(() => parseDate(props.memory.end_time) ?? start.value)
const dateLabel = computed(() => {
  if (!start.value || !end.value) return '时间待确认'
  if (start.value.toDateString() === end.value.toDateString()) return fullDate.format(start.value)
  const endFormat = start.value.getFullYear() === end.value.getFullYear() ? monthDay : fullDate
  return `${fullDate.format(start.value)} – ${endFormat.format(end.value)}`
})

function normalizeDateLabel(label: string) {
  return label.replace(/\s/g, '').replace(/\d+(?=[月日])/g, digits => String(Number(digits)))
}

const systemDates = computed(() => {
  if (props.memory.title_source !== 'system' || !start.value || !end.value) return []
  const first = fullDate.format(start.value)
  const last = fullDate.format(end.value)
  return [first, last, `${first}至${monthDay.format(end.value)}`, `${first}至${last}`]
})

const displayTitle = computed(() => {
  const [prefix, ...rest] = props.memory.title.split(/[·•]/)
  if (rest.length && systemDates.value.includes(normalizeDateLabel(prefix))) {
    return rest.join('·').trim() || props.memory.title
  }
  return props.memory.title
})
const showDate = computed(() => !systemDates.value.some(date => normalizeDateLabel(displayTitle.value) === `${date}的记忆`))
const place = computed(() => {
  const name = props.memory.places[0]?.name
  return name && !displayTitle.value.includes(name) ? name : ''
})
const people = computed(() => props.memory.people.slice(0, 3).map(person => person.name).join('、'))
const excerpt = computed(() => {
  if (!isCandidate.value) return props.memory.story
  const evidence = props.memory.evidence[0]
  if (evidence?.type === 'ticket' && displayTitle.value.includes('→')) {
    const train = evidence.summary.match(/^([A-Z]{0,3}\d{1,6})\s*[:：]/i)
    if (train) return train[1]
  }
  return evidence?.summary || props.memory.story
})
</script>

<style scoped>
.memory-card {
  position: relative;
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--ts-color-border);
  border-radius: 14px;
  background: var(--ts-color-surface);
  transition: border-color 160ms, box-shadow 160ms;
}
.memory-card:hover { border-color: color-mix(in srgb, var(--ts-journal-focus) 36%, var(--ts-color-border)); }
.memory-card--selected { border-color: var(--ts-journal-focus); box-shadow: 0 0 0 1px var(--ts-journal-focus); }
.memory-card-media { display: flex; align-self: stretch; min-width: 0; min-height: 72px; gap: 3px; overflow: hidden; border-radius: 8px; background: var(--ts-color-surface-muted); }
.memory-card-cover { position: relative; flex: 1; display: grid; place-items: center; min-width: 0; }
.memory-card-cover img, .memory-card-strip img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.memory-card-cover > svg { width: 24px; height: 24px; color: var(--ts-color-text-secondary); stroke-width: 1.5; }
.memory-card-copy { display: grid; gap: 4px; min-width: 0; }
.memory-card h2 { color: var(--ts-color-text); font-size: 17px; font-weight: 650; line-height: 1.35; overflow-wrap: anywhere; }
.memory-card-link { display: -webkit-box; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.memory-card-link::after { position: absolute; z-index: 1; inset: 0; border-radius: 14px; content: ''; }
.memory-card-link:focus-visible { outline: none; }
.memory-card-link:focus-visible::after { outline: 2px solid var(--ts-journal-focus); outline-offset: 2px; }
.memory-card-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 3px 10px; font-size: 12px; color: var(--ts-color-text-secondary); font-variant-numeric: tabular-nums; }
.memory-card-meta span { display: inline-flex; align-items: center; gap: 4px; }
.memory-card-meta .memory-card-people { display: inline-block; max-width: 16ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.memory-card-meta svg, .memory-card-excerpt svg { width: 13px; height: 13px; flex-shrink: 0; }
.memory-card-excerpt { display: -webkit-box; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 1; color: var(--ts-color-text-secondary); font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }
.memory-card-excerpt svg { display: inline-block; margin-right: 4px; color: var(--ts-journal-focus); vertical-align: -2px; }
.memory-card-actions { position: relative; z-index: 2; display: flex; align-items: center; gap: 4px; margin-right: 3px; }
.memory-card-action { display: inline-flex; justify-content: center; align-items: center; gap: 5px; min-width: 44px; min-height: 44px; padding-inline: 10px; border-radius: 9px; color: var(--ts-color-text-secondary); font-size: 13px; font-weight: 600; white-space: nowrap; }
.memory-card-action svg { width: 15px; height: 15px; }
.memory-card-save { background: var(--ts-journal-active); color: var(--ts-journal-accent-text); }
.memory-card-action:hover:enabled { background: var(--ts-color-surface-muted); color: var(--ts-color-text); }
.memory-card-save:hover:enabled { background: var(--ts-journal-action); color: white; }
.memory-card-action:disabled { opacity: .55; cursor: wait; }
.memory-card-action:focus-visible, .memory-card-select:focus-within { outline: 2px solid var(--ts-journal-focus); outline-offset: 2px; }
.memory-card-select { position: relative; z-index: 2; display: grid; place-items: center; width: 44px; height: 44px; border-radius: 9px; background: var(--ts-color-surface-muted); cursor: pointer; }
.memory-card-select input { width: 19px; height: 19px; accent-color: var(--ts-journal-focus); cursor: pointer; }

.memory-card--gallery { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto 1fr; gap: 0; align-items: start; padding: 0; }
.memory-card--gallery .memory-card-media { height: clamp(155px, 16vw, 225px); border-radius: 13px 13px 0 0; }
.memory-card--gallery .memory-card-cover img { transition: transform 300ms ease; }
.memory-card--gallery:hover .memory-card-cover img { transform: scale(1.035); }
.memory-card-strip { display: grid; grid-auto-rows: minmax(0, 1fr); width: 27%; gap: 3px; }
.memory-card-strip img { position: relative; min-height: 0; }
.memory-card--gallery .memory-card-copy { gap: 7px; padding: 14px 16px 16px; }
.memory-card--gallery h2 { font: 700 21px/1.3 var(--ts-journal-serif); }
.memory-card--gallery .memory-card-excerpt { -webkit-line-clamp: 2; }
.memory-card--gallery .memory-card-select, .memory-card-arrow { position: absolute; top: 8px; right: 8px; }
.memory-card-arrow { box-sizing: content-box; width: 15px; height: 15px; padding: 8px; border-radius: 9px; color: var(--ts-color-text); background: var(--ts-color-surface); }

@media (max-width: 520px) {
  .memory-card:not(.memory-card--gallery) { grid-template-columns: 72px minmax(0, 1fr); column-gap: 11px; row-gap: 5px; }
  .memory-card:not(.memory-card--gallery) .memory-card-media { grid-row: 1 / span 2; min-height: 70px; }
  .memory-card-actions, .memory-card:not(.memory-card--gallery) .memory-card-select { grid-column: 2; justify-self: start; }
  .memory-card h2 { font-size: 16px; }
  .memory-card--gallery .memory-card-media { height: 180px; }
}

@media (prefers-reduced-motion: reduce) {
  .memory-card, .memory-card--gallery .memory-card-cover img { transition: none; }
}
</style>
