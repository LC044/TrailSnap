<template>
  <div :class="['location-list flex flex-col relative py-6 px-4', (viewMode === 'map' || viewMode === 'trajectory') ? 'p-0 h-screen' : 'container mx-auto']">
    <!-- Header -->
    <div :class="['container mx-auto flex sm:flex-row justify-between items-start sm:items-center gap-4 flex-shrink-0 z-50 transition-all duration-300', (viewMode === 'map' || viewMode === 'trajectory') ? 'absolute top-0 left-0 right-0 p-4 pointer-events-none' : 'sticky top-0 backdrop-blur-md pb-4 pt-2 -mt-2 mb-2']">
      <div class="flex flex-col gap-3 pointer-events-auto">
        <div class="flex items-center gap-3 w-full md:w-auto dark:bg-gray-900/80 backdrop-blur-md px-3 py-1.5 rounded-full shadow-sm border border-gray-200/50 dark:border-gray-700/50">
          <button @click="router.back()" class="p-0 md:p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors bg-white dark:bg-gray-900">
            <ArrowLeft class="w-5 h-5 text-gray-600 dark:text-gray-300" />
          </button>
          <h1 class="text-xl md:text-2xl font-bold text-gray-800 dark:text-white">位置</h1>
        </div>

        <!-- Stats Block -->
        <div v-if="viewMode === 'map' && statistics" class="self-start dark:bg-gray-900/80 backdrop-blur-md px-4 py-2.5 rounded-xl shadow-sm border border-gray-200/50 dark:border-gray-700/50 transition-all">
           <div class="text-sm font-bold text-gray-800 dark:text-white">
              累计点亮 <span class="text-primary-500 text-base">{{ statistics.province_count }}</span> 省 <span class="text-primary-500 text-base">{{ statistics.city_count }}</span> 市
           </div>
           <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
              已解锁 {{ unlockPercentage }}%
           </div>
        </div>
      </div>

      <div class="pointer-events-auto flex items-center gap-1 md:gap-3">
        <!-- Add Scene Button (Left) -->
        <button
          v-if="level === 'scene'"
          @click="editingScene = null; showAddScene = true"
          class="px-3 py-1.5 rounded-lg bg-primary-500 text-white hover:bg-primary-600 shadow-sm transition-all flex items-center gap-1.5"
          title="新增景区"
        >
          <Plus class="w-4 h-4" />
          <span class="hidden sm:inline">新增景区</span>
        </button>

        <!-- Year Filter -->
        <div class="hidden md:flex bg-gray-200 dark:bg-gray-800 p-0 md:p-1 rounded-lg relative" ref="yearMenuRef">
           <button
             @click="showYearMenu = !showYearMenu"
             class="px-3 py-1.5 rounded-md text-sm font-medium bg-white dark:bg-gray-700 shadow-sm text-gray-900 dark:text-white flex items-center gap-1.5"
           >
             {{ selectedYear ? selectedYear + '年' : (isCustomRange ? '自定义范围' : '全部时间') }}
             <ChevronDown class="w-4 h-4 transition-transform duration-200" :class="{ 'rotate-180': showYearMenu }" />
           </button>

           <div
             v-show="showYearMenu"
             class="absolute top-full right-0 mt-2 w-32 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden z-[60] max-h-60 overflow-y-auto"
           >
             <button
               @click="selectYear(null); showYearMenu = false"
               :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors dark:bg-gray-800', !selectedYear && !isCustomRange ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
             >
               全部时间
             </button>
            <button
               @click="handleCustomRangeClick"
               :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors dark:bg-gray-800 flex items-center justify-between', isCustomRange ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
             >
               自定义范围
             </button>
             <button
               v-for="year in availableYears"
               :key="year"
               @click="selectYear(year); showYearMenu = false"
               :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors dark:bg-gray-800', selectedYear === year ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
             >
               {{ year }}年
             </button>
             <div class="h-px bg-gray-200 dark:bg-gray-700 mx-2 my-1"></div>

           </div>
        </div>

        <!-- Date Range Filter -->
        <div v-if="isCustomRange" class="hidden md:flex bg-white dark:bg-gray-800 rounded-lg relative">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            class="!w-[260px]"
            @change="handleDateRangeChange"
          />
        </div>

        <!-- Filter Toggle (Only for Scene Level) -->
        <div v-if="level === 'scene'" class="bg-gray-200 dark:bg-gray-800 p-1 rounded-lg hidden md:flex">
          <button
            v-for="opt in filterOptions"
            :key="opt.value"
            @click="filterStatus = opt.value as any"
            :class="['px-3 py-1 rounded-md text-xs font-medium transition-all bg-white dark:bg-gray-700 ', filterStatus === opt.value ? 'shadow-sm text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
          >
            {{ opt.label }}
          </button>
        </div>

        <!-- Level Toggle -->
        <div class="bg-gray-200 dark:bg-gray-800 p-0 md:p-1 rounded-lg flex relative" ref="levelMenuRef">
          <!-- Mobile Dropdown Trigger -->
          <button
            @click="showLevelMenu = !showLevelMenu"
            class="md:hidden px-3 py-1.5 rounded-md text-sm font-medium bg-white dark:bg-gray-700 shadow-sm text-gray-900 dark:text-white flex items-center gap-1.5"
          >
            {{ currentLevelLabel }}
            <ChevronDown class="w-4 h-4 transition-transform duration-200" :class="{ 'rotate-180': showLevelMenu }" />
          </button>

          <!-- Mobile Dropdown Menu -->
          <div
            v-show="showLevelMenu"
            class="md:hidden absolute top-full left-0 mt-2 w-40 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden z-[60] flex flex-col max-h-[80vh]"
          >
            <!-- Level Options -->
            <div class="py-1">
              <button
                v-for="opt in levelOptions"
                :key="opt.value"
                @click="changeLevel(opt.value as any); showLevelMenu = false"
                :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors dark:bg-gray-800', level === opt.value ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
              >
                {{ opt.label }}
              </button>
            </div>

            <div class="h-px bg-gray-200 dark:bg-gray-700 mx-2"></div>

            <!-- Year Options -->
            <div class="py-1 max-h-40 overflow-y-auto">
              <button
                @click="selectYear(null); showLevelMenu = false"
                :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors dark:bg-gray-800 flex items-center justify-between', !selectedYear && !isCustomRange ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
              >
                <div class="flex items-center gap-2">
                  <Calendar class="w-3.5 h-3.5 opacity-70" />
                  <span>全部时间</span>
                </div>
                <Check v-if="!selectedYear && !isCustomRange" class="w-3.5 h-3.5" />
              </button>
              <button
                @click="handleCustomRangeClick"
                :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors dark:bg-gray-800 flex items-center justify-between', isCustomRange ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
              >
                <span>自定义范围</span>
                <Check v-if="isCustomRange" class="w-3.5 h-3.5" />
              </button>
              <button
                v-for="year in availableYears"
                :key="year"
                @click="selectYear(year); showLevelMenu = false"
                :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors dark:bg-gray-800 flex items-center justify-between', selectedYear === year ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
              >
                <span>{{ year }}年</span>
                <Check v-if="selectedYear === year" class="w-3.5 h-3.5" />
              </button>
            </div>

            <div class="h-px bg-gray-200 dark:bg-gray-700 mx-2"></div>
            <!-- Mobile Date Range Picker -->
            <div v-if="isCustomRange" class="p-2 flex flex-col items-center gap-2">
              <el-date-picker
                v-model="dateRangeStart"
                type="date"
                placeholder="开始日期"
                value-format="YYYY-MM-DD"
                size="small"
                class="flex-1 !w-full"
              />
              <el-date-picker
                v-model="dateRangeEnd"
                type="date"
                placeholder="结束日期"
                value-format="YYYY-MM-DD"
                size="small"
                class="flex-1 !w-full"
              />
            </div>

            <!-- Mobile Filter Options -->
            <template v-if="level === 'scene'">
              <div class="h-px bg-gray-200 dark:bg-gray-700 mx-2"></div>
              <div class="py-1">
                <button
                  v-for="opt in filterOptions"
                  :key="'m-' + opt.value"
                  @click="filterStatus = opt.value as any; showLevelMenu = false"
                  :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 dark:bg-gray-800 transition-colors', filterStatus === opt.value ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
                >
                  {{ opt.label }}
                </button>
              </div>
            </template>

            <div class="h-px bg-gray-200 dark:bg-gray-700 mx-2"></div>
            
            <button
               v-show="viewMode === 'map'"
               @click="level = 'photo-map'; showLevelMenu = false"
               :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 dark:bg-gray-800 transition-colors flex items-center gap-2', level === 'photo-map' ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
            >
               <Images class="w-4 h-4" />
               地图照片
            </button>
          </div>

          <!-- Desktop Buttons -->
          <div class="hidden md:flex">
            <button
              @click="changeLevel('district')"
              :class="['px-4 py-1.5 rounded-md text-sm transition-all bg-white dark:bg-gray-700', level === 'district' ? ' shadow-sm text-gray-900 dark:text-white font-medium' : 'bg-white/60 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
            >
              区县
            </button>
            <button
              @click="changeLevel('city')"
              :class="['px-4 py-1.5 rounded-md text-sm transition-all bg-white dark:bg-gray-700', level === 'city' ? 'shadow-sm text-gray-900 dark:text-white font-medium' : 'bg-white/60 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
            >
              城市
            </button>
            <button
              @click="changeLevel('province')"
              :class="['px-4 py-1.5 rounded-md text-sm transition-all bg-white dark:bg-gray-700', level === 'province' ? 'shadow-sm text-gray-900 dark:text-white font-medium' : 'bg-white/60 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
            >
              省份
            </button>
            <button
              @click="changeLevel('scene')"
              :class="['px-4 py-1.5 rounded-md text-sm transition-all bg-white dark:bg-gray-700', level === 'scene' ? 'shadow-sm text-gray-900 dark:text-white font-medium' : 'bg-white/60 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
            >
              景区
            </button>
          </div>

          <div v-show="viewMode === 'map'" class="hidden md:block w-px h-4 bg-gray-300 dark:bg-gray-600 mx-1 my-auto"></div>

          <button
            v-show="viewMode === 'map'"
            @click="level = 'photo-map'"
            :class="['hidden md:flex px-3 py-1.5 rounded-md text-sm font-medium transition-all items-center gap-1.5 bg-white dark:bg-gray-700', level === 'photo-map' ? 'bg-white dark:bg-gray-700 shadow-sm text-gray-900 dark:text-white font-medium' : 'bg-white/60 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
            title="地图照片"
          >
            <Images class="w-4 h-4" />
            <span class="hidden sm:inline">照片</span>
          </button>
        </div>
        <!-- View Toggle -->
        <div class="bg-gray-200 dark:bg-gray-800 p-0 md:p-1 rounded-lg flex relative" ref="viewMenuRef">
          <!-- Mobile Dropdown Trigger -->
          <button
            @click="showViewMenu = !showViewMenu"
            class="md:hidden px-3 py-1.5 rounded-md text-sm font-medium bg-white dark:bg-gray-700 shadow-sm text-gray-900 dark:text-white flex items-center gap-1.5"
          >
            <component :is="currentViewIcon" class="w-4 h-4" />
            <ChevronDown class="w-4 h-4 transition-transform duration-200" :class="{ 'rotate-180': showViewMenu }" />
          </button>

          <!-- Mobile Dropdown Menu -->
          <div
            v-show="showViewMenu"
            class="md:hidden absolute top-full right-0 mt-2 w-36 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden z-[60]"
          >
            <button
              @click="viewMode = 'grid'; showViewMenu = false"
              :class="['w-full px-4 py-2 text-left text-sm dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2', viewMode === 'grid' ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
            >
              <LayoutGrid class="w-4 h-4" />
              网格视图
            </button>
            <button
              @click="viewMode = 'map'; showViewMenu = false"
              :class="['w-full px-4 py-2 text-left text-sm dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2', viewMode === 'map' ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
            >
              <Map class="w-4 h-4" />
              地图视图
            </button>
            <button
              @click="viewMode = 'timeline'; showViewMenu = false"
              :class="['w-full px-4 py-2 text-left text-sm dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2', viewMode === 'timeline' ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
            >
              <Clock class="w-4 h-4" />
              时间轴视图
            </button>
            <button
              @click="viewMode = 'trajectory'; showViewMenu = false"
              :class="['w-full px-4 py-2 text-left text-sm dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2', viewMode === 'trajectory' ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
            >
              <Route class="w-4 h-4" />
              轨迹视图
            </button>
          </div>

          <!-- Desktop Buttons -->
          <div class="hidden md:flex">
            <button
              @click="viewMode = 'grid'"
              :class="['p-1.5 rounded-md transition-all bg-white dark:bg-gray-700', viewMode === 'grid' ? 'shadow-sm text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
              title="网格视图"
            >
              <LayoutGrid class="w-4 h-4" />
            </button>
            <button
              @click="viewMode = 'map'"
              :class="['p-1.5 rounded-md transition-all bg-white dark:bg-gray-700', viewMode === 'map' ? 'shadow-sm text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
              title="地图视图"
            >
              <Map class="w-4 h-4" />
            </button>
            <button
              @click="viewMode = 'timeline'"
              :class="['p-1.5 rounded-md transition-all bg-white dark:bg-gray-700', viewMode === 'timeline' ? 'shadow-sm text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
              title="时间轴视图"
            >
              <Clock class="w-4 h-4" />
            </button>
            <button
              @click="viewMode = 'trajectory'"
              :class="['p-1.5 rounded-md transition-all bg-white dark:bg-gray-700', viewMode === 'trajectory' ? 'shadow-sm text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
              title="轨迹视图"
            >
              <Route class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Map View -->
    <LocationMapView
      v-show="viewMode === 'map' && level !== 'photo-map' && level !== 'scene'"
      :level="level"
      :view-mode="viewMode"
      :start-date="dateRange?.[0]"
      :end-date="dateRange?.[1]"
      @click-location="goToLocation"
      @change-level="(level: string, viewState?: { zoom: number; center: number[] }) => changeLevel(level as any, viewState)"
    />

    <!-- Photo Map View -->
    <LocationMap v-if="viewMode === 'map' && (level === 'photo-map' || level === 'scene')" :filter-status="filterStatus" :start-date="dateRange?.[0]" :end-date="dateRange?.[1]" class="flex-1 overflow-hidden shadow-sm" />

    <!-- Timeline View -->
    <LocationTimelineView
      v-if="viewMode === 'timeline'"
      :start-date="dateRange?.[0]"
      :end-date="dateRange?.[1]"
      :level="level"
      @click-photo="handlePhotoClick"
      class="flex-1"
    />

    <!-- Grid View -->
    <LocationListView
      v-show="viewMode === 'grid'"
      :locations="locations"
      :loading="loading"
      :level="level"
      @click="goToLocation"
      @edit="handleEdit"
      @delete="handleDelete"
    />
    <!-- Trajectory View -->
    <LocationTrajectoryView
      v-if="viewMode === 'trajectory'"
      :start-date="dateRange?.[0]"
      :end-date="dateRange?.[1]"
      :level="level"
      :view-mode="viewMode"
      @click-photo="handlePhotoClick"
      class="flex-1"
    />
    <AddSceneDialog v-model="showAddScene" :edit-data="editingScene" @success="fetchLocations" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useLocationStore } from '@/stores/locationStore'
