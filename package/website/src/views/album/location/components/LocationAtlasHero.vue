<template>
  <div
    ref="heroRef"
    class="group atlas-hero"
    :class="{ 'is-coverless': !usableCover }"
    role="link"
    tabindex="0"
    :aria-label="ariaLabel"
    @click="onOpen"
    @keydown.enter.prevent="onOpen"
    @keydown.space.prevent="onOpen"
    @pointermove="onPointerMove"
    @pointerleave="resetPointer"
  >
    <div class="atlas-hero-photo">
      <img
        v-if="usableCover && !failed"
        :src="coverImage!.thumbnail"
        alt=""
        class="atlas-hero-underlay"
        aria-hidden="true"
      />
      <img
        v-if="usableCover && !failed"
        :src="coverImage!.preview"
        alt=""
        class="atlas-hero-image"
        :class="{ 'is-loaded': loaded }"
        decoding="async"
        @load="loaded = true"
        @error="failed = true"
      />
      <div v-else class="atlas-hero-fallback" aria-hidden="true">
        <span class="atlas-hero-fallback-rings"></span>
        <MapPin class="atlas-hero-fallback-pin" />
      </div>

      <span class="atlas-hero-glow" aria-hidden="true"></span>
      <span class="atlas-hero-shade" aria-hidden="true"></span>

      <span class="atlas-hero-rank">
        <span class="atlas-hero-rank-label">NO.</span>
        <span class="atlas-hero-rank-value">{{ indexLabel }}</span>
      </span>

      <span class="atlas-hero-spine" aria-hidden="true">TRAVELSNAP · ATLAS</span>
    </div>

    <div class="atlas-hero-panel">
      <div class="atlas-hero-heading">
        <p class="atlas-hero-kicker">
          <span class="atlas-hero-kicker-dot" aria-hidden="true"></span>
          <span>{{ kickerLabel }}</span>
          <span class="atlas-hero-kicker-latin">{{ kickerLatin }}</span>
        </p>
        <h3 class="atlas-hero-name">{{ location.name }}</h3>
        <p class="atlas-hero-meta">
          <span class="lm-num">{{ countLabel }}</span>
          <template v-if="month">
            <span class="atlas-hero-meta-sep" aria-hidden="true">·</span>
            <span>最近 {{ month }}</span>
          </template>
        </p>
      </div>

      <div v-if="thumbs.length" class="atlas-hero-thumbs" aria-hidden="true">
        <img
          v-for="(thumb, i) in thumbs"
          :key="thumb.id"
          :src="thumb.thumbnail"
          alt=""
          loading="lazy"
          decoding="async"
          :style="{ '--thumb-index': i }"
        />
      </div>

      <span class="atlas-hero-cta">
        <span>走进这里</span>
        <span class="atlas-hero-cta-arrow"><ArrowUpRight /></span>
      </span>

      <span class="atlas-hero-ghost" aria-hidden="true">{{ indexLabel }}</span>
    </div>

    <div v-if="level === 'scene' && location.id" class="atlas-hero-actions">
      <button
        type="button"
        class="atlas-hero-action"
        title="编辑景区"
        aria-label="编辑景区"
        @click.stop="emit('edit', location)"
        @keydown.stop
      >
        <Pencil />
      </button>
      <button
        type="button"
        class="atlas-hero-action is-danger"
        title="删除景区"
        aria-label="删除景区"
        @click.stop="emit('delete', location)"
        @keydown.stop
      >
        <Trash2 />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ArrowUpRight, MapPin, Pencil, Trash2 } from 'lucide-vue-next'
import { mapPhotoToImage } from '@/stores/photoStore'
import { locationService } from '@/api/location'
import type { Photo } from '@/types/album'
import type { Location } from '@/types/location'
import {
  formatCount,
  formatCoverMonth,
  formatIndex,
  locationLevelMeta,
} from '@/utils/locationPresentation'

const props = defineProps<{
  location: Location
  level: string
  index: number
  sortMode: 'count' | 'recent'
  startDate?: string
  endDate?: string
}>()

