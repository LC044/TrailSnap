<template>
  <div
    class="group atlas-card"
    :class="{ 'is-coverless': !usableCover }"
    role="link"
    tabindex="0"
    :aria-label="ariaLabel"
    @click="onOpen"
    @keydown.enter.prevent="onOpen"
    @keydown.space.prevent="onOpen"
  >
    <div class="atlas-card-media">
      <img
        v-if="usableCover && !failed"
        :src="coverImage!.thumbnail"
        alt=""
        class="atlas-card-image"
        :class="{ 'is-loaded': loaded }"
        loading="lazy"
        decoding="async"
        @load="loaded = true"
        @error="failed = true"
      />
      <div v-else class="atlas-card-fallback" aria-hidden="true">
        <span class="atlas-card-fallback-rings"></span>
        <MapPin class="atlas-card-fallback-pin" />
      </div>

      <span class="atlas-card-scrim" aria-hidden="true"></span>

      <span class="atlas-card-count" :class="{ 'is-empty': location.count === 0 }">
        <Camera v-if="location.count > 0" class="atlas-card-count-icon" aria-hidden="true" />
        {{ countLabel }}
      </span>

      <span class="atlas-card-body">
        <span class="atlas-card-index" aria-hidden="true">{{ indexLabel }}</span>
        <h3 class="atlas-card-name" :title="location.name">{{ location.name }}</h3>
        <span class="atlas-card-meta">{{ metaLabel }}</span>
      </span>

      <span class="atlas-card-go" aria-hidden="true">
        <ArrowUpRight />
      </span>
    </div>

    <div v-if="level === 'scene' && location.id" class="atlas-card-actions">
      <button
        type="button"
        class="atlas-card-action"
        title="编辑景区"
        aria-label="编辑景区"
        @click.stop="emit('edit', location)"
        @keydown.stop
      >
        <Pencil />
      </button>
      <button
        type="button"
        class="atlas-card-action is-danger"
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
import { computed, ref } from 'vue'
import { ArrowUpRight, Camera, MapPin, Pencil, Trash2 } from 'lucide-vue-next'
import { mapPhotoToImage } from '@/stores/photoStore'
import type { Location } from '@/types/location'
import {
  formatCompactCount,
  formatCoverMonth,
  formatIndex,
  locationLevelMeta,
} from '@/utils/locationPresentation'

const props = defineProps<{
  location: Location
  level: string
  index: number
}>()

const emit = defineEmits<{
  (e: 'click', name: string, level?: string, sceneId?: string): void
  (e: 'edit', loc: Location): void
  (e: 'delete', loc: Location): void
}>()

const loaded = ref(false)
const failed = ref(false)

const usableCover = computed(() => Boolean(props.location.cover?.width && props.location.cover?.height))
const coverImage = computed(() => (usableCover.value ? mapPhotoToImage(props.location.cover!) : null))
const countLabel = computed(() =>
  props.location.count === 0 ? '未打卡' : `${formatCompactCount(props.location.count)} 张`,
)
const indexLabel = computed(() => formatIndex(props.index))
const month = computed(() => formatCoverMonth(props.location.cover))
const metaLabel = computed(() => {
  if (month.value) return `最近 ${month.value}`
  return props.location.count > 0 ? '已收录影像' : '等待第一张照片'
})
const levelMeta = computed(() => locationLevelMeta(props.level))

const ariaLabel = computed(() => {
  const count = props.location.count > 0 ? `${props.location.count} 张影像` : '暂无影像'
  const recent = month.value ? `，最近 ${month.value}` : ''
  return `打开${levelMeta.value.noun}「${props.location.name}」，${count}${recent}`
})

function onOpen(event: Event) {
  const target = event.target as HTMLElement | null
  if (target?.closest('.atlas-card-actions')) return
  emit('click', props.location.name, props.level, props.location.id)
}
</script>

<style scoped>
.atlas-card {
  position: relative;
  min-width: 0;
  border-radius: 22px;
  cursor: pointer;
  outline: none;
  -webkit-tap-highlight-color: transparent;
  transition: transform 420ms var(--lm-ease), filter 420ms var(--lm-ease);
}

