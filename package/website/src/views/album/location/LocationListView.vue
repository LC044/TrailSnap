<template>
  <div
    ref="scrollRoot"
    class="atlas-scroll flex-1 min-h-0 overflow-y-auto"
  >
    <div v-if="loading && locations.length" class="atlas-refresh-line" aria-hidden="true"></div>
    <!-- Loading skeleton -->
    <div v-if="loading && locations.length === 0" class="atlas-shell atlas-skeleton" aria-busy="true" aria-label="正在加载位置图鉴">
      <div class="atlas-skeleton-head">
        <span class="atlas-skeleton-line is-kicker"></span>
        <span class="atlas-skeleton-line is-title"></span>
        <span class="atlas-skeleton-line is-sub"></span>
      </div>
      <div class="atlas-skeleton-hero"></div>
      <div class="atlas-skeleton-grid">
        <span v-for="i in 10" :key="i" class="atlas-skeleton-cell"></span>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="error && locations.length === 0" class="atlas-shell atlas-state">
      <div class="atlas-state-art is-error" aria-hidden="true">
        <CloudOff />
      </div>
      <h2 class="atlas-state-title">位置图鉴暂时打不开</h2>
      <p class="atlas-state-copy">连接服务器时出了点问题，你的照片和足迹仍然安全。</p>
      <button type="button" class="atlas-state-action" @click="$emit('retry')">重新加载</button>
    </div>

    <!-- Empty -->
    <div v-else-if="locations.length === 0" class="atlas-shell atlas-state">
      <div class="atlas-state-art" aria-hidden="true">
        <span class="atlas-state-rings"></span>
        <MapPin />
      </div>
      <h2 class="atlas-state-title">{{ hasRangeFilter ? '这段时间还没有位置记录' : '暂无位置信息' }}</h2>
      <p class="atlas-state-copy">
        {{ hasRangeFilter ? '换一个年份，或放宽时间范围再看看。' : '照片带上拍摄地点后，这里会自动生长成一本地方图鉴。' }}
      </p>
      <RouterLink v-if="level === 'scene' && !hasRangeFilter" to="/settings" class="atlas-state-action">去检查地图与定位设置</RouterLink>
    </div>

    <!-- Atlas -->
    <div v-else class="atlas-shell">
      <header class="atlas-masthead">
        <div class="atlas-masthead-main">
          <p class="atlas-kicker">
            <span class="atlas-pulse" aria-hidden="true"></span>
            <span>位置图鉴</span>
            <span class="atlas-kicker-rule" aria-hidden="true"></span>
            <span class="atlas-kicker-range">{{ rangeLabel }}</span>
          </p>
          <h2 class="atlas-headline">
            <span class="atlas-headline-number lm-num">{{ countUpLabel }}</span>
            <span class="atlas-headline-unit">{{ levelMeta.unit }}</span>
          </h2>
          <p class="atlas-summary">
            <span><span class="lm-num">{{ photosUpLabel }}</span> 帧影像</span>
            <template v-if="yearSpan">
              <span class="atlas-summary-sep" aria-hidden="true">·</span>
              <span>{{ yearSpan }}</span>
            </template>
            <template v-if="provinceCount !== null && level !== 'province'">
              <span class="atlas-summary-province">
                <span class="atlas-summary-sep" aria-hidden="true">·</span>
                <span>累计点亮 {{ provinceCount }} 个省份</span>
              </span>
            </template>
          </p>
        </div>

        <div v-if="provinceCount !== null" class="atlas-coverage">
          <div class="atlas-coverage-head">
            <span class="atlas-coverage-label">足迹覆盖</span>
            <span class="atlas-coverage-value lm-num">{{ coveragePercent }}<small>%</small></span>
          </div>
          <div
            class="atlas-coverage-track"
            role="img"
            :aria-label="`已点亮 ${provinceCount} 个省份，共 34 个`"
          >
            <span
              v-for="n in 34"
              :key="n"
              class="atlas-coverage-seg"
              :class="{ 'is-lit': n <= provinceCount }"
              :style="{ '--seg-index': n }"
              aria-hidden="true"
            ></span>
          </div>
          <p class="atlas-coverage-note">
            累计 <span class="lm-num">{{ provinceCount }}</span> / 34 个省份
            <template v-if="countryCount"> · {{ countryCount }} 个国家</template>
          </p>
        </div>
      </header>

      <div class="atlas-gridbar">
        <p v-if="cards.length" class="atlas-gridbar-note">
          其余 <span class="lm-num">{{ cards.length }}</span> {{ levelMeta.unit }}
        </p>
        <p v-else class="atlas-gridbar-note">{{ levelMeta.noun }}图鉴</p>
        <button
          type="button"
          class="atlas-sort"
          :aria-label="sortMode === 'count' ? '当前按照片数量排序，点击切换为最近记录' : '当前按最近记录排序，点击切换为照片数量'"
          @click="toggleSort"
        >
          <ArrowDownWideNarrow class="atlas-sort-icon" />
          <span>{{ sortMode === 'count' ? '影像最多' : '最近记录' }}</span>
        </button>
      </div>

      <TransitionGroup
        tag="div"
        name="atlas-item"
        appear
        class="atlas-grid"
        data-testid="location-album-grid"
        :aria-busy="loading"
      >
        <LocationAtlasHero
          v-if="hero"
          :key="heroKey"
          :style="{ '--stagger': 0 }"
          :location="hero"
          :level="level"
          :index="0"
          :sort-mode="sortMode"
          :start-date="startDate"
          :end-date="endDate"
          @click="(name, lvl, sceneId) => $emit('click', name, lvl, sceneId)"
          @edit="loc => $emit('edit', loc)"
          @delete="loc => $emit('delete', loc)"
        />
        <LocationAtlasCard
          v-for="(loc, index) in cards"
          :key="cardKey(loc)"
          :style="{ '--stagger': Math.min(index + 1, 12) }"
          :location="loc"
          :level="level"
          :index="index + 1"
          @click="(name, lvl, sceneId) => $emit('click', name, lvl, sceneId)"
          @edit="loc => $emit('edit', loc)"
          @delete="loc => $emit('delete', loc)"
        />
      </TransitionGroup>
    </div>

    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowDownWideNarrow, CloudOff, MapPin } from 'lucide-vue-next'
