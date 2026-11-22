<template>
  <div
    ref="scrollRoot"
    class="location-timeline w-full custom-scrollbar transition-colors duration-300"
    @scroll="handleScroll"
  >
    <div class="tl-content">
      <header class="tl-masthead">
        <div class="tl-masthead-copy">
          <p class="la-eyebrow">
            <span class="la-eyebrow-dot" aria-hidden="true"></span>
            <span>位置时间轴</span>
            <span class="la-eyebrow-rule" aria-hidden="true"></span>
            <span class="tl-range">{{ rangeLabel }}</span>
          </p>
          <p class="la-display tl-masthead-title">时间手卷</p>
          <p class="tl-masthead-meta">
            <span><span class="la-num">{{ groupedNodes.length }}</span> 个月</span>
            <span class="tl-dot" aria-hidden="true"></span>
            <span><span class="la-num">{{ timelineNodes.length }}</span> 条记录</span>
            <template v-if="monthRange">
              <span class="tl-dot" aria-hidden="true"></span>
              <span class="la-num">{{ monthRange }}</span>
            </template>
          </p>
        </div>
        <span class="tl-masthead-seal" aria-hidden="true">卷</span>
      </header>

      <div v-if="activeGroup" class="tl-sticky">
        <div class="tl-sticky-inner">
          <span class="la-eyebrow">
            <span class="la-eyebrow-dot" aria-hidden="true"></span>
            {{ activeGroup.id.slice(0, 4) }} 年
          </span>
          <strong class="tl-sticky-month">{{ monthNumber(activeGroup) }} 月</strong>
          <span class="tl-sticky-count">{{ activeGroup.nodes.length }} 条</span>
          <span class="tl-sticky-progress" aria-hidden="true">
            <i :style="{ width: `${scrollProgress}%` }"></i>
          </span>
          <span class="tl-sticky-percent la-num">{{ Math.round(scrollProgress) }}%</span>
        </div>
      </div>

      <div v-if="loading && !loadingMore" class="la-loading">
        <span class="la-spinner" aria-hidden="true"></span>
        <span>正在展开时间手卷…</span>
      </div>

      <div v-else-if="!timelineNodes.length && !loading" class="la-empty tl-empty">
        <div class="tl-empty-art" aria-hidden="true">
          <Map />
        </div>
        <p class="la-title">暂无地理位置足迹</p>
        <p class="tl-empty-copy">带定位的照片会在这里按月份聚合成一卷时间手记。</p>
      </div>

      <div v-else class="tl-chapters">
        <section
          v-for="group in groupedNodes"
          :key="group.id"
          class="tl-chapter"
          :class="{ 'is-active': activeGroupId === group.id, 'is-collapsed': collapsedMonths[group.id] }"
          :data-month="group.id"
        >
          <div class="tl-spine">
            <div
              class="tl-spine-inner"
              role="button"
              tabindex="0"
              :aria-expanded="!collapsedMonths[group.id]"
              :aria-label="`${group.id.slice(0, 4)} 年 ${monthNumber(group)} 月，${group.nodes.length} 条记录，点击${collapsedMonths[group.id] ? '展开' : '收起'}`"
              @click="toggleMonth(group.id)"
              @keydown.enter.prevent="toggleMonth(group.id)"
              @keydown.space.prevent="toggleMonth(group.id)"
            >
              <span class="tl-spine-dot" aria-hidden="true"></span>
              <p class="la-eyebrow">
                <span class="la-eyebrow-dot" aria-hidden="true"></span>
                第 {{ monthNumber(group) }} 章
              </p>
              <h2
                class="tl-chapter-title"
                :aria-label="`${group.id.slice(0, 4)} 年 ${monthNumber(group)} 月`"
              >
                <span class="tl-chapter-month">{{ monthNumber(group) }}</span>
                <span class="tl-chapter-year">{{ group.id.slice(0, 4) }}</span>
              </h2>
              <p class="tl-chapter-meta">
                <span>{{ uniquePlaces(group) }} 个地点</span>
                <span class="tl-dot" aria-hidden="true"></span>
                <span>{{ group.nodes.length }} 条记录</span>
              </p>
              <span class="tl-chapter-toggle" aria-hidden="true">
                <ChevronDown />
              </span>
            </div>
          </div>

          <Transition name="tl-fold">
            <div
              v-show="!collapsedMonths[group.id]"
              class="tl-cards"
              :class="{ 'is-single': group.nodes.length === 1 }"
            >
              <div
                v-for="(node, nodeIdx) in group.nodes"
                :key="`${node.startDate}-${node.locationName}-${nodeIdx}`"
                class="tl-card"
                :style="{ '--i': Math.min(nodeIdx, 10) }"
                role="link"
                tabindex="0"
                :aria-label="cardAria(node)"
                @click="goToLocationDetail(node)"
                @keydown.enter.prevent="goToLocationDetail(node)"
                @keydown.space.prevent="goToLocationDetail(node)"
              >
                <div class="tl-card-media">
                  <img
                    v-if="node.coverId && !isCoverFailed(node.coverId)"
                    :src="getThumbnailUrl(node.coverId)"
                    alt=""
                    class="tl-card-image"
                    :class="{ 'is-loaded': isCoverLoaded(node.coverId) }"
                    loading="lazy"
                    decoding="async"
                    @load="markCoverLoaded(node.coverId)"
                    @error="markCoverFailed(node.coverId)"
                  />
                  <div v-else class="tl-card-fallback" aria-hidden="true">
                    <span class="tl-card-rings"></span>
                    <MapPin class="tl-card-fallback-pin" />
                  </div>

                  <span class="tl-card-shade" aria-hidden="true"></span>
                  <span class="tl-card-date">{{ nodeDateShort(node) }}</span>
                  <span class="tl-card-count">{{ node.photoCount }} 张</span>

                  <div class="tl-card-copy">
                    <span class="tl-card-level">
                      <MapPin aria-hidden="true" />
                      {{ levelLabel(node.level) }}
                    </span>
                    <h3 class="tl-card-place" :title="node.locationName">{{ node.locationName }}</h3>
                    <span
                      v-if="node.endDate && node.endDate !== node.startDate"
                      class="tl-card-meta"
                    >
                      {{ formatNodeDate(node.startDate) }} — {{ formatNodeDate(node.endDate) }}
                    </span>
                  </div>

                  <span class="tl-card-arrow" aria-hidden="true">
                    <ArrowUpRight />
                  </span>
                </div>
              </div>
            </div>
          </Transition>
        </section>
      </div>

      <div v-if="loadingMore" class="la-loading tl-load-more">
        <span class="la-spinner" aria-hidden="true"></span>
        <span>继续展开…</span>
      </div>
      <div v-else-if="!hasMore && timelineNodes.length" class="tl-end">
        <span class="la-eyebrow">手卷至此 · 已经到底啦</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, computed, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { MapPin, Map, ChevronDown, ArrowUpRight } from 'lucide-vue-next'
