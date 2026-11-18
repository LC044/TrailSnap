<template>
  <div class="ts-page-background ts-browse-page ts-bottom-safe mx-auto min-h-full w-full max-w-screen-2xl px-[var(--ts-page-gutter)]" data-testid="footprint-list-page">
    <header class="ts-browse-header flex items-center justify-between gap-3">
      <div class="min-w-0">
        <h1 class="ts-page-title text-gray-900 dark:text-white">足迹</h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {{ loading ? '正在整理你的旅行记忆…' : `共 ${format(filteredCities.length)} 条足迹` }}
        </p>
      </div>
      <div class="ts-liquid-glass ts-glass-toolbar" aria-label="足迹操作">
        <RouterLink to="/footprint" class="ts-glass-button" aria-label="打开 3D 足迹地图" title="3D 足迹地图"><Globe2 class="h-5 w-5" /></RouterLink>
      </div>
    </header>

    <!-- 移动端：年度统计横条 -->
    <div class="ts-surface mt-4 grid grid-cols-3 divide-x divide-gray-100 rounded-2xl dark:divide-gray-800 lg:hidden" aria-label="足迹统计">
      <div v-for="metric in mobileMetrics" :key="metric.label" class="flex flex-col items-center gap-1 px-2 py-3">
        <component :is="metric.icon" class="h-4 w-4 text-primary-500" aria-hidden="true" />
        <strong class="text-base font-semibold text-gray-900 dark:text-white">{{ metric.value }}</strong>
        <span class="text-xs text-gray-500 dark:text-gray-400">{{ metric.label }}</span>
      </div>
    </div>

    <!-- 筛选区 -->
    <div class="ts-surface mt-4 rounded-2xl p-3 sm:p-4">
      <!-- 桌面：搜索 + 年份 + 地点 + 重置 -->
      <div class="hidden items-center gap-3 md:flex">
        <label class="relative min-w-0 flex-1">
          <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
          <input v-model="search" type="search" class="ts-input w-full pl-9" placeholder="搜索足迹标题或地点…" aria-label="搜索足迹" />
        </label>
        <select v-model="year" class="ts-input w-36" aria-label="按年份筛选" :disabled="loading">
          <option :value="null">全部年份</option>
          <option v-for="value in years" :key="value" :value="value">{{ value }} 年</option>
        </select>
        <select v-model="province" class="ts-input w-40" aria-label="按地点筛选">
          <option :value="null">全部地点</option>
          <option v-for="value in provinces" :key="value" :value="value">{{ value }}</option>
        </select>
        <button class="ts-button ts-button-secondary shrink-0" :disabled="!hasActiveFilters" @click="resetFilters">
          <RotateCcw class="h-4 w-4" aria-hidden="true" />重置筛选
        </button>
      </div>
      <!-- 移动端：搜索 + 筛选抽屉入口 -->
      <div class="flex items-center gap-2 md:hidden">
        <label class="relative min-w-0 flex-1">
          <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
          <input v-model="search" type="search" class="ts-input w-full pl-9" placeholder="搜索足迹标题或地点…" aria-label="搜索足迹" />
        </label>
        <button class="ts-button ts-button-secondary shrink-0 border-primary-200 text-primary-600 dark:border-primary-800 dark:text-primary-400" aria-label="打开筛选" :aria-expanded="filterOpen" @click="filterOpen = true">
          <SlidersHorizontal class="h-4 w-4" aria-hidden="true" />筛选
        </button>
      </div>
      <div v-if="activeChips.length" class="mt-3 flex flex-wrap items-center gap-2 md:hidden" aria-label="已选筛选条件">
        <button v-for="chip in activeChips" :key="chip.key" class="ts-filter-chip flex items-center gap-1.5 border text-xs text-primary-600 dark:text-primary-400" :aria-label="`清除筛选：${chip.label}`" @click="chip.clear()">
          {{ chip.label }}<X class="h-3 w-3" aria-hidden="true" />
        </button>
      </div>
    </div>

    <div class="mt-6 flex items-start gap-6">
      <main class="min-w-0 flex-1">
        <div v-if="loading && !data" class="flex min-h-[320px] items-center justify-center" role="status">
          <LoaderCircle class="h-8 w-8 animate-spin text-primary-500" />
        </div>
        <div v-else-if="error" class="ts-surface flex min-h-[320px] flex-col items-center justify-center rounded-2xl border-dashed px-6 text-center" role="alert">
          <Globe2 class="h-12 w-12 text-primary-400" aria-hidden="true" />
          <h2 class="ts-section-title mt-4 text-gray-900 dark:text-white">暂时无法读取足迹</h2>
          <p class="mt-2 max-w-md text-sm text-gray-500 dark:text-gray-400">{{ error }}</p>
          <button class="ts-button ts-button-primary mt-5" @click="store.load()">重新加载</button>
        </div>
        <div v-else-if="!filteredCities.length" class="ts-surface flex min-h-[320px] flex-col items-center justify-center rounded-2xl border-dashed px-6 text-center">
          <MapPin class="h-12 w-12 text-primary-400" aria-hidden="true" />
          <h2 class="ts-section-title mt-4 text-gray-900 dark:text-white">{{ hasActiveFilters ? '没有匹配的足迹' : '世界很大，留下你的第一枚足迹' }}</h2>
          <p class="mt-2 max-w-md text-sm text-gray-500 dark:text-gray-400">{{ hasActiveFilters ? '换个关键词或放宽筛选条件试试。' : '上传带有 GPS 信息的照片后，去过的城市会出现在这里。' }}</p>
          <button v-if="hasActiveFilters" class="ts-button ts-button-secondary mt-5" @click="resetFilters">重置筛选</button>
          <RouterLink v-else to="/photos" class="ts-button ts-button-primary mt-5">查看照片</RouterLink>
        </div>
        <div v-else class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3" data-testid="footprint-card-grid">
          <FootprintCityCard v-for="city in filteredCities" :key="city.id" :city="city" @open="openCity" />
        </div>
        <p v-if="offline" class="mt-4 text-xs text-gray-500 dark:text-gray-400" role="status">离线快照 · {{ cachedAt ? new Date(cachedAt).toLocaleString() : '' }}</p>
      </main>

      <!-- 桌面：年度概览侧栏 -->
      <aside class="ts-surface sticky top-[calc(var(--ts-header-height)+1rem)] hidden w-72 shrink-0 rounded-2xl p-5 lg:block" aria-label="年度概览">
        <div class="flex items-center justify-between">
          <h2 class="ts-section-title text-gray-900 dark:text-white">年度概览</h2>
          <span class="rounded-full bg-primary-50 px-2.5 py-1 text-xs font-medium text-primary-600 dark:bg-primary-900/40 dark:text-primary-400">{{ year ? `${year} 年` : '全部年份' }}</span>
        </div>
        <dl class="mt-4 space-y-3">
          <div v-for="row in summaryRows" :key="row.label" class="flex items-center justify-between gap-3">
            <dt class="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
              <component :is="row.icon" class="h-4 w-4 text-primary-500" aria-hidden="true" />{{ row.label }}
            </dt>
            <dd class="text-sm font-semibold text-gray-900 dark:text-white">{{ row.value }}</dd>
          </div>
        </dl>
        <div class="mt-5 border-t border-gray-100 pt-4 dark:border-gray-800">
          <h3 class="text-sm font-medium text-gray-900 dark:text-white">足迹趋势</h3>
          <FootprintTrend :items="data?.timeline || []" :year="year" @select="year = $event" />
        </div>
        <div class="mt-4 border-t border-gray-100 pt-4 dark:border-gray-800">
          <h3 class="text-sm font-medium text-gray-900 dark:text-white">热门打卡地</h3>
          <div class="mt-2 space-y-1">
            <button v-for="(city, index) in rankedCities.slice(0, 5)" :key="city.id" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:hover:bg-gray-800/70" :aria-label="`查看${city.name}的足迹详情`" @click="openCity(city)">
              <span class="w-4 shrink-0 text-xs font-semibold" :class="index < 3 ? 'text-primary-500' : 'text-gray-400 dark:text-gray-500'">{{ index + 1 }}</span>
              <span class="min-w-0 flex-1 truncate text-gray-700 dark:text-gray-200">{{ city.name }}</span>
              <small class="shrink-0 text-xs text-gray-400 dark:text-gray-500">{{ format(city.photo_count) }} 张</small>
            </button>
          </div>
        </div>
      </aside>
    </div>

    <!-- 移动端筛选抽屉 -->
    <ResponsiveDialog v-model="filterOpen" title="筛选足迹" description="按年份和地点缩小足迹范围">
      <div class="space-y-5">
        <label class="block">
          <span class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-200">时间范围</span>
          <select v-model="year" class="ts-input w-full" aria-label="按年份筛选" :disabled="loading">
            <option :value="null">全部年份</option>
            <option v-for="value in years" :key="value" :value="value">{{ value }} 年</option>
          </select>
        </label>
        <label class="block">
          <span class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-200">地点</span>
          <select v-model="province" class="ts-input w-full" aria-label="按地点筛选">
            <option :value="null">全部地点</option>
            <option v-for="value in provinces" :key="value" :value="value">{{ value }}</option>
          </select>
        </label>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <button class="ts-button ts-button-secondary flex-1" :disabled="!hasActiveFilters" @click="resetFilters">重置</button>
          <button class="ts-button ts-button-primary flex-1" @click="filterOpen = false">查看 {{ format(filteredCities.length) }} 条足迹</button>
        </div>
      </template>
    </ResponsiveDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { CalendarDays, Footprints, Globe2, Images, LoaderCircle, MapPin, RotateCcw, Search, SlidersHorizontal, X } from 'lucide-vue-next'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import FootprintCityCard from '@/components/footprint/FootprintCityCard.vue'