import LocationAtlasCard from './components/LocationAtlasCard.vue'
import LocationAtlasHero from './components/LocationAtlasHero.vue'
import { useCountUp } from '@/composables/useCountUp'
import type { Location, LocationStatistics } from '@/types/location'
import {
  coverTimestamp,
  formatCount,
  locationLevelMeta,
} from '@/utils/locationPresentation'

const props = defineProps<{
  locations: Location[]
  loading: boolean
  level: string
  statistics?: LocationStatistics | null
  availableYears?: number[]
  selectedYear?: number | null
  rangeLabel?: string
  startDate?: string
  endDate?: string
  error?: boolean
}>()

defineEmits<{
  (e: 'click', name: string, level?: string, sceneId?: string): void
  (e: 'edit', loc: Location): void
  (e: 'delete', loc: Location): void
  (e: 'retry'): void
}>()

const scrollRoot = ref<HTMLElement | null>(null)
const sortMode = ref<'count' | 'recent'>('count')

const levelMeta = computed(() => locationLevelMeta(props.level))

const sortedLocations = computed(() => {
  const list = [...props.locations]
  return list.sort((a, b) => {
    if (sortMode.value === 'recent') {
      const diff = coverTimestamp(b.cover) - coverTimestamp(a.cover)
      if (diff !== 0) return diff
    }
    return b.count - a.count
  })
})

const hero = computed(() => sortedLocations.value[0] ?? null)
const cards = computed(() => sortedLocations.value.slice(1))

const totalPhotos = computed(() => props.locations.reduce((sum, loc) => sum + (loc.count || 0), 0))
const countUp = useCountUp(computed(() => props.locations.length))
const photosUp = useCountUp(totalPhotos)
const countUpLabel = computed(() => formatCount(countUp.value))
const photosUpLabel = computed(() => formatCount(photosUp.value))

const provinceCount = computed(() => props.statistics?.province_count ?? null)
const countryCount = computed(() => props.statistics?.country_count ?? 0)
const coveragePercent = computed(() => {
  const count = provinceCount.value
  if (count === null) return 0
  return Math.max(0, Math.min(100, Math.round((count / 34) * 100)))
})

const yearSpan = computed(() => {
  // With a year or custom range selected, the kicker already names the period;
  // repeating the lifetime span would make the filtered figures look lifetime.
  if (props.rangeLabel && props.rangeLabel !== '全部时间') return ''
  const years = (props.availableYears ?? [])
    .filter(year => Number.isFinite(year))
    .sort((a, b) => a - b)
  if (!years.length) return ''
  const first = years[0]
  const last = years[years.length - 1]
  return first === last ? `${first} 年` : `${first} — ${last}`
})