import { locationService } from '@/api/location'
import type { TimelineNode } from '@/types/location'
import type { Photo } from '@/types/album'
import { thumbnailUrl } from '@/utils/mediaUrl'

const props = defineProps<{
  startDate?: string
  endDate?: string
  level: string
}>()

const emit = defineEmits<{
  (e: 'click-photo', photo: Photo, contextPhotos: Photo[]): void
}>()

const router = useRouter()

const loading = ref(false)
const loadingMore = ref(false)
const hasMore = ref(true)
const skip = ref(0)
const limit = 100

const timelineNodes = ref<TimelineNode[]>([])
const collapsedMonths = ref<Record<string, boolean>>({})
const activeGroupId = ref('')
const scrollProgress = ref(0)
const loadedCovers = reactive(new Set<string>())
const failedCovers = reactive(new Set<string>())
const scrollRoot = ref<HTMLElement | null>(null)
let scrollParent: HTMLElement | null = null

interface MonthGroup {
  id: string
  label: string
  nodes: TimelineNode[]
}

const groupedNodes = computed(() => {
  const groups: MonthGroup[] = []
  let currentGroup: MonthGroup | null = null

  timelineNodes.value.forEach((node, index) => {
    const dateStr = node.endDate
    const date = new Date(dateStr)
    const monthId = `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}`
    const monthLabel = `${date.getFullYear()} · ${(date.getMonth() + 1).toString().padStart(2, '0')}`

    if (!currentGroup || currentGroup.id !== monthId) {
      currentGroup = {
        id: monthId,
        label: monthLabel,
        nodes: []
      }
      groups.push(currentGroup)
    }
    currentGroup.nodes.push(node)
  })

  return groups
})