const emit = defineEmits<{
  (e: 'click', name: string, level?: string, sceneId?: string): void
  (e: 'edit', loc: Location): void
  (e: 'delete', loc: Location): void
}>()

const heroRef = ref<HTMLElement | null>(null)
const loaded = ref(false)
const failed = ref(false)
const thumbs = ref<ReturnType<typeof mapPhotoToImage>[]>([])
let thumbRequest = 0

const usableCover = computed(() => Boolean(props.location.cover?.width && props.location.cover?.height))
const coverImage = computed(() => (usableCover.value ? mapPhotoToImage(props.location.cover!) : null))
const countLabel = computed(() =>
  props.location.count > 0 ? `${formatCount(props.location.count)} 张影像` : '还没有影像',
)
const indexLabel = computed(() => formatIndex(props.index))
const month = computed(() => formatCoverMonth(props.location.cover))
const levelMeta = computed(() => locationLevelMeta(props.level))

const kickerLabel = computed(() => (props.sortMode === 'recent' ? '最近记录' : '影像最多'))
const kickerLatin = computed(() => (props.sortMode === 'recent' ? 'LATEST' : 'MOST CAPTURED'))

const ariaLabel = computed(() => {
  const count = props.location.count > 0 ? `${props.location.count} 张影像` : '暂无影像'
  return `精选${levelMeta.value.noun}「${props.location.name}」，${count}${month.value ? `，最近 ${month.value}` : ''}`
})

function onOpen(event: Event) {
  const target = event.target as HTMLElement | null
  if (target?.closest('.atlas-hero-actions')) return
  emit('click', props.location.name, props.level, props.location.id)
}

function onPointerMove(event: PointerEvent) {
  if (event.pointerType !== 'mouse') return
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  const el = heroRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const x = (event.clientX - rect.left) / rect.width
  const y = (event.clientY - rect.top) / rect.height
  el.style.setProperty('--spot-x', `${(x * 100).toFixed(2)}%`)
  el.style.setProperty('--spot-y', `${(y * 100).toFixed(2)}%`)
  el.style.setProperty('--shift-x', `${((x - 0.5) * 14).toFixed(2)}px`)
  el.style.setProperty('--shift-y', `${((y - 0.5) * 12).toFixed(2)}px`)
}

function resetPointer() {
  const el = heroRef.value
  if (!el) return
  el.style.removeProperty('--spot-x')
  el.style.removeProperty('--spot-y')
  el.style.removeProperty('--shift-x')
  el.style.removeProperty('--shift-y')
}

async function loadThumbs() {
  const request = ++thumbRequest
  thumbs.value = []
  const cover = props.location.cover
  if (!cover?.width || !cover?.height) return
  try {
    const photos = await locationService.getLocationPhotos(
      encodeURIComponent(props.location.name),
      props.level === 'scene' ? 'scene' : (props.level as 'city' | 'province' | 'district'),
      0,
      5,
      props.startDate,
      props.endDate,
      props.level === 'scene' ? props.location.id : undefined,
    )
    if (request !== thumbRequest) return
    const seen = new Set<string>([cover.id])
    const unique: Photo[] = []
    for (const photo of photos) {
      if (!photo?.id || seen.has(photo.id)) continue
      seen.add(photo.id)
      unique.push(photo)
      if (unique.length === 3) break
    }
    thumbs.value = unique.map(photo => mapPhotoToImage(photo))
  } catch (error) {
    if (request === thumbRequest) thumbs.value = []
    console.warn('Failed to load hero thumbnails', error)
  }
}

watch(
  () => [props.location.name, props.location.id, props.startDate, props.endDate] as const,
  loadThumbs,
  { immediate: true },
)

onBeforeUnmount(() => {
  thumbRequest += 1
})
</script>