.atlas-card:focus-visible {
  outline: 2px solid var(--ts-journal-focus);
  outline-offset: 4px;
}

.atlas-card-media {
  position: relative;
  isolation: isolate;
  display: block;
  aspect-ratio: 3 / 4;
  overflow: hidden;
  border-radius: 22px;
  background: var(--ts-color-surface-muted);
  box-shadow:
    0 1px 2px rgb(15 23 42 / 6%),
    0 18px 38px -30px rgb(15 23 42 / 45%);
  transition: box-shadow 420ms var(--lm-ease), transform 420ms var(--lm-ease);
}

.atlas-card-image {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  filter: blur(16px) saturate(0.55);
  transform: scale(1.045);
  transition:
    opacity 640ms var(--lm-ease),
    filter 760ms var(--lm-ease),
    transform 1000ms var(--lm-ease);
}

.atlas-card-image.is-loaded {
  opacity: 1;
  filter: blur(0) saturate(1);
  transform: scale(1);
}

.atlas-card-scrim {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background:
    linear-gradient(to top, rgb(6 10 18 / 82%) 0%, rgb(6 10 18 / 46%) 30%, rgb(6 10 18 / 0%) 58%),
    linear-gradient(to bottom, rgb(6 10 18 / 26%) 0%, rgb(6 10 18 / 0%) 26%);
  opacity: 0.94;
  transition: opacity 460ms var(--lm-ease);
}