const activeGroup = computed(() => (
  groupedNodes.value.find(group => group.id === activeGroupId.value)
  ?? groupedNodes.value[0]
  ?? null
))

const rangeLabel = computed(() => {
  if (!props.startDate && !props.endDate) return '全部时间'
  return `${props.startDate || '最早记录'} — ${props.endDate || '最新记录'}`
})

const monthRange = computed(() => {
  const ids = groupedNodes.value.map(group => group.id).sort()
  if (!ids.length) return ''
  const oldest = ids[0].replace('-', '.')
  const newest = ids[ids.length - 1].replace('-', '.')
  return oldest === newest ? newest : `${oldest} — ${newest}`
})

const monthNumber = (group: MonthGroup) => group.id.slice(5)

const uniquePlaces = (group: MonthGroup) => new Set(group.nodes.map(node => node.locationName)).size

const levelLabel = (level?: string) => (
  ({ province: '省份', city: '城市', district: '区县', scene: '景区' } as Record<string, string>)[level || 'city'] || '地点'
)

const fetchTimelineData = async (isLoadMore = false) => {
  if (loading.value || loadingMore.value || (!hasMore.value && isLoadMore)) return

  if (isLoadMore) {
    loadingMore.value = true
  } else {
    loading.value = true
    skip.value = 0
    hasMore.value = true
  }

  try {
    const res = await locationService.getTimelineNodes(skip.value, limit, props.startDate, props.endDate, props.level)
    const newNodes = res.nodes

    if (newNodes.length < limit) {
      hasMore.value = false
    }

    if (isLoadMore) {
      timelineNodes.value.push(...newNodes)
    } else {
      timelineNodes.value = newNodes
      collapsedMonths.value = {}
    }

    skip.value += limit
  } catch (e) {
    console.error('Failed to fetch timeline nodes', e)
  } finally {
    loading.value = false
    loadingMore.value = false
    requestAnimationFrame(() => updateScrollState())
  }
}

const getScrollParent = () => (
  scrollRoot.value?.closest('.ts-main-scroll') as HTMLElement | null
)

const updateScrollState = (scroller?: HTMLElement | null) => {
  const parent = scroller || scrollParent || getScrollParent()
  if (!parent) return

  const max = parent.scrollHeight - parent.clientHeight
  scrollProgress.value = max > 0
    ? Math.min(100, Math.max(0, (parent.scrollTop / max) * 100))
    : 0

  const viewportTop = parent.getBoundingClientRect().top
  const chapters = Array.from(scrollRoot.value?.querySelectorAll<HTMLElement>('[data-month]') ?? [])
  let current = activeGroupId.value || chapters[0]?.dataset.month || ''
  for (const chapter of chapters) {
    if (chapter.getBoundingClientRect().top - viewportTop <= 120) {
      current = chapter.dataset.month || current
    } else {
      break
    }
  }
  if (current) activeGroupId.value = current
}

const handleScroll = (e: Event) => {
  const target = e.target as HTMLElement | null
  const targetScrolls = Boolean(target && target.scrollHeight > target.clientHeight + 1)
  const scroller = (targetScrolls ? target : (scrollParent || target)) as HTMLElement | null
  updateScrollState(scroller)

  if (!scroller) return
  if (scroller.scrollHeight - scroller.scrollTop <= scroller.clientHeight + 240) {
    fetchTimelineData(true)
  }
}