<style scoped>
.atlas-hero {
  --spot-x: 50%;
  --spot-y: 40%;
  --shift-x: 0px;
  --shift-y: 0px;
  position: relative;
  isolation: isolate;
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: minmax(0, 1.52fr) minmax(300px, 0.85fr);
  min-height: 348px;
  overflow: hidden;
  border: 1px solid var(--ts-color-border);
  border-radius: 28px;
  background: var(--ts-color-surface);
  box-shadow:
    0 1px 2px rgb(15 23 42 / 6%),
    0 30px 60px -40px rgb(15 23 42 / 55%);
  cursor: pointer;
  outline: none;
  transition: box-shadow 480ms var(--lm-ease), transform 480ms var(--lm-ease);
}

.atlas-hero:focus-visible {
  outline: 2px solid var(--ts-journal-focus);
  outline-offset: 4px;
}

.atlas-hero-photo {
  position: relative;
  isolation: isolate;
  min-height: 348px;
  overflow: hidden;
  background: var(--ts-color-surface-muted);
}

.atlas-hero-underlay {
  position: absolute;
  inset: -12px;
  width: calc(100% + 24px);
  height: calc(100% + 24px);
  object-fit: cover;
  filter: blur(20px) saturate(0.85);
  transform: scale(1.04);
  opacity: 0.85;
}

.atlas-hero-image {
  position: absolute;
  inset: -10px;
  width: calc(100% + 20px);
  height: calc(100% + 20px);
  object-fit: cover;
  opacity: 0;
  filter: blur(18px) saturate(0.6);
  transform: scale(1.05);
  transition:
    opacity 800ms var(--lm-ease),
    filter 900ms var(--lm-ease),
    transform var(--hero-parallax-duration, 1100ms) var(--lm-ease);
  will-change: transform;
}

.atlas-hero-image.is-loaded {
  --hero-parallax-duration: 280ms;
  opacity: 1;
  filter: blur(0) saturate(1);
  transform: translate3d(var(--shift-x), var(--shift-y), 0) scale(1.035);
}

.atlas-hero-glow {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  opacity: 0;
  background: radial-gradient(
    34% 44% at var(--spot-x) var(--spot-y),
    rgb(255 255 255 / 18%),
    transparent 72%
  );
  transition: opacity 420ms ease;
}

.atlas-hero-shade {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background:
    linear-gradient(to top, rgb(6 10 18 / 52%) 0%, rgb(6 10 18 / 0%) 42%),
    linear-gradient(to right, rgb(6 10 18 / 30%) 0%, rgb(6 10 18 / 0%) 34%);
}

.atlas-hero-rank {
  position: absolute;
  z-index: 3;
  top: 18px;
  left: 18px;
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  height: 30px;
  padding: 0 11px;
  border: 1px solid rgb(255 255 255 / 26%);
  border-radius: 999px;
  color: #fff;
  background: rgb(9 14 24 / 34%);
  -webkit-backdrop-filter: blur(14px) saturate(150%);
  backdrop-filter: blur(14px) saturate(150%);
  font-variant-numeric: tabular-nums;
}

.atlas-hero-rank-label {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.16em;
  opacity: 0.7;
}

.atlas-hero-rank-value {
  font-family: var(--lm-font-display);
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.atlas-hero-spine {
  position: absolute;
  z-index: 3;
  top: 50%;
  right: 16px;
  color: rgb(255 255 255 / 46%);
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.34em;
  writing-mode: vertical-rl;
  transform: translateY(-50%);
  pointer-events: none;
}

/* The panel is a reading surface, not a floating card: flat colour, a hairline
   seam and the theme's light gathered at the top-right. */
.atlas-hero-panel {
  position: relative;
  display: flex;
  min-width: 0;
  flex-direction: column;
  padding: clamp(24px, 2.6vw, 38px);
  overflow: hidden;
  border-left: 1px solid var(--ts-color-divider);
  background:
    radial-gradient(120% 100% at 100% 0%, rgba(var(--theme-rgb), 0.13), transparent 62%),
    var(--ts-color-surface);
}

.atlas-hero-heading {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.atlas-hero-kicker {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: var(--ts-color-text-secondary);
  font-size: 10.5px;
  font-weight: 650;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.atlas-hero-kicker-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--theme-primary);
  box-shadow: 0 0 0 4px rgba(var(--theme-rgb), 0.12);
  animation: ts-breathe 3.4s var(--ts-ease-breathe) 700ms 2;
}

.atlas-hero-kicker-latin {
  color: var(--ts-color-text-tertiary);
  font-family: var(--lm-font-display);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.2em;
}

.atlas-hero-name {
  margin: 0;
  color: var(--ts-color-text);
  font-family: var(--lm-font-display);
  font-size: clamp(29px, 3vw, 42px);
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.045em;
  overflow-wrap: anywhere;
  text-wrap: balance;
}

.atlas-hero-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
  margin: 2px 0 0;
  color: var(--ts-color-text-secondary);
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: 0.01em;
  font-variant-numeric: tabular-nums;
}