import FootprintTrend from '@/components/footprint/FootprintTrend.vue'
import { useFootprintStore } from '@/stores/footprintStore'
import type { FootprintCity } from '@/types/footprint'

const store = useFootprintStore()
const router = useRouter()
const { data, year, loading, offline, cachedAt, error } = storeToRefs(store)

const search = ref('')
const province = ref<string | null>(null)
const filterOpen = ref(false)

const years = computed(() => [...(data.value?.years || [])].sort((a, b) => a - b))
const provinces = computed(() => [...new Set((data.value?.cities || []).map(city => city.province).filter((value): value is string => !!value))].sort((a, b) => a.localeCompare(b, 'zh-CN')))
const rankedCities = computed(() => [...(data.value?.cities || [])].sort((a, b) => b.photo_count - a.photo_count))
const filteredCities = computed(() => {
  const keyword = search.value.trim().toLocaleLowerCase()
  return [...(data.value?.cities || [])]
    .filter(city => !province.value || city.province === province.value)
    .filter(city => !keyword || `${city.name} ${city.province || ''} ${city.country || ''}`.toLocaleLowerCase().includes(keyword))
    .sort((a, b) => (b.last_at || '').localeCompare(a.last_at || ''))
})
const hasActiveFilters = computed(() => year.value !== null || province.value !== null || !!search.value.trim())
const activeChips = computed(() => {
  const chips: { key: string; label: string; clear: () => void }[] = []
  if (year.value !== null) chips.push({ key: 'year', label: `${year.value} 年`, clear: () => { year.value = null } })
  if (province.value) chips.push({ key: 'province', label: province.value, clear: () => { province.value = null } })
  return chips
})
const format = (value?: number) => (value || 0).toLocaleString('zh-CN')
const mobileMetrics = computed(() => [
  { icon: Footprints, label: '足迹', value: format(data.value?.summary.city_count) },
  { icon: Images, label: '定位照片', value: format(data.value?.summary.gps_photo_count) },
  { icon: MapPin, label: '省份', value: format(data.value?.summary.province_count) },
])
const summaryRows = computed(() => [
  { icon: Footprints, label: '足迹', value: `${format(data.value?.summary.city_count)} 条` },
  { icon: Images, label: '定位照片', value: `${format(data.value?.summary.gps_photo_count)} 张` },
  { icon: MapPin, label: '省份', value: `${format(data.value?.summary.province_count)} 个` },
  { icon: CalendarDays, label: '到访', value: `${format(data.value?.summary.visit_count)} 次` },
])

function resetFilters() { search.value = ''; province.value = null; year.value = null }
function openCity(city: FootprintCity) { void router.push({ path: '/footprint', query: { city: city.id } }) }

watch(year, () => { void store.load() })
onMounted(() => { void store.load() })
</script>