const handleResize = () => {
  updateScrollState()
}

const toggleMonth = (monthId: string) => {
  collapsedMonths.value[monthId] = !collapsedMonths.value[monthId]
  requestAnimationFrame(() => updateScrollState())
  // Re-read the spine after the fold animation has changed the page height.
  window.setTimeout(() => updateScrollState(), 520)
}

const formatNodeDate = (dateStr: string) => {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return `${date.getFullYear()}.${(date.getMonth() + 1).toString().padStart(2, '0')}.${date.getDate().toString().padStart(2, '0')}`;
}

const nodeDateShort = (node: TimelineNode) => {
  const start = formatNodeDate(node.startDate)
  if (!start) return ''
  const shortStart = start.slice(5)
  if (node.endDate && node.endDate !== node.startDate) {
    const end = formatNodeDate(node.endDate)
    if (end) return `${shortStart}–${end.slice(5)}`
  }
  return shortStart
}

const cardAria = (node: TimelineNode) => (
  `打开${levelLabel(node.level)}「${node.locationName}」，${node.photoCount} 张影像，${formatNodeDate(node.startDate)}`
)

const markCoverLoaded = (coverId?: string) => {
  if (coverId) loadedCovers.add(coverId)
}

const markCoverFailed = (coverId?: string) => {
  if (coverId) failedCovers.add(coverId)
}

const isCoverLoaded = (coverId?: string) => Boolean(coverId && loadedCovers.has(coverId))

const isCoverFailed = (coverId?: string) => Boolean(coverId && failedCovers.has(coverId))

const getThumbnailUrl = (photoId: string) => {
  return thumbnailUrl(photoId, 'medium')
}

const goToLocationDetail = (node: TimelineNode) => {
  router.push({
    name: 'LocationDetail',
    params: { name: node.locationName },
    query: {
      level: node.level || 'city',
      startDate: node.startDate,
      endDate: node.endDate
    }
  })
}

watch([() => props.startDate, () => props.endDate, () => props.level], () => {
  fetchTimelineData()
})

watch(groupedNodes, (groups) => {
  if (!groups.length) {
    activeGroupId.value = ''
    return
  }
  if (!groups.some(group => group.id === activeGroupId.value)) {
    activeGroupId.value = groups[0].id
  }
}, { immediate: true })

onMounted(() => {
  fetchTimelineData()
  scrollParent = getScrollParent()
  scrollParent?.addEventListener('scroll', handleScroll, { passive: true })
  window.addEventListener('resize', handleResize, { passive: true })
  requestAnimationFrame(() => updateScrollState())
})

onBeforeUnmount(() => {
  scrollParent?.removeEventListener('scroll', handleScroll)
  window.removeEventListener('resize', handleResize)
  scrollParent = null
})
</script>

<style scoped>
.location-timeline {
  color: var(--ts-color-text);
  background: var(--ts-color-page);
}

.tl-content {
  width: 100%;
  max-width: 1240px;
  margin-inline: auto;
  padding: 4px 0 72px;
}

/* ------------------------------------------------------------------ masthead */
.tl-masthead {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding: 10px 0 22px;
}

.tl-masthead-copy {
  min-width: 0;
}

.tl-range {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tl-masthead-title {
  margin: 7px 0 0;
  font-size: clamp(30px, 3.2vw, 42px);
}

.tl-masthead-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 9px 0 0;
  color: var(--ts-color-text-secondary);
  font-size: 12px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.01em;
}

.tl-dot {
  width: 3px;
  height: 3px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--ts-color-text-tertiary);
}

.tl-masthead-seal {
  display: grid;
  width: 46px;
  height: 46px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid rgba(var(--theme-rgb), 0.3);
  border-radius: 14px;
  color: var(--ts-journal-accent-text);
  background: rgba(var(--theme-rgb), 0.06);
  font-family: var(--lm-font-display);
  font-size: 24px;
  font-weight: 700;
  line-height: 1;
  transform: rotate(-4deg);
  user-select: none;
}

