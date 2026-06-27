<template>
  <div class="flex-1 container mx-auto overflow-y-auto pb-8">
    <!-- No location data empty state -->
    <div v-if="showNoLocation" class="flex flex-col items-center justify-center py-20 text-center">
      <Map class="w-16 h-16 text-gray-300 dark:text-gray-600 mb-4" />
      <p class="text-gray-500 dark:text-gray-400 mb-4">这段时间还没有位置数据</p>
      <button
        @click="goMap"
        class="px-4 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >去地图视图标注一下</button>
    </div>

    <div v-else class="space-y-4">
      <StatsOverviewCard :overview="overview" :loading="overviewLoading" />
      <StatsAnnualTrendCard :data="trend" :loading="trendLoading" :error="trendError" @narrow-range="onNarrowRange" @retry="fetchTrend" />
      <StatsMonthlyRadarCard :data="radar" :most-recent-year="mostRecentYear" :loading="radarLoading" :error="radarError" @narrow-range="onNarrowRange" @retry="fetchRadar" />
      <StatsTopPlacesCard :places="places.top_places" :loading="placesLoading" :error="placesError" @go-location="onGoLocation" @retry="fetchPlaces" />
      <StatsRevisitsCard :revisits="places.revisits" :loading="placesLoading" :error="placesError" @retry="fetchPlaces" />
      <StatsHeatmapCard :data="heatmap.data" :loading="heatmapLoading" :error="heatmapError" @narrow-range="onNarrowRange" @retry="fetchHeatmap" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { Map } from 'lucide-vue-next';
import { useLocationStore } from '@/stores/locationStore';
import { locationService, type OverviewStats, type AnnualTrendItem, type MonthlyRadarItem, type PlacesResponse, type HeatmapRangeResponse } from '@/api/location';
import StatsOverviewCard from './stats/StatsOverviewCard.vue';
import StatsAnnualTrendCard from './stats/StatsAnnualTrendCard.vue';
import StatsMonthlyRadarCard from './stats/StatsMonthlyRadarCard.vue';
import StatsTopPlacesCard from './stats/StatsTopPlacesCard.vue';
import StatsRevisitsCard from './stats/StatsRevisitsCard.vue';
import StatsHeatmapCard from './stats/StatsHeatmapCard.vue';

const props = defineProps<{
  startDate?: string;
  endDate?: string;
  level: string;
  parentRegion?: string;
}>();
const emit = defineEmits<{ (e: 'narrow-range', start: string, end: string, year?: number): void; (e: 'go-location', name: string): void }>();

const store = useLocationStore();

const overview = ref<OverviewStats | null>(null);
const overviewLoading = ref(true);
const overviewError = ref(false);
const trend = ref<AnnualTrendItem[]>([]);
const trendLoading = ref(true);
const trendError = ref(false);
const radar = ref<MonthlyRadarItem[]>([]);
const radarLoading = ref(true);
const radarError = ref(false);
const places = ref<PlacesResponse>({ top_places: [], revisits: [] });
const placesLoading = ref(true);
const placesError = ref(false);
const heatmap = ref<HeatmapRangeResponse>({ total_photos: 0, total_days: 0, data: [] });
const heatmapLoading = ref(true);
const heatmapError = ref(false);
const mostRecentYear = ref<number | null>(null);

const showNoLocation = computed(() =>
  !overviewLoading.value && !overviewError.value && overview.value && !overview.value.has_location && overview.value.travel_days === 0
);

async function fetchOverview() {
  overviewLoading.value = true; overviewError.value = false;
  try { overview.value = await locationService.getOverview(props.startDate, props.endDate); }
  catch { overviewError.value = true; }
  finally { overviewLoading.value = false; }
}
async function fetchTrend() {
  trendLoading.value = true; trendError.value = false;
  try { trend.value = await locationService.getAnnualTrend(props.startDate, props.endDate); }
  catch { trendError.value = true; }
  finally { trendLoading.value = false; }
}
async function fetchRadar() {
  radarLoading.value = true; radarError.value = false;
  try { radar.value = await locationService.getMonthlyRadar(props.startDate, props.endDate); }
  catch { radarError.value = true; }
  finally { radarLoading.value = false; }
}
async function fetchPlaces() {
  placesLoading.value = true; placesError.value = false;
  try { places.value = await locationService.getPlaces(props.level, props.startDate, props.endDate, props.parentRegion); }
  catch { placesError.value = true; }
  finally { placesLoading.value = false; }
}
async function fetchHeatmap() {
  heatmapLoading.value = true; heatmapError.value = false;
  try { heatmap.value = await locationService.getHeatmapRange(props.startDate, props.endDate); }
  catch { heatmapError.value = true; }
  finally { heatmapLoading.value = false; }
}

async function loadAll() {
  await fetchOverview();
  fetchTrend(); fetchRadar(); fetchPlaces(); fetchHeatmap();
}

function onNarrowRange(start: string, end: string, year?: number) {
  emit('narrow-range', start, end, year);
}
function onGoLocation(name: string) {
  emit('go-location', name);
}
function goMap() {
  store.viewMode = 'map';
}

watch(() => [props.startDate, props.endDate], loadAll);
watch(() => [props.level, props.parentRegion], fetchPlaces);

onMounted(async () => {
  try { const years = await locationService.getYears(); mostRecentYear.value = years[0] ?? null; } catch { mostRecentYear.value = null; }
  loadAll();
});
</script>
