<template>
  <SurfaceCard padding="lg" :elevated="false" class="stats-place-card">
    <div class="stats-place-head">
      <div class="min-w-0">
        <p class="la-panel-kicker">PLACE RANKING</p>
        <h2 class="stats-title">留下最多照片的地方</h2>
        <p class="stats-caption">{{ scope }} · 按照片数量排名</p>
      </div>
      <span class="stats-place-head-icon" aria-hidden="true"><MapPin /></span>
    </div>

    <div v-if="loading" class="stats-empty"><el-skeleton :rows="6" animated /></div>
    <div v-else-if="error" class="stats-empty">
      <span>地点统计加载失败</span>
      <button class="text-primary-500" @click="$emit('retry')">重试</button>
    </div>
    <div v-else-if="!feature" class="stats-empty">这段时间还没有地点记录</div>

    <template v-else-if="feature">
      <div
        class="stats-place-feature"
        role="button"
        tabindex="0"
        :aria-label="`${feature.name}，${feature.photo_count} 张照片，查看这个地点`"
        @click="$emit('go-location', feature.name)"
        @keydown.enter.prevent="$emit('go-location', feature.name)"
        @keydown.space.prevent="$emit('go-location', feature.name)"
      >
        <div class="stats-place-feature-media">
          <img
            v-if="coverOf(feature.name)"
            :src="coverOf(feature.name)"
            alt=""
            loading="lazy"
            @error="failedCovers.add(feature.name)"
          />
          <span v-else class="stats-place-fallback" aria-hidden="true"><MapPin /></span>
          <span class="stats-place-scrim" aria-hidden="true"></span>
          <span class="stats-place-rank">NO.01</span>
          <span class="stats-place-cover-count">{{ feature.photo_count.toLocaleString() }} 张</span>
        </div>

        <div class="stats-place-feature-copy">
          <span class="la-panel-kicker">MOST PHOTOGRAPHED</span>
          <h3 class="stats-place-feature-name">{{ feature.name }}</h3>
          <span class="stats-place-feature-meta">
            {{ feature.photo_count.toLocaleString() }} 张照片<span aria-hidden="true"> · </span>{{ feature.visit_count }} 个记录日
          </span>
          <span v-if="rangeOf(feature)" class="stats-place-feature-dates">{{ rangeOf(feature) }}</span>
          <span class="stats-place-cta">走进这里 <ArrowUpRight aria-hidden="true" /></span>
        </div>
      </div>

      <ol v-if="rest.length" class="stats-place-list">
        <li v-for="(place, index) in rest" :key="place.name">
          <button
            class="place-row stats-place-row"
            :aria-label="`${place.name}，${place.photo_count} 张照片，查看照片`"
            @click="$emit('go-location', place.name)"
          >
            <span class="stats-place-row-rank" aria-hidden="true">{{ String(index + 2).padStart(2, '0') }}</span>
            <span class="stats-place-row-cover">
              <img
                v-if="coverOf(place.name)"
                :src="coverOf(place.name)"
                alt=""
                loading="lazy"
                @error="failedCovers.add(place.name)"
              />
              <MapPin v-else aria-hidden="true" />
            </span>
            <span class="stats-place-row-body">
              <span class="stats-place-row-top">
                <span class="stats-place-row-name" :title="place.name">{{ place.name }}</span>
                <span class="stats-place-row-count">{{ place.photo_count.toLocaleString() }}<small>张</small></span>
              </span>
              <span class="stats-place-row-bar" aria-hidden="true">
                <span :style="{ width: `${(place.photo_count / maxCount) * 100}%` }"></span>
              </span>
              <span v-if="rangeOf(place)" class="stats-place-row-meta">{{ rangeOf(place) }}</span>
            </span>
          </button>
        </li>
      </ol>

      <p v-if="places.length > 5" class="stats-caption stats-place-more">
        以上为照片最多的前 5 个地点，共 {{ places.length }} 个。
      </p>
    </template>
  </SurfaceCard>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { ArrowUpRight, MapPin } from 'lucide-vue-next'
import SurfaceCard from '@/components/ui/SurfaceCard.vue'
import type { PlaceStats } from '@/api/location'

const props = defineProps<{
  places: PlaceStats[]
  covers: Record<string, string>
  scope: string
  loading: boolean
  error: boolean
}>()

defineEmits<{ (e: 'go-location', name: string): void; (e: 'retry'): void }>()

const feature = computed(() => props.places[0] ?? null)
const rest = computed(() => props.places.slice(1, 5))
const maxCount = computed(() => Math.max(...props.places.map(p => p.photo_count), 1))
const failedCovers = reactive(new Set<string>())

watch(() => props.covers, () => failedCovers.clear())

function coverOf(name: string) {
  return failedCovers.has(name) ? '' : (props.covers[name] || '')
}

function rangeOf(place: PlaceStats) {
  const first = place.first_date ? place.first_date.replaceAll('-', '.') : ''
  const last = place.last_date ? place.last_date.replaceAll('-', '.') : ''
  if (!first) return ''
  return last && last !== first ? `${first} — ${last}` : first
}
</script>

<style scoped>
.place-row:hover {
  background: var(--ts-color-surface-muted);
}
</style>