import { locationService } from '@/api/location'
import type { Location, LocationStatistics, Scene } from '@/types/location'
import type { Photo } from '@/types/album'
import { ArrowLeft, LayoutGrid, Map, Images, Plus, ChevronDown, Calendar, Check, Clock, Route } from 'lucide-vue-next'
import { onClickOutside } from '@vueuse/core'
import { ElMessageBox, ElMessage } from 'element-plus'
import LocationMap from './LocationMap.vue'
import AddSceneDialog from './AddSceneDialog.vue'
import LocationListView from './LocationListView.vue'
import LocationMapView from './LocationMapView.vue'
import LocationTimelineView from './LocationTimelineView.vue'
import LocationTrajectoryView from './LocationTrajectoryView.vue'
import PhotoLightbox from '@/components/PhotoLightbox.vue'

const router = useRouter()
const locationStore = useLocationStore()
const { level, viewMode, filterStatus } = storeToRefs(locationStore)
const locationsRaw = ref<Location[]>([])
const statistics = ref<LocationStatistics | null>(null)
const loading = ref(true)
const showAddScene = ref(false)
const editingScene = ref<Scene | null>(null)
const showLevelMenu = ref(false)
const levelMenuRef = ref<HTMLElement | null>(null)
const showViewMenu = ref(false)
const viewMenuRef = ref<HTMLElement | null>(null)
const showYearMenu = ref(false)
const yearMenuRef = ref<HTMLElement | null>(null)
const selectedYear = ref<number | null>(null)
const availableYears = ref<number[]>([])
const dateRange = ref<[string, string] | null>(null)
const isCustomRange = ref(false)