/* --------------------------------------------------------------- sticky month */
.tl-sticky {
  position: sticky;
  z-index: 30;
  top: 0;
  margin: 0 0 12px;
  padding: 7px 0;
  border-bottom: 1px solid var(--ts-color-divider);
  background: color-mix(in srgb, var(--ts-color-page) 88%, transparent);
  -webkit-backdrop-filter: blur(16px) saturate(130%);
  backdrop-filter: blur(16px) saturate(130%);
}

.tl-sticky-inner {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.tl-sticky-month {
  color: var(--ts-color-text);
  font-family: var(--lm-font-display);
  font-size: 19px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: -0.03em;
}

.tl-sticky-count {
  color: var(--ts-color-text-secondary);
  font-size: 11px;
  white-space: nowrap;
}

.tl-sticky-progress {
  position: relative;
  flex: 1 1 auto;
  max-width: 200px;
  height: 2px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--ts-color-border);
}

.tl-sticky-progress i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(to right, rgba(var(--theme-rgb), 0.55), var(--theme-primary));
  transition: width 160ms linear;
}

.tl-sticky-percent {
  color: var(--ts-color-text-tertiary);
  font-size: 10px;
  white-space: nowrap;
}

/* ------------------------------------------------------------------ chapters */
.tl-chapters {
  --tl-spine: clamp(150px, 15vw, 190px);
  display: flex;
  flex-direction: column;
  gap: 30px;
}

.tl-chapter {
  position: relative;
  display: grid;
  grid-template-columns: var(--tl-spine) minmax(0, 1fr);
  column-gap: 36px;
  align-items: stretch;
}

.tl-spine {
  position: relative;
  min-width: 0;
  padding-right: 26px;
  border-right: 1px dashed var(--ts-color-border);
}

.tl-spine-inner {
  position: sticky;
  top: 76px;
  padding: 6px 0 22px;
  cursor: pointer;
  outline: none;
}

.tl-spine-inner:focus-visible {
  outline: 2px solid var(--ts-journal-focus);
  outline-offset: 6px;
  border-radius: 10px;
}

.tl-spine-dot {
  position: absolute;
  top: 18px;
  right: -5px;
  width: 9px;
  height: 9px;
  border: 2px solid var(--ts-color-page);
  border-radius: 50%;
  background: var(--ts-color-text-tertiary);
  box-shadow: 0 0 0 0 rgba(var(--theme-rgb), 0);
  transition: background-color 260ms ease, box-shadow 260ms ease, transform 260ms var(--lm-ease);
}

.tl-chapter.is-active .tl-spine-dot {
  background: var(--theme-primary);
  box-shadow: 0 0 0 5px rgba(var(--theme-rgb), 0.13), 0 0 16px rgba(var(--theme-rgb), 0.55);
  transform: scale(1.08);
}

.tl-chapter-title {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  margin: 5px 0 0;
  color: var(--ts-color-text);
}

.tl-chapter-month {
  font-family: var(--lm-font-display);
  font-size: clamp(54px, 5vw, 74px);
  font-weight: 700;
  line-height: 0.78;
  letter-spacing: -0.065em;
  transition: color 220ms ease;
}

.tl-chapter.is-active .tl-chapter-month {
  color: var(--ts-journal-accent-text);
}

.tl-chapter-year {
  margin-bottom: 7px;
  color: var(--ts-color-text-secondary);
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.2em;
}

.tl-chapter-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 10px 0 0;
  color: var(--ts-color-text-secondary);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.tl-chapter-toggle {
  display: inline-grid;
  width: 28px;
  height: 28px;
  margin-top: 14px;
  place-items: center;
  border: 1px solid var(--ts-color-border);
  border-radius: 50%;
  color: var(--ts-color-text-secondary);
  background: var(--ts-color-surface);
  transition: transform 320ms var(--lm-ease), color 180ms ease, border-color 180ms ease;
}