const rangeLabel = computed(() => props.rangeLabel || '全部时间')
const hasRangeFilter = computed(() => rangeLabel.value !== '全部时间')

function cardKey(loc: Location) {
  return `${props.level}-${rangeLabel.value}-${loc.id || loc.name}`
}

const heroKey = computed(() => {
  const first = hero.value
  if (!first) return 'atlas-hero'
  return `${props.level}-${rangeLabel.value}-${first.id || first.name}-hero`
})

function toggleSort() {
  sortMode.value = sortMode.value === 'count' ? 'recent' : 'count'
  scrollToTop()
}

function scrollToTop() {
  scrollRoot.value?.scrollTo({ top: 0, behavior: 'smooth' })
}

defineExpose({ scrollToTop })
</script>

<style scoped>
.atlas-scroll {
  position: relative;
  overflow-x: hidden;
  scrollbar-gutter: stable;
  scroll-behavior: smooth;
}

.atlas-shell {
  position: relative;
  width: 100%;
  max-width: 1720px;
  margin-inline: auto;
  padding: 4px 0 48px;
}

/* ---------------------------------------------------------------- masthead */
.atlas-masthead {
  position: relative;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 32px;
  padding: 10px 0 26px;
}

.atlas-masthead::before {
  position: absolute;
  top: -160px;
  right: -8%;
  width: min(760px, 64vw);
  height: 360px;
  content: '';
  pointer-events: none;
  background: radial-gradient(closest-side, rgba(var(--theme-rgb), 0.1), transparent 72%);
  filter: blur(6px);
}

.atlas-masthead-main {
  position: relative;
  z-index: 1;
  min-width: 0;
}

.atlas-kicker {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  color: var(--ts-color-text-secondary);
  font-size: 10.5px;
  font-weight: 650;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.atlas-kicker-rule {
  flex-shrink: 0;
  width: 22px;
  height: 1px;
  background: var(--ts-color-border);
}

.atlas-kicker-range {
  min-width: 0;
  overflow: hidden;
  color: var(--ts-color-text-secondary);
  letter-spacing: 0.08em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.atlas-pulse {
  width: 6px;
  height: 6px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--theme-primary);
  box-shadow: 0 0 0 4px rgba(var(--theme-rgb), 0.13);
  animation: ts-breathe 3.6s var(--ts-ease-breathe) 400ms 2;
}

.atlas-headline {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin: 0;
  color: var(--ts-color-text);
  font-family: var(--lm-font-display);
  font-weight: 700;
  line-height: 0.96;
  letter-spacing: -0.055em;
}

.atlas-headline-number {
  font-size: clamp(46px, 5.4vw, 72px);
  font-variant-numeric: tabular-nums;
}

.atlas-headline-unit {
  font-family: var(--ts-font-sans);
  color: var(--ts-color-text-secondary);
  font-size: clamp(15px, 1.4vw, 18px);
  font-weight: 600;
  letter-spacing: -0.02em;
}

.atlas-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 12px 0 0;
  color: var(--ts-color-text-secondary);
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: 0.01em;
  font-variant-numeric: tabular-nums;
}

.atlas-summary-sep {
  color: var(--ts-color-text-tertiary);
}

.atlas-summary-province {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

/* The desktop coverage meter already carries the province figure. */
@media (min-width: 768px) {
  .atlas-summary-province { display: none; }
}

/* A 34-segment "province coverage" meter: enough structure to read as a
   journey, not a dashboard chart. */
.atlas-coverage {
  position: relative;
  z-index: 1;
  width: min(310px, 32vw);
  flex-shrink: 0;
  padding-bottom: 3px;
}

.atlas-coverage-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 9px;
}

.atlas-coverage-label {
  color: var(--ts-color-text-secondary);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
}

.atlas-coverage-value {
  color: var(--ts-color-text);
  font-family: var(--lm-font-display);
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.03em;
}

.atlas-coverage-value small {
  margin-left: 1px;
  color: var(--ts-color-text-tertiary);
  font-family: var(--ts-font-sans);
  font-size: 10px;
  font-weight: 600;
}

.atlas-coverage-track {
  display: flex;
  gap: 3px;
  height: 6px;
}

.atlas-coverage-seg {
  flex: 1 1 0;
  height: 100%;
  border-radius: 2px;
  background: var(--ts-color-border);
  opacity: 0.55;
  transform: scaleY(0.55);
  transform-origin: center;
}