.atlas-hero-meta-sep {
  color: var(--ts-color-text-tertiary);
}

.atlas-hero-thumbs {
  position: relative;
  z-index: 2;
  display: flex;
  gap: 8px;
  margin-top: 18px;
}

.atlas-hero-thumbs img {
  width: 58px;
  height: 72px;
  object-fit: cover;
  border-radius: 11px;
  border: 2px solid var(--ts-color-surface);
  box-shadow: 0 10px 20px -14px rgb(15 23 42 / 60%);
  transform: rotate(calc((var(--thumb-index) - 1) * 3deg));
  transition: transform 480ms var(--lm-ease);
}

.atlas-hero-thumbs img:first-child {
  transform: translateY(5px) rotate(-3deg);
}

.atlas-hero-thumbs img:nth-child(3) {
  transform: translateY(7px) rotate(4deg);
}

.atlas-hero-cta {
  position: relative;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-top: auto;
  padding-top: 22px;
  color: var(--ts-color-text);
  font-size: 13px;
  font-weight: 650;
  letter-spacing: 0.01em;
}

.atlas-hero-cta-arrow {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  margin-left: 2px;
  border: 1px solid var(--ts-color-border);
  border-radius: 50%;
  color: var(--ts-journal-accent-text);
  background: var(--ts-color-surface);
  transition:
    background-color 260ms ease,
    color 260ms ease,
    transform 380ms var(--lm-ease);
}

.atlas-hero-cta-arrow svg {
  width: 15px;
  height: 15px;
}

.atlas-hero-ghost {
  position: absolute;
  z-index: 0;
  right: 12px;
  bottom: -34px;
  color: rgba(var(--theme-rgb), 0.09);
  font-family: var(--lm-font-display);
  font-size: clamp(150px, 15vw, 210px);
  font-weight: 700;
  line-height: 0.72;
  letter-spacing: -0.06em;
  pointer-events: none;
  user-select: none;
}

.atlas-hero-fallback {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  overflow: hidden;
  background:
    radial-gradient(100% 80% at 15% 0%, rgba(var(--theme-rgb), 0.34), transparent 60%),
    linear-gradient(145deg, var(--ts-color-surface-muted), var(--ts-color-surface));
}

.atlas-hero-fallback-rings {
  position: absolute;
  inset: -16%;
  opacity: 0.55;
  background:
    repeating-radial-gradient(
      ellipse at 70% 76%,
      transparent 0 26px,
      rgba(var(--theme-rgb), 0.2) 27px 28px
    ),
    repeating-radial-gradient(
      ellipse at 22% 16%,
      transparent 0 42px,
      rgba(var(--theme-rgb), 0.12) 43px 44px
    );
}

.atlas-hero-fallback-pin {
  position: relative;
  width: 46px;
  height: 46px;
  color: var(--theme-primary);
  opacity: 0.55;
}

.atlas-hero-actions {
  position: absolute;
  z-index: 7;
  right: 16px;
  top: 16px;
  display: flex;
  gap: 6px;
}

.atlas-hero-action {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid transparent;
  border-radius: 50%;
  color: var(--ts-color-text-secondary);
  background: var(--ts-color-surface-muted);
  cursor: pointer;
  transition: background-color 180ms ease, color 180ms ease, border-color 180ms ease;
}

.atlas-hero-action svg {
  width: 14px;
  height: 14px;
}