.tl-chapter-toggle svg {
  width: 14px;
  height: 14px;
}

.tl-chapter.is-collapsed .tl-chapter-toggle {
  transform: rotate(-90deg);
}

.tl-spine-inner:hover .tl-chapter-toggle {
  border-color: rgba(var(--theme-rgb), 0.4);
  color: var(--ts-journal-accent-text);
}

/* --------------------------------------------------------------------- cards */
.tl-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
  min-width: 0;
}

.tl-cards.is-single {
  grid-template-columns: minmax(0, 1fr);
}

.tl-card {
  position: relative;
  min-width: 0;
  cursor: pointer;
  outline: none;
  animation: tl-card-in 560ms var(--lm-ease) both;
  animation-delay: calc(var(--i, 0) * 38ms);
  -webkit-tap-highlight-color: transparent;
}

.tl-card-media {
  position: relative;
  isolation: isolate;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border-radius: 20px;
  background: var(--ts-color-surface-muted);
  box-shadow:
    0 1px 2px rgb(15 23 42 / 5%),
    0 18px 38px -30px rgb(15 23 42 / 45%);
  transition: transform 420ms var(--lm-ease), box-shadow 420ms var(--lm-ease);
}

.tl-cards.is-single .tl-card-media {
  aspect-ratio: 16 / 9;
}

.tl-card-image {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  filter: blur(14px) saturate(0.55);
  transform: scale(1.045);
  transition:
    opacity 620ms var(--lm-ease),
    filter 720ms var(--lm-ease),
    transform 900ms var(--lm-ease);
}

.tl-card-image.is-loaded {
  opacity: 1;
  filter: blur(0) saturate(1);
  transform: scale(1);
}

.tl-card-shade {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background:
    linear-gradient(to top, rgb(6 10 18 / 84%) 0%, rgb(6 10 18 / 48%) 32%, transparent 60%),
    linear-gradient(to bottom, rgb(6 10 18 / 26%) 0%, transparent 28%);
  transition: opacity 420ms var(--lm-ease);
}