const dateRangeStart = computed({
  get: () => dateRange.value?.[0] || '',
  set: (val) => {
    if (!dateRange.value) {
      dateRange.value = [val || '', '']
    } else {
      dateRange.value[0] = val || ''
    }
    if (!dateRange.value[0] && !dateRange.value[1]) {
      dateRange.value = null
    }
    handleMobileDateChange(val, 'start')
  }
})

const dateRangeEnd = computed({
  get: () => dateRange.value?.[1] || '',
  set: (val) => {
    if (!dateRange.value) {
      dateRange.value = ['', val || '']
    } else {
      dateRange.value[1] = val || ''
    }
    if (!dateRange.value[0] && !dateRange.value[1]) {
      dateRange.value = null
    }
    handleMobileDateChange(val, 'end')
  }
})

const filterOptions = [
  { label: '全部', value: 'all' },
  { label: '已打卡', value: 'checked' },
  { label: '未打卡', value: 'unchecked' }
]

const isMobile = computed(() => {
  return window.innerWidth <= 768
})

const locations = computed(() => {
  if (level.value !== 'scene' || filterStatus.value === 'all') {
    return locationsRaw.value
  }
  return locationsRaw.value.filter(loc => {
    // Both Location and Scene might be in locationsRaw
    const count = (loc as any).count !== undefined ? (loc as any).count : (loc as any).photo_count
    if (filterStatus.value === 'checked') {
      return count > 0
    } else {
      return count === 0
    }
  })
})