.atlas-hero-action:hover {
  border-color: var(--ts-color-border);
  background: var(--ts-color-surface);
  color: var(--ts-color-text);
}

.atlas-hero-action.is-danger:hover {
  color: var(--ts-color-danger);
}

.atlas-hero-action:focus-visible {
  outline: 2px solid var(--ts-journal-focus);
  outline-offset: 2px;
}

/* When the hero stacks, the actions sit on the photo and need the dark glass. */
@media (max-width: 767px) {
  .atlas-hero-action {
    border-color: rgb(255 255 255 / 30%);
    color: #fff;
    background: rgb(9 14 24 / 42%);
    -webkit-backdrop-filter: blur(10px);
    backdrop-filter: blur(10px);
  }

  .atlas-hero-action:hover {
    background: rgb(255 255 255 / 92%);
    color: var(--ts-color-text);
  }

  .atlas-hero-action.is-danger:hover {
    color: var(--ts-color-danger);
  }

  .atlas-hero-action:focus-visible {
    outline-color: #fff;
  }
}

@media (hover: hover) and (pointer: fine) {
  .atlas-hero:hover {
    box-shadow:
      0 1px 2px rgb(15 23 42 / 8%),
      0 44px 80px -46px rgb(15 23 42 / 66%);
  }

  .atlas-hero:hover .atlas-hero-glow {
    opacity: 1;
  }

  .atlas-hero:hover .atlas-hero-thumbs img,
  .atlas-hero:hover .atlas-hero-thumbs img:first-child,
  .atlas-hero:hover .atlas-hero-thumbs img:nth-child(3) {
    transform: translateY(0) rotate(0deg);
  }

  .atlas-hero:hover .atlas-hero-cta-arrow {
    color: #fff;
    background: var(--ts-journal-action);
    transform: translate3d(2px, -2px, 0);
  }
}

@media (max-width: 767px) {
  .atlas-hero {
    grid-template-columns: 1fr;
    min-height: 0;
    border-radius: 24px;
  }

  .atlas-hero-photo {
    min-height: 0;
    aspect-ratio: 2 / 1;
  }

  .atlas-hero-panel {
    border-left: 0;
    border-top: 1px solid var(--ts-color-divider);
    padding: 22px 22px 24px;
  }

  .atlas-hero-name {
    font-size: clamp(27px, 6.4vw, 36px);
  }

  .atlas-hero-thumbs {
    display: none;
  }

  .atlas-hero-cta {
    padding-top: 18px;
  }

  .atlas-hero-ghost {
    right: 14px;
    bottom: -22px;
    font-size: 118px;
  }

  .atlas-hero-spine {
    display: none;
  }
}

@media (max-width: 767px) {
  .atlas-hero {
    border-radius: 20px;
  }

  .atlas-hero-photo {
    aspect-ratio: 2 / 1;
  }

  .atlas-hero-panel {
    padding: 14px 15px 15px;
  }

  .atlas-hero-heading {
    gap: 6px;
  }

  .atlas-hero-kicker {
    font-size: 10px;
    letter-spacing: 0.1em;
  }

  .atlas-hero-kicker-latin {
    display: none;
  }

  .atlas-hero-name {
    font-size: clamp(24px, 7vw, 30px);
  }

  .atlas-hero-meta {
    gap: 5px;
    font-size: 11.5px;
  }

  .atlas-hero-cta {
    padding-top: 12px;
    font-size: 12.5px;
  }

  .atlas-hero-cta-arrow {
    width: 29px;
    height: 29px;
  }

  .atlas-hero-rank {
    top: 12px;
    left: 12px;
    height: 26px;
  }

  .atlas-hero-ghost {
    font-size: 96px;
    bottom: -16px;
  }

  .atlas-hero-actions {
    top: 12px;
    right: 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .atlas-hero,
  .atlas-hero-image,
  .atlas-hero-glow,
  .atlas-hero-thumbs img,
  .atlas-hero-cta-arrow {
    transition: none !important;
    animation: none !important;
  }

  .atlas-hero-image {
    opacity: 1;
    filter: none;
    transform: none;
  }
}
</style>