.tl-card-date,
.tl-card-count {
  position: absolute;
  z-index: 3;
  top: 13px;
  display: inline-flex;
  height: 26px;
  align-items: center;
  border: 1px solid rgb(255 255 255 / 24%);
  border-radius: 999px;
  color: rgb(255 255 255 / 94%);
  background: rgb(9 14 24 / 38%);
  -webkit-backdrop-filter: blur(12px) saturate(140%);
  backdrop-filter: blur(12px) saturate(140%);
  font-size: 10.5px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.tl-card-date {
  left: 13px;
  padding: 0 9px;
}

.tl-card-count {
  right: 13px;
  padding: 0 9px;
  color: rgb(255 255 255 / 78%);
}

.tl-card-copy {
  position: absolute;
  z-index: 2;
  right: 16px;
  bottom: 15px;
  left: 16px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  color: #fff;
  pointer-events: none;
}

.tl-card-level {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: rgb(255 255 255 / 64%);
  font-size: 10px;
  font-weight: 650;
  letter-spacing: 0.13em;
  text-transform: uppercase;
}

.tl-card-level svg {
  width: 11px;
  height: 11px;
}

.tl-card-place {
  margin: 0;
  color: #fff;
  font-size: 17px;
  font-weight: 650;
  line-height: 1.3;
  letter-spacing: -0.01em;
  text-shadow: 0 1px 14px rgb(0 0 0 / 32%);
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow-wrap: anywhere;
}

.tl-card-meta {
  display: block;
  overflow: hidden;
  color: rgb(255 255 255 / 64%);
  font-size: 11px;
  line-height: 1.4;
  font-variant-numeric: tabular-nums;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tl-card-arrow {
  position: absolute;
  z-index: 3;
  right: 13px;
  bottom: 14px;
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 42%);
  border-radius: 50%;
  color: #fff;
  background: rgb(255 255 255 / 10%);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  opacity: 0;
  transform: translate3d(-4px, 4px, 0) scale(0.9);
  transition: opacity 300ms var(--lm-ease), transform 380ms var(--lm-ease), background-color 220ms ease;
}

.tl-card-arrow svg {
  width: 14px;
  height: 14px;
}

.tl-card-fallback {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  overflow: hidden;
  background:
    radial-gradient(120% 90% at 18% 0%, rgba(var(--theme-rgb), 0.26), transparent 62%),
    linear-gradient(150deg, var(--ts-color-surface-muted), var(--ts-color-surface));
}

.tl-card-rings {
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

.tl-card-fallback-pin {
  position: relative;
  width: 30px;
  height: 30px;
  color: var(--theme-primary);
  opacity: 0.6;
}

@media (hover: hover) and (pointer: fine) {
  .tl-card:hover {
    z-index: 3;
  }

  .tl-card:hover .tl-card-media {
    transform: translate3d(0, -5px, 0);
    box-shadow:
      0 1px 2px rgb(15 23 42 / 7%),
      0 30px 58px -30px rgb(15 23 42 / 62%);
  }

  .tl-card:hover .tl-card-image {
    transform: scale(1.055);
  }

  .tl-card:hover .tl-card-shade {
    opacity: 1;
  }

  .tl-card:hover .tl-card-arrow {
    opacity: 1;
    transform: translate3d(0, 0, 0) scale(1);
  }
}

.tl-card:focus-visible .tl-card-media {
  box-shadow:
    0 0 0 2px var(--ts-journal-focus),
    0 0 0 6px var(--ts-color-page),
    0 24px 48px -26px rgb(15 23 42 / 52%);
}

@media (hover: none) {
  .tl-card:active .tl-card-media {
    transform: scale(0.985);
  }
}

/* ------------------------------------------------------------------- states */
.tl-empty {
  min-height: 52vh;
  border: 1px solid var(--ts-color-border);
  border-radius: 24px;
  background: var(--ts-color-surface);
}

.tl-empty-art {
  position: relative;
  display: grid;
  width: 84px;
  height: 84px;
  margin-bottom: 8px;
  place-items: center;
  border-radius: 50%;
  color: var(--theme-primary);
  background: rgba(var(--theme-rgb), 0.08);
}

.tl-empty-art::before,
.tl-empty-art::after {
  position: absolute;
  border: 1px solid rgba(var(--theme-rgb), 0.18);
  border-radius: 50%;
  content: '';
}

.tl-empty-art::before { inset: 9px; }
.tl-empty-art::after { inset: 18px; border-style: dashed; }

.tl-empty-art svg {
  position: relative;
  z-index: 1;
  width: 28px;
  height: 28px;
}

.tl-empty-copy {
  max-width: 320px;
  margin: 0;
  color: var(--ts-color-text-secondary);
  font-size: 12.5px;
  line-height: 1.65;
  text-wrap: pretty;
}

.tl-load-more {
  min-height: 76px;
}

.tl-end {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 34px 0 6px;
}

.tl-end::before,
.tl-end::after {
  width: 44px;
  height: 1px;
  content: '';
  background: linear-gradient(to right, transparent, var(--ts-color-border));
}

.tl-end::after {
  background: linear-gradient(to left, transparent, var(--ts-color-border));
}

/* ---------------------------------------------------------------- transitions */
.tl-fold-enter-active,
.tl-fold-leave-active {
  overflow: hidden;
  transition:
    max-height 480ms var(--lm-ease),
    opacity 260ms ease;
}

.tl-fold-enter-from,
.tl-fold-leave-to {
  max-height: 0;
  opacity: 0;
}

.tl-fold-enter-to,
.tl-fold-leave-from {
  max-height: 60000px;
  opacity: 1;
}

@keyframes tl-card-in {
  from {
    opacity: 0;
    transform: translate3d(0, 18px, 0) scale(0.99);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0) scale(1);
  }
}

/* ------------------------------------------------------------------ responsive */
@media (max-width: 1023px) {
  .tl-chapters {
    --tl-spine: 136px;
    gap: 26px;
  }

  .tl-chapter {
    column-gap: 24px;
  }

  .tl-spine {
    padding-right: 20px;
  }

  .tl-cards {
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }

  .tl-cards.is-single .tl-card-media {
    aspect-ratio: 16 / 9;
  }

  .tl-chapter-month {
    font-size: clamp(46px, 6vw, 58px);
  }
}

@media (max-width: 767px) {
  .tl-content {
    padding: 2px 0 56px;
  }

  .tl-masthead {
    align-items: flex-start;
    gap: 14px;
    padding: 0 0 16px;
  }

  .tl-masthead-title {
    margin-top: 5px;
    font-size: clamp(28px, 9vw, 36px);
  }

  .tl-masthead-meta {
    margin-top: 7px;
    gap: 6px;
    font-size: 11px;
  }

  .tl-masthead-seal {
    width: 38px;
    height: 38px;
    border-radius: 12px;
    font-size: 20px;
  }

  .tl-range {
    max-width: 46vw;
  }

  .tl-sticky {
    margin-bottom: 10px;
    padding: 6px 0;
  }

  .tl-sticky-inner {
    gap: 9px;
  }

  .tl-sticky-month {
    font-size: 17px;
  }

  .tl-sticky-progress {
    max-width: none;
  }

  .tl-sticky-percent {
    display: none;
  }

  .tl-chapters {
    gap: 22px;
  }

  .tl-chapter {
    display: block;
  }

  .tl-spine {
    padding: 0 0 12px;
    border-right: 0;
    border-bottom: 1px solid var(--ts-color-divider);
  }

  .tl-spine-inner {
    position: relative;
    top: auto;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-rows: auto auto;
    column-gap: 14px;
    padding: 0 0 2px;
    align-items: center;
  }

  .tl-spine-dot {
    display: none;
  }

  .tl-spine-inner > .la-eyebrow {
    grid-column: 1 / -1;
    margin-bottom: 2px;
  }

  .tl-chapter-title {
    grid-row: 2;
    grid-column: 1;
    margin: 0;
  }

  .tl-chapter-month {
    font-size: 44px;
  }

  .tl-chapter-year {
    margin-bottom: 4px;
    font-size: 10px;
  }

  .tl-chapter-meta {
    grid-row: 2;
    grid-column: 2;
    margin: 0;
    font-size: 10.5px;
  }

  .tl-chapter-toggle {
    grid-row: 2;
    grid-column: 3;
    margin-top: 0;
  }

  .tl-cards {
    margin-top: 14px;
  }

  .tl-card-media {
    border-radius: 18px;
    aspect-ratio: 4 / 3;
  }

  .tl-card-copy {
    right: 12px;
    bottom: 12px;
    left: 12px;
  }

  .tl-card-place {
    font-size: 15.5px;
  }

  .tl-card-date,
  .tl-card-count {
    top: 10px;
    height: 24px;
    font-size: 10px;
  }

  .tl-card-date { left: 10px; }
  .tl-card-count { right: 10px; }

  .tl-card-arrow {
    right: 10px;
    bottom: 11px;
    width: 26px;
    height: 26px;
    opacity: 0.9;
    transform: none;
  }

  .tl-empty {
    min-height: 46vh;
    border-radius: 20px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .tl-card,
  .tl-card-image,
  .tl-card-media,
  .tl-card-shade,
  .tl-card-arrow,
  .tl-chapter-toggle,
  .tl-spine-dot,
  .tl-sticky-progress i {
    animation: none !important;
    transition: none !important;
  }

  .tl-card {
    opacity: 1;
    transform: none;
  }

  .tl-card-image {
    opacity: 1;
    filter: none;
    transform: none;
  }

  .tl-fold-enter-active,
  .tl-fold-leave-active {
    transition: none !important;
  }
}
</style>