onClickOutside(levelMenuRef, () => {
  showLevelMenu.value = false
})

onClickOutside(viewMenuRef, () => {
  showViewMenu.value = false
})

onClickOutside(yearMenuRef, () => {
  showYearMenu.value = false
})

const levelOptions = [
  { label: '区县', value: 'district' },
  { label: '城市', value: 'city' },
  { label: '省份', value: 'province' },
  { label: '景区', value: 'scene' }
]

const currentLevelLabel = computed(() => {
  let label = '区县'
  if (level.value === 'photo-map') {
    label = '照片'
  } else {
    const option = levelOptions.find(opt => opt.value === level.value)
    if (option) label = option.label
  }
  
  if (selectedYear.value) {
    return `${label} · ${selectedYear.value}`
  }
  return label
})

const unlockPercentage = computed(() => {
  if (!statistics.value) return 0
  // 34 provincial administrative divisions in China
  return Math.min(Math.round((statistics.value.province_count / 34) * 100), 100)
})

const currentViewIcon = computed(() => {
  switch (viewMode.value) {
    case 'grid': return LayoutGrid
    case 'map': return Map
    case 'timeline': return Clock
    case 'trajectory': return Route
    default: return LayoutGrid
  }
})

// Fetch data for Grid View
const fetchLocations = async () => {
  loading.value = true
  try {
    // Fetch stats
    statistics.value = await locationService.getStatistics()

    const startDate = dateRange.value?.[0] || undefined
    const endDate = dateRange.value?.[1] || undefined

    if (level.value === 'photo-map') {
      locationsRaw.value = await locationService.getLocations('city', 0, 10000, startDate, endDate)
      return
    }
    
    if (level.value === 'scene' && !startDate && !endDate) {
      const scenes = await locationService.getScenesList(0, 1000)
      // Map Scene to Location-like structure for the grid view
      locationsRaw.value = scenes.map(s => ({
        ...s,
        count: s.photo_count || 0,
        level: 'scene' as const
      })) as any[]
    } else if (level.value === 'scene' && (startDate || endDate)) {
      const scenes = await locationService.getScenesList(0, 1000, startDate, endDate)
      locationsRaw.value = scenes.map(s => ({
        ...s,
        count: s.photo_count || 0,
        level: 'scene' as const
      })) as any[]
    } else {
      locationsRaw.value = await locationService.getLocations(level.value, 0, 10000, startDate, endDate)
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const fetchYears = async () => {
  try {
    availableYears.value = await locationService.getYears()
  } catch (e) {
    console.error(e)
  }
}

const selectYear = (year: number | null) => {
  selectedYear.value = year
  isCustomRange.value = false
  if (year) {
    dateRange.value = [`${year}-01-01`, `${year}-12-31`]
  } else {
    dateRange.value = null
  }
  fetchLocations()
}

const handleCustomRangeClick = () => {
  isCustomRange.value = true
  selectedYear.value = null
  dateRange.value = null
  showYearMenu.value = false
  // We don't fetch locations here immediately since dateRange is empty,
  // user needs to pick a range first. But we could fetch all.
  fetchLocations()
}

const handleMobileDateChange = (val: string | null, type: 'start' | 'end') => {
  if (dateRange.value) {
    const startYear = dateRange.value[0]?.substring(0, 4) || ''
    const endYear = dateRange.value[1]?.substring(0, 4) || ''
    if (dateRange.value[0] === `${startYear}-01-01` && dateRange.value[1] === `${endYear}-12-31` && startYear === endYear && startYear) {
      selectedYear.value = parseInt(startYear)
      isCustomRange.value = false
    } else {
      selectedYear.value = null
      isCustomRange.value = true
    }
  } else {
    selectedYear.value = null
  }
  // Do not close showLevelMenu on mobile to allow selecting the other date
  if (type === 'end') {
    fetchLocations()
  } else {
    showLevelMenu.value = true
  }
}

const handleDateRangeChange = (val: [string, string] | null) => {
    const startYear = val?.[0]?.substring(0, 4) || ''
    const endYear = val?.[1]?.substring(0, 4) || ''
    if (dateRange.value) {
      if (val?.[0] === `${startYear}-01-01` && val?.[1] === `${endYear}-12-31` && startYear === endYear && startYear) {
        selectedYear.value = parseInt(startYear)
        isCustomRange.value = false
      } else {
        selectedYear.value = null
        isCustomRange.value = true
      }
  } else {
    selectedYear.value = null
    // keep isCustomRange state
  }
  showLevelMenu.value = false
  fetchLocations()
}

const changeLevel = (newLevel: 'city' | 'province' | 'district' | 'scene', viewState?: { zoom: number, center: number[] }) => {
  if (level.value === newLevel) return
  level.value = newLevel
  fetchLocations()
  // Map initialization is handled by LocationMapView watcher on 'level'
}

const goToLocation = (name: string) => {
  const query: any = { level: level.value }
  if (dateRange.value) {
    query.startDate = dateRange.value[0]
    query.endDate = dateRange.value[1]
  }
  router.push({
    name: 'LocationDetail',
    params: { name: name },
    query
  })
}

const handleEdit = async (loc: Location) => {
  if (!loc.id) return
  try {
    const scene = await locationService.getScene(loc.id)
    editingScene.value = scene
    showAddScene.value = true
  } catch (e) {
    console.error(e)
  }
}

const handlePhotoClick = (photo: Photo, contextPhotos: Photo[]) => {
  lightboxPhotos.value = contextPhotos
  lightboxImage.value = photo
  document.body.style.overflow = 'hidden'
}

const lightboxImage = ref<Photo | null>(null)
const lightboxPhotos = ref<Photo[]>([])


const handleDelete = async (loc: Location) => {
  if (!loc.id) return
  
  try {
    await ElMessageBox.confirm(
      `确定要删除景区 "${loc.name}" 吗？此操作不可撤销。`,
      '确认删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )
    
    loading.value = true
    await locationService.deleteScene(loc.id)
    ElMessage.success('删除成功')
    await fetchLocations()
  } catch (e: any) {
    if (e !== 'cancel') {
      console.error(e)
      ElMessage.error(e.response?.data?.detail || '删除失败')
    }
  } finally {
    loading.value = false
  }
}

// Watchers
watch(viewMode, (newMode) => {
  // Map initialization handled in LocationMapView
  if (newMode !== 'map' && level.value === 'photo-map') {
    level.value = 'city'
  }
})

onMounted(() => {
  fetchYears()
  fetchLocations()
})
</script>

<style scoped>
/* Optional transitions */
</style>