.atlas-card-count {
  position: absolute;
  z-index: 3;
  top: 12px;
  right: 12px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 9px;
  border: 1px solid rgb(255 255 255 / 24%);
  border-radius: 999px;
  color: rgb(255 255 255 / 94%);
  background: rgb(9 14 24 / 38%);
  -webkit-backdrop-filter: blur(12px) saturate(140%);
  backdrop-filter: blur(12px) saturate(140%);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.01em;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.atlas-card-count.is-empty {
  color: rgb(255 255 255 / 78%);
  background: rgb(9 14 24 / 28%);
}

.atlas-card-count-icon {
  width: 12px;
  height: 12px;
  opacity: 0.78;
}

.atlas-card-body {
  position: absolute;
  z-index: 2;
  inset: auto 0 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 18px 42px 17px 16px;
  color: #fff;
  pointer-events: none;
}

.atlas-card-index {
  color: rgb(255 255 255 / 62%);
  font-family: var(--lm-font-display);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.18em;
  line-height: 1.2;
}

.atlas-card-name {
  margin: 0;
  color: #fff;
  font-size: 16px;
  font-weight: 650;
  line-height: 1.3;
  letter-spacing: -0.01em;
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow-wrap: anywhere;
  text-shadow: 0 1px 14px rgb(0 0 0 / 32%);
  /* The body is pointer-transparent so the whole photo acts as the hit area;
     the title re-enables events so the name itself remains a real target for
     keyboards, selection and accessibility tooling. */
  pointer-events: auto;
}

.atlas-card-meta {
  color: rgb(255 255 255 / 68%);
  font-size: 11.5px;
  font-weight: 500;
  line-height: 1.4;
  letter-spacing: 0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.atlas-card-go {
  position: absolute;
  z-index: 3;
  right: 13px;
  bottom: 15px;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid rgb(255 255 255 / 44%);
  border-radius: 50%;
  color: #fff;
  background: rgb(255 255 255 / 10%);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  opacity: 0;
  transform: translate3d(-4px, 4px, 0) scale(0.9);
  transition:
    opacity 320ms var(--lm-ease),
    transform 420ms var(--lm-ease),
    background-color 240ms ease;
}

.atlas-card-go svg {
  width: 14px;
  height: 14px;
}

/* A topographic fallback keeps a place without a cover feeling intentional. */
.atlas-card-fallback {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  overflow: hidden;
  background:
    radial-gradient(120% 90% at 18% 0%, rgba(var(--theme-rgb), 0.26), transparent 62%),
    linear-gradient(150deg, var(--ts-color-surface-muted), var(--ts-color-surface));
}

.atlas-card-fallback-rings {
  position: absolute;
  inset: -18%;
  opacity: 0.5;
  background:
    repeating-radial-gradient(
      ellipse at 72% 78%,
      transparent 0 21px,
      rgba(var(--theme-rgb), 0.19) 22px 23px
    ),
    repeating-radial-gradient(
      ellipse at 20% 18%,
      transparent 0 33px,
      rgba(var(--theme-rgb), 0.12) 34px 35px
    );
}

.atlas-card-fallback-pin {
  position: relative;
  width: 30px;
  height: 30px;
  color: var(--theme-primary);
  opacity: 0.6;
}

.atlas-card-actions {
  position: absolute;
  z-index: 6;
  top: 12px;
  left: 12px;
  display: flex;
  gap: 6px;
  opacity: 0;
  transform: translate3d(0, -4px, 0);
  transition: opacity 220ms ease, transform 280ms var(--lm-ease);
}

.atlas-card-action {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 1px solid rgb(255 255 255 / 30%);
  border-radius: 50%;
  color: #fff;
  background: rgb(9 14 24 / 44%);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  cursor: pointer;
  transition: background-color 180ms ease, transform 180ms var(--lm-ease), color 180ms ease;
}

.atlas-card-action svg {
  width: 14px;
  height: 14px;
}

.atlas-card-action:hover {
  background: rgb(255 255 255 / 92%);
  color: var(--ts-color-text);
}

.atlas-card-action.is-danger:hover {
  color: var(--ts-color-danger);
}

.atlas-card-action:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}

@media (hover: hover) and (pointer: fine) {
  .atlas-card:hover,
  .atlas-card:focus-within {
    z-index: 3;
  }

  .atlas-card:hover .atlas-card-media {
    transform: translate3d(0, -5px, 0);
    box-shadow:
      0 1px 2px rgb(15 23 42 / 8%),
      0 28px 54px -28px rgb(15 23 42 / 58%);
  }

  .atlas-card:hover .atlas-card-image {
    transform: scale(1.055);
  }

  .atlas-card:hover .atlas-card-scrim {
    opacity: 1;
  }

  .atlas-card:hover .atlas-card-go {
    opacity: 1;
    transform: translate3d(0, 0, 0) scale(1);
  }

  .atlas-card:hover .atlas-card-actions,
  .atlas-card:focus-within .atlas-card-actions {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

/* Touch has no hover: keep the whole card pressable and the actions visible
   only on scene cards, where managing the place is a primary task. */
@media (hover: none) {
  .atlas-card:active .atlas-card-media {
    transform: scale(0.985);
  }

  .atlas-card-actions {
    opacity: 1;
    transform: none;
  }
}

@media (max-width: 767px) {
  .atlas-card,
  .atlas-card-media {
    border-radius: 18px;
  }

  .atlas-card-media {
    aspect-ratio: 3 / 4;
  }

  .atlas-card-body {
    padding: 14px 34px 13px 12px;
  }

  .atlas-card-name {
    font-size: 14.5px;
  }

  .atlas-card-index {
    font-size: 10px;
  }

  .atlas-card-go {
    width: 25px;
    height: 25px;
    opacity: 0.9;
    transform: none;
  }

  .atlas-card-count {
    top: 9px;
    right: 9px;
    height: 23px;
    padding: 0 8px;
    font-size: 10.5px;
  }

  .atlas-card-actions {
    top: 9px;
    left: 9px;
  }

  .atlas-card-action {
    width: 27px;
    height: 27px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .atlas-card,
  .atlas-card-media,
  .atlas-card-image,
  .atlas-card-scrim,
  .atlas-card-go,
  .atlas-card-actions {
    transition: none !important;
    animation: none !important;
    transform: none !important;
  }

  .atlas-card-image {
    opacity: 1;
    filter: none;
  }
}
</style>