.atlas-coverage-seg.is-lit {
  background: linear-gradient(to top, rgba(var(--theme-rgb), 0.72), var(--theme-primary));
  opacity: 1;
  transform: scaleY(1);
  animation: atlas-seg-in 520ms var(--ts-ease-spring) calc(var(--seg-index) * 16ms) backwards;
}

.atlas-coverage-note {
  margin: 8px 0 0;
  color: var(--ts-color-text-secondary);
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
}

@keyframes atlas-seg-in {
  from { transform: scaleY(0.15); opacity: 0; }
  to { transform: scaleY(1); opacity: 1; }
}

/* ------------------------------------------------------------------ toolbar */
.atlas-gridbar {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 6px 1px 14px;
}

.atlas-gridbar-note {
  margin: 0;
  color: var(--ts-color-text-secondary);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
}

.atlas-sort {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  border: 1px solid var(--ts-color-border);
  border-radius: 999px;
  color: var(--ts-color-text-secondary);
  background: var(--ts-glass-bg);
  -webkit-backdrop-filter: blur(var(--ts-glass-blur-panel));
  backdrop-filter: blur(var(--ts-glass-blur-panel));
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition: color 200ms ease, border-color 200ms ease, background-color 200ms ease, transform 180ms var(--lm-ease);
}

.atlas-sort:hover {
  border-color: rgba(var(--theme-rgb), 0.4);
  color: var(--ts-journal-accent-text);
  background: var(--ts-color-surface);
}

.atlas-sort:active {
  transform: scale(0.97);
}

.atlas-sort:focus-visible {
  outline: 2px solid var(--ts-journal-focus);
  outline-offset: 2px;
}

.atlas-sort-icon {
  width: 14px;
  height: 14px;
}

/* --------------------------------------------------------------------- grid */
.atlas-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-items: start;
}

@media (min-width: 640px) {
  .atlas-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 16px;
  }
}

@media (min-width: 1024px) {
  .atlas-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 20px;
  }
}

@media (min-width: 1600px) {
  .atlas-grid {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }
}

/* ---------------------------------------------------------------- transitions */
.atlas-grid > .atlas-item-enter-active {
  transition:
    opacity 620ms var(--lm-ease) calc(var(--stagger, 0) * 26ms),
    transform 680ms var(--ts-ease-enter) calc(var(--stagger, 0) * 26ms);
}

.atlas-grid > .atlas-item-leave-active {
  transition: none;
  pointer-events: none;
}

.atlas-grid > .atlas-item-enter-from {
  opacity: 0;
  transform: translate3d(0, 20px, 0) scale(0.985);
}

.atlas-grid > .atlas-item-leave-to {
  opacity: 0;
}

.atlas-grid > .atlas-item-move {
  transition: transform 560ms var(--lm-ease);
}

/* Refresh keeps the current collection visible and only signals at the edge. */
.atlas-refresh-line {
  position: sticky;
  z-index: 45;
  top: 0;
  height: 2px;
  margin-bottom: -2px;
  pointer-events: none;
  background: linear-gradient(90deg, transparent, var(--theme-primary), transparent);
  background-size: 40% 100%;
  background-repeat: no-repeat;
  animation: atlas-refresh 1.1s var(--ts-ease-breathe) infinite;
}

@keyframes atlas-refresh {
  0% { background-position: -40% 0; }
  100% { background-position: 140% 0; }
}

/* ------------------------------------------------------------------ skeleton */
.atlas-skeleton {
  padding-top: 18px;
}

.atlas-skeleton-head {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-bottom: 26px;
}

.atlas-skeleton-line,
.atlas-skeleton-hero,
.atlas-skeleton-cell {
  display: block;
  border-radius: 14px;
  background: var(--ts-color-surface-muted);
  animation: atlas-shimmer 1.6s var(--ts-ease-breathe) infinite;
}

.atlas-skeleton-line.is-kicker { width: 170px; height: 11px; border-radius: 6px; }
.atlas-skeleton-line.is-title { width: 300px; max-width: 60%; height: 52px; border-radius: 12px; }
.atlas-skeleton-line.is-sub { width: 360px; max-width: 72%; height: 13px; border-radius: 6px; }

.atlas-skeleton-hero {
  height: 348px;
  border-radius: 28px;
  margin-bottom: 20px;
}

.atlas-skeleton-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.atlas-skeleton-cell {
  aspect-ratio: 3 / 4;
  border-radius: 22px;
}

