<template>
  <div class="location-stats flex-1 min-h-0 mx-auto w-full max-w-screen-2xl overflow-y-auto pb-8">
    <div class="space-y-4">
      <header class="flex flex-wrap items-start justify-between gap-3 py-2">
        <div><h1 class="text-xl font-semibold tracking-tight">足迹统计</h1><p class="stats-caption mt-1">{{ rangeLabel }} · 从照片中回看走过的地方与记录的日子</p></div>
        <details class="stats-method">
          <summary class="stats-caption cursor-pointer py-1">统计口径</summary>
          <p class="stats-caption mt-2 max-w-lg">概览、时间趋势和日历跟随时间筛选，包含整个图库；城市和省份来自照片中的位置。时间趋势、记录天数和照片数包含无位置的照片，仅统计有拍摄日期的记录。顶部地区层级仅影响地点排名与地点记录。</p>
        </details>
      </header>
      <StatsOverviewCard :overview="overviewError ? null : overview" :loading="overviewLoading" />
      <div v-if="overviewError" class="stats-caption flex items-center gap-3" role="alert">足迹概览加载失败<button class="text-primary-500" @click="fetchOverview">重试</button></div>
      <div class="stats-main stats-main-primary">
        <StatsAnnualTrendCard :data="heatmap.data" :loading="heatmapLoading" :error="heatmapError" @narrow-range="onNarrowRange" @retry="fetchHeatmap" />
        <StatsTopPlacesCard :places="places.top_places" :covers="covers" :scope="placeScope" :loading="placesLoading" :error="placesError" @go-location="onGoLocation" @retry="fetchPlaces" />
      </div>
      <StatsHeatmapCard :data="heatmap.data" :loading="heatmapLoading" :error="heatmapError" @narrow-range="onNarrowRange" @retry="fetchHeatmap" />
      <StatsPersonPlacesCard :start-date="startDate" :end-date="endDate" :level="level" :parent-region="parentRegion" />
      <StatsRevisitsCard :revisits="places.revisits" :scope="placeScope" :loading="placesLoading" :error="placesError" @retry="fetchPlaces" @go-location="onGoLocation" />
      <p v-if="!overviewError && overview?.farthest_place" class="stats-caption px-1">最远记录地点 · {{ overview.farthest_place }} · 约 {{ Math.round(overview.farthest_distance_km).toLocaleString() }} 公里</p>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { mapPhotoToImage } from '@/stores/photoStore'
import { locationService, type OverviewStats, type PlacesResponse, type HeatmapRangeResponse } from '@/api/location'
import type { Location } from '@/types/location'
import StatsPersonPlacesCard from './stats/StatsPersonPlacesCard.vue'
import StatsOverviewCard from './stats/StatsOverviewCard.vue'
import StatsAnnualTrendCard from './stats/StatsAnnualTrendCard.vue'
import StatsTopPlacesCard from './stats/StatsTopPlacesCard.vue'
import StatsRevisitsCard from './stats/StatsRevisitsCard.vue'
import StatsHeatmapCard from './stats/StatsHeatmapCard.vue'
import './stats/stats.css'
const props = defineProps<{ startDate?: string; endDate?: string; level: string; parentRegion?: string; locations?: Location[] }>()
const emit = defineEmits<{ (e: 'narrow-range', start: string, end: string, year?: number): void; (e: 'go-location', name: string): void }>()
const overview = ref<OverviewStats | null>(null)
const overviewLoading = ref(true)
const overviewError = ref(false)
const places = ref<PlacesResponse>({ top_places: [], revisits: [] })
const placesLoading = ref(true)
const placesError = ref(false)
const heatmap = ref<HeatmapRangeResponse>({ total_photos: 0, total_days: 0, data: [] })
const heatmapLoading = ref(true)
const heatmapError = ref(false)
const rangeLabel = computed(() => !props.startDate && !props.endDate ? '全部时间' : `${props.startDate || '最早记录'} 至 ${props.endDate || '最新记录'}`)
const placeScope = computed(() => `${props.parentRegion ? props.parentRegion + ' · ' : ''}${({ city: '城市', province: '省份', district: '区县', scene: '景区' } as Record<string, string>)[props.level] || '城市'}`)
const covers = computed(() => Object.fromEntries((props.locations ?? []).filter(l => l.cover).map(l => [l.name, mapPhotoToImage(l.cover!).thumbnail])))
let overviewRequest = 0, placesRequest = 0, heatmapRequest = 0
async function fetchOverview() {
  const id = ++overviewRequest
  overviewLoading.value = true; overviewError.value = false
  try { const value = await locationService.getOverview(props.startDate, props.endDate); if (id === overviewRequest) overview.value = value }
  catch { if (id === overviewRequest) overviewError.value = true }
  finally { if (id === overviewRequest) overviewLoading.value = false }
}
async function fetchPlaces() {
  const id = ++placesRequest
  placesLoading.value = true; placesError.value = false
  try { const value = await locationService.getPlaces(props.level, props.startDate, props.endDate, props.parentRegion); if (id === placesRequest) places.value = value }
  catch { if (id === placesRequest) placesError.value = true }
  finally { if (id === placesRequest) placesLoading.value = false }
}
async function fetchHeatmap() {
  const id = ++heatmapRequest
  heatmapLoading.value = true; heatmapError.value = false
  try { const value = await locationService.getHeatmapRange(props.startDate, props.endDate); if (id === heatmapRequest) heatmap.value = value }
  catch { if (id === heatmapRequest) heatmapError.value = true }
  finally { if (id === heatmapRequest) heatmapLoading.value = false }
}
function onNarrowRange(start: string, end: string, year?: number) { emit('narrow-range', start, end, year) }
function onGoLocation(name: string) { emit('go-location', name) }
watch(() => [props.startDate, props.endDate], () => { fetchOverview(); fetchHeatmap() }, { immediate: true })
watch(() => [props.startDate, props.endDate, props.level, props.parentRegion], fetchPlaces, { immediate: true })
onBeforeUnmount(() => { overviewRequest++; placesRequest++; heatmapRequest++ })
</script>
<style scoped>
.stats-method { max-width: 480px; }
.stats-method summary { text-align: right; }
@media (max-width: 639px) { .stats-method summary { text-align: left; } }
</style>