@keyframes atlas-shimmer {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

@media (min-width: 640px) {
  .atlas-skeleton-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
}

@media (min-width: 1024px) {
  .atlas-skeleton-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 20px; }
}

/* --------------------------------------------------------------------- states */
.atlas-state {
  display: flex;
  min-height: 46vh;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding-block: 64px 72px;
  text-align: center;
}

.atlas-state-art {
  position: relative;
  display: grid;
  width: 88px;
  height: 88px;
  margin-bottom: 20px;
  place-items: center;
  border-radius: 50%;
  color: var(--ts-color-text-tertiary);
  background: var(--ts-color-surface-muted);
}

.atlas-state-art svg {
  position: relative;
  z-index: 1;
  width: 30px;
  height: 30px;
}

.atlas-state-rings {
  position: absolute;
  inset: 10px;
  border: 1px solid var(--ts-color-border);
  border-radius: 50%;
}

.atlas-state-rings::after {
  position: absolute;
  inset: 9px;
  border: 1px dashed var(--ts-color-border);
  border-radius: 50%;
  content: '';
}

.atlas-state-art.is-error {
  color: var(--ts-color-danger);
  background: color-mix(in srgb, var(--ts-color-danger) 10%, transparent);
}

.atlas-state-title {
  margin: 0;
  color: var(--ts-color-text);
  font-family: var(--lm-font-display);
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.03em;
}

.atlas-state-copy {
  max-width: 380px;
  margin: 8px 0 0;
  color: var(--ts-color-text-secondary);
  font-size: 13px;
  line-height: 1.65;
  text-wrap: pretty;
}

.atlas-state-action {
  display: inline-flex;
  min-height: 38px;
  align-items: center;
  margin-top: 20px;
  padding: 0 16px;
  border-radius: 999px;
  color: #fff;
  background: var(--ts-journal-action);
  box-shadow: var(--ts-glass-rim), 0 8px 20px -12px rgba(var(--theme-rgb), 0.7);
  font-size: 12.5px;
  font-weight: 650;
  transition: filter 180ms ease, transform 160ms var(--lm-ease);
}

.atlas-state-action:hover { filter: brightness(0.94); }
.atlas-state-action:active { transform: scale(0.97); }

.atlas-state-action:focus-visible {
  outline: 2px solid var(--ts-journal-focus);
  outline-offset: 3px;
}

/* -------------------------------------------------------------------- mobile */
@media (max-width: 1023px) {
  .atlas-masthead {
    align-items: stretch;
    flex-direction: column;
    gap: 16px;
    padding: 4px 0 20px;
  }

  .atlas-coverage {
    width: 100%;
  }

  .atlas-headline-number {
    font-size: clamp(40px, 8vw, 56px);
  }
}

@media (max-width: 767px) {
  .atlas-shell {
    padding: 2px 0 40px;
  }

  .atlas-masthead {
    gap: 0;
    padding: 0 0 12px;
  }

  .atlas-kicker {
    margin-bottom: 6px;
    font-size: 9.5px;
  }

  .atlas-headline {
    gap: 9px;
  }

  .atlas-headline-number {
    font-size: clamp(36px, 10.5vw, 44px);
  }

  .atlas-headline-unit {
    font-size: 13.5px;
  }

  .atlas-summary {
    margin-top: 7px;
    gap: 6px;
    font-size: 11.5px;
  }

  /* The 34-segment meter is a desktop reading aid. On a phone the same fact
     already lives in「点亮 28 个省份」, and the space belongs to the photos. */
  .atlas-coverage {
    display: none;
  }

  .atlas-gridbar {
    padding: 0 0 8px;
  }

  .atlas-gridbar-note {
    font-size: 10px;
  }

  .atlas-sort {
    min-height: 32px;
    padding: 0 10px;
    font-size: 11px;
  }

  .atlas-skeleton-hero {
    height: 280px;
    border-radius: 20px;
  }

  .atlas-skeleton-cell {
    border-radius: 18px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .atlas-scroll {
    scroll-behavior: auto;
  }

  .atlas-pulse,
  .atlas-coverage-seg.is-lit,
  .atlas-skeleton-line,
  .atlas-skeleton-hero,
  .atlas-skeleton-cell,
  .atlas-refresh-line {
    animation: none !important;
  }

  .atlas-item-enter-active,
  .atlas-item-leave-active,
  .atlas-item-move,
  .atlas-sort,
  .atlas-state-action {
    transition: none !important;
  }
}
</style>