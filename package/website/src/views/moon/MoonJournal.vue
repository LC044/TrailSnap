<template>
  <div class="moon-journal min-h-screen bg-gray-50 text-gray-900 dark:bg-gray-900 dark:text-gray-100" data-testid="moon-journal">
    <div class="mx-auto max-w-[1600px] px-3 py-3 sm:px-5 md:px-8 md:py-6">
      <header class="relative isolate min-h-[168px] overflow-hidden rounded-3xl bg-gray-950 text-white shadow-lg md:min-h-[190px]">
        <img
          v-if="heroPhoto"
          :src="heroPhoto.preview || heroPhoto.thumbnail"
          alt=""
          class="absolute inset-0 -z-20 h-full w-full object-cover object-center opacity-30"
        />
        <div class="absolute inset-0 -z-10 bg-gradient-to-br from-gray-950/95 via-gray-950/75 to-gray-800/40"></div>
        <div class="absolute -right-20 -top-24 -z-10 h-72 w-72 rounded-full bg-primary-500/20 blur-3xl"></div>

        <div class="flex h-full min-h-[168px] flex-col justify-between p-4 sm:p-5 md:min-h-[190px] md:p-6">
          <div class="flex items-start justify-between gap-3">
            <div class="flex min-w-0 items-center gap-3">
              <button
                type="button"
                class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/10 text-white backdrop-blur transition hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950"
                aria-label="返回"
                @click="router.back()"
              >
                <ArrowLeft class="h-5 w-5" />
              </button>
              <div class="min-w-0">
                <h1 class="text-xl font-bold tracking-wide sm:text-2xl">月迹</h1>
                <p class="mt-0.5 truncate text-xs text-gray-300 dark:text-gray-300 sm:text-sm">记录每一次阴晴圆缺</p>
              </div>
            </div>
            <div class="hidden rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm text-gray-200 backdrop-blur md:block">
              {{ yearRange }}
            </div>
          </div>

          <div class="flex items-end justify-between gap-3">
            <div class="flex flex-wrap items-center gap-x-4 gap-y-1.5">
              <p class="text-2xl font-bold tabular-nums sm:text-3xl">{{ photos.length }} <span class="text-base font-medium text-gray-300 dark:text-gray-300">次记录</span></p>
              <span class="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs text-gray-200 backdrop-blur">覆盖 {{ coveredPhaseCount }} / 8 种月相</span>
            </div>
            <div v-if="latestObservation" class="flex items-center gap-2.5 rounded-2xl border border-white/10 bg-black/20 px-3 py-2 backdrop-blur sm:px-4">
              <MoonPhaseIcon :phase="latestObservation.phase" class="h-9 w-9 shrink-0" />
              <div class="hidden sm:block">
                <p class="text-sm font-semibold">最近记录 · {{ latestObservation.label }}</p>
                <p class="text-xs text-gray-300 dark:text-gray-300">{{ formatDate(latestObservation.takenAt) }}</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      <nav class="sticky top-2 z-40 mx-auto mt-4 flex w-fit rounded-full border border-gray-200/70 bg-white/90 p-1 shadow-sm backdrop-blur dark:border-gray-700/70 dark:bg-gray-900/90" aria-label="月迹视图">
        <button
          v-for="tab in viewTabs"
          :key="tab.value"
          type="button"
          class="min-w-[76px] rounded-full px-4 py-2 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 sm:min-w-[92px]"
          :class="selectedView === tab.value ? 'bg-primary-600 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800'"
          :aria-current="selectedView === tab.value ? 'page' : undefined"
          @click="selectedView = tab.value"
        >
          {{ tab.label }}
        </button>
      </nav>

      <div v-if="loading" class="grid grid-cols-2 gap-3 py-10 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-6">
        <div v-for="index in 12" :key="index" class="aspect-square animate-pulse rounded-2xl bg-gray-200 dark:bg-gray-800"></div>
      </div>

      <div v-else-if="error" class="my-10 rounded-2xl border border-red-200 bg-red-50 p-8 text-center dark:border-red-900/50 dark:bg-red-950/30">
        <p class="font-medium text-red-700 dark:text-red-300">{{ error }}</p>
        <button type="button" class="mt-4 rounded-full bg-primary-600 px-5 py-2 text-sm text-white hover:bg-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="loadPhotos">
          重新加载
        </button>
      </div>

      <div v-else-if="photos.length === 0" class="flex min-h-[45vh] flex-col items-center justify-center py-16 text-center">
        <div class="h-24 w-24 rounded-full bg-gray-900 p-3 shadow-xl dark:bg-gray-950">
          <MoonPhaseIcon phase="waxing_crescent" />
        </div>
        <h2 class="mt-6 text-xl font-semibold">还没有月亮记录</h2>
        <p class="mt-2 max-w-sm text-sm text-gray-500 dark:text-gray-400">完成图片分类后，被识别为“月亮”的照片会自动出现在这里。</p>
      </div>

      <template v-else>
        <main v-if="selectedView === 'phase'" class="py-8 md:py-10">
          <section aria-labelledby="phase-filter-title">
            <div class="mb-5 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <h2 id="phase-filter-title" class="text-xl font-bold md:text-2xl">月相记录</h2>
                <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">从初一渐盈，到满月，再渐亏为残月</p>
              </div>
              <div class="flex w-full rounded-xl bg-gray-100 p-1 dark:bg-gray-800 md:w-auto" aria-label="月相阶段筛选">
                <button
                  v-for="group in groupFilters"
                  :key="group.value"
                  type="button"
                  class="flex-1 whitespace-nowrap rounded-lg px-3 py-2 text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 md:flex-none"
                  :class="selectedGroup === group.value && !selectedPhase ? 'bg-white font-medium text-primary-600 shadow-sm dark:bg-gray-700 dark:text-primary-400' : 'text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white'"
                  @click="selectGroup(group.value)"
                >
                  {{ group.label }}
                </button>
              </div>
            </div>

            <div class="moon-phase-scroller -mx-3 flex snap-x snap-mandatory gap-2 overflow-x-auto px-3 pb-3 sm:mx-0 sm:grid sm:grid-cols-4 sm:overflow-visible sm:px-0 md:grid-cols-8 md:gap-3">
              <button
                v-for="option in phaseOptions"
                :key="option.phase"
                type="button"
                class="group min-w-[94px] snap-start rounded-2xl border bg-white p-3 text-center shadow-sm transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:bg-gray-800 sm:min-w-0"
                :class="selectedPhase === option.phase ? 'border-primary-500 ring-1 ring-primary-500' : 'border-gray-200 dark:border-gray-700'"
                :aria-pressed="selectedPhase === option.phase"
                @click="selectPhase(option.phase)"
              >
                <span class="mx-auto block h-11 w-11 rounded-full bg-gray-950 p-0.5 shadow-inner sm:h-12 sm:w-12">
                  <MoonPhaseIcon :phase="option.phase" class="h-full w-full" />
                </span>
                <span class="mt-2 block text-sm font-semibold text-gray-900 dark:text-gray-100">{{ option.label }}</span>
                <span class="mt-0.5 block text-xs text-gray-500 dark:text-gray-400">{{ phaseCounts[option.phase] }} 张</span>
              </button>
            </div>
          </section>

          <section class="mt-7" aria-live="polite">
            <div class="mb-4 flex items-center justify-between gap-3">
              <div>
                <h3 class="text-lg font-semibold">{{ activeFilterLabel }}</h3>
                <p class="text-xs text-gray-500 dark:text-gray-400">{{ filteredObservations.length }} 张照片</p>
              </div>
              <button
                v-if="selectedPhase || selectedGroup !== 'all'"
                type="button"
                class="rounded-full px-3 py-1.5 text-sm text-primary-600 hover:bg-primary-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:text-primary-400 dark:hover:bg-primary-900/30"
                @click="clearFilters"
              >
                查看全部
              </button>
            </div>

            <div v-if="filteredObservations.length" class="grid grid-cols-2 gap-2.5 sm:grid-cols-3 sm:gap-4 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
              <button
                v-for="observation in filteredObservations"
                :key="observation.photo.id"
                type="button"
                class="group relative aspect-square overflow-hidden rounded-2xl bg-gray-200 text-left shadow-sm transition hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:bg-gray-800"
                data-testid="moon-photo-card"
                @click="openLightbox(observation.photo, filteredObservations.map((item) => item.photo))"
              >
                <img :src="observation.photo.thumbnail" :alt="observation.photo.filename || `${observation.label}照片`" class="h-full w-full object-cover transition duration-500 group-hover:scale-105" loading="lazy" />
                <span class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/55 to-transparent px-3 pb-2.5 pt-9 text-white">
                  <span class="flex items-center gap-1.5 text-sm font-semibold">
                    <MoonPhaseIcon :phase="observation.phase" class="h-5 w-5 shrink-0" />
                    {{ observation.label }} · {{ observation.lunarDate }}
                  </span>
                  <span class="mt-0.5 block text-xs text-gray-300 dark:text-gray-300">{{ formatDate(observation.takenAt) }} · 亮面 {{ formatIllumination(observation.illumination) }}</span>
                </span>
              </button>
            </div>
            <div v-else class="rounded-2xl border border-dashed border-gray-300 bg-white py-14 text-center dark:border-gray-700 dark:bg-gray-800">
              <MoonPhaseIcon :phase="emptyPhase" class="mx-auto h-16 w-16 rounded-full bg-gray-950 p-1" />
              <p class="mt-4 font-medium">还没有记录过{{ activeFilterLabel }}</p>
              <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">下一次拍到时，这里就会被点亮。</p>
            </div>
          </section>

          <section v-if="unknownTimePhotos.length" class="mt-8 rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
            <p class="font-medium">{{ unknownTimePhotos.length }} 张照片缺少可靠拍摄时间</p>
            <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">这些照片仍会出现在“全部”视图，但无法计算月相。</p>
          </section>
        </main>

        <main v-else-if="selectedView === 'calendar'" class="py-8 md:py-10">
          <section class="rounded-3xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800 sm:p-6">
            <div class="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h2 class="text-xl font-bold md:text-2xl">农历日记录</h2>
                <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">选择一个农历日，查看历次在这一天拍摄的月亮</p>
              </div>
              <div class="w-fit rounded-full bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-600 dark:bg-gray-900 dark:text-gray-300">
                已记录 {{ recordedLunarDayCount }} / 30 天
              </div>
            </div>

            <div class="space-y-5">
              <div v-for="lane in lunarDayLanes" :key="lane.label" class="xl:flex xl:items-center xl:gap-4">
                <div class="mb-2 flex items-center gap-2 xl:mb-0 xl:w-12 xl:shrink-0 xl:flex-col xl:gap-0.5">
                  <span class="text-sm font-semibold text-gray-700 dark:text-gray-200">{{ lane.label }}</span>
                  <span class="text-xs text-gray-400 dark:text-gray-500">{{ lane.range }}</span>
                </div>
                <div class="grid flex-1 grid-cols-5 gap-1.5 sm:gap-2 xl:grid-cols-[repeat(15,minmax(0,1fr))]">
                <button
                  v-for="day in lane.days"
                  :key="day.day"
                  data-testid="lunar-day"
                  type="button"
                  class="relative flex aspect-square min-w-0 flex-col items-center justify-center rounded-xl border px-1 py-1.5 transition hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
                  :class="selectedLunarDay === day.day ? 'border-primary-500 bg-primary-50 text-primary-700 shadow-md ring-2 ring-primary-500 dark:bg-primary-900/30 dark:text-primary-300' : 'border-gray-200 bg-gray-50 text-gray-800 hover:border-primary-500/50 hover:bg-white dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:hover:bg-gray-800'"
                  :aria-label="`农历${day.label}，${day.photos.length} 张月亮照片`"
                  @click="selectedLunarDay = day.day"
                >
                  <MoonPhaseIcon :phase="day.phase" class="h-6 w-6 rounded-full bg-gray-950 sm:h-7 sm:w-7" />
                  <span class="mt-1 text-[10px] font-semibold sm:text-xs">{{ day.label }}</span>
                  <span class="mt-0.5 text-[9px] tabular-nums" :class="day.photos.length ? 'text-primary-600 dark:text-primary-400' : 'text-gray-400 dark:text-gray-500'">
                    {{ day.photos.length ? `${day.photos.length} 次` : '—' }}
                  </span>
                </button>
              </div>
              </div>
            </div>
          </section>

          <section class="mt-6 rounded-3xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800 sm:p-6">
            <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div class="flex items-center gap-3">
                <MoonPhaseIcon :phase="selectedLunarDayPhase" class="h-12 w-12 shrink-0 rounded-full bg-gray-950 p-1 sm:h-14 sm:w-14" />
                <div>
                  <h3 class="text-xl font-bold sm:text-2xl">农历{{ selectedLunarDayLabel }} · {{ selectedLunarDayPhaseLabel }}</h3>
                  <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">历次在农历{{ selectedLunarDayLabel }}拍摄的月亮</p>
                </div>
              </div>
              <div class="flex gap-2 text-sm">
                <span class="rounded-full bg-gray-100 px-3 py-1.5 text-gray-600 dark:bg-gray-900 dark:text-gray-300">{{ selectedLunarDayPhotos.length }} 次记录</span>
                <span class="rounded-full bg-gray-100 px-3 py-1.5 text-gray-600 dark:bg-gray-900 dark:text-gray-300">跨越 {{ selectedLunarDayYearCount }} 年</span>
              </div>
            </div>
            <div v-if="selectedLunarDayObservations.length" class="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-3 sm:gap-4 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
                <button v-for="observation in selectedLunarDayObservations" :key="observation.photo.id" type="button" class="group relative aspect-square overflow-hidden rounded-2xl bg-gray-200 shadow-sm transition hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:bg-gray-700" @click="openLightbox(observation.photo, selectedLunarDayPhotos)">
                  <img :src="observation.photo.thumbnail" :alt="observation.photo.filename || '月亮照片'" class="h-full w-full object-cover transition duration-500 group-hover:scale-105" />
                  <span class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-3 pb-2 pt-8 text-xs text-white">{{ formatDate(observation.takenAt) }}</span>
                </button>
            </div>
            <div v-else class="mt-5 flex flex-col items-center rounded-2xl border border-dashed border-gray-300 bg-gray-50 px-4 py-10 text-center dark:border-gray-600 dark:bg-gray-900">
              <span class="flex h-12 w-12 items-center justify-center rounded-full bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400">
                <CalendarDays class="h-6 w-6" />
              </span>
              <p class="mt-3 font-medium text-gray-800 dark:text-gray-100">农历{{ selectedLunarDayLabel }}还没有月亮记录</p>
              <template v-if="nextCaptureDate">
                <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">下一次补拍机会</p>
                <p class="mt-1 text-base font-semibold text-primary-600 dark:text-primary-400">{{ nextCaptureDateLabel }}</p>
                <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">拍摄后会根据照片时间自动归入农历{{ selectedLunarDayLabel }}</p>
              </template>
            </div>
          </section>
        </main>

        <section v-else class="-mx-3 pb-6 pt-4 sm:-mx-5 md:-mx-8">
          <UnifiedPhotoPage
            :photos="photos"
            :loading="false"
            :has-more="false"
            :timeline-items="timeline"
            :timeline-stats="{ timeline }"
            :show-back="false"
            @confirm-delete="handleConfirmDelete"
          >
            <template #header-left><span aria-hidden="true"></span></template>
            <template #batch-actions="{ selectedIds, clearSelection }">
              <el-dropdown-item @click="removeFromMoonTag(Array.from(selectedIds)); clearSelection()">
                <div class="flex items-center gap-2"><ImageMinus class="h-4 w-4" /><span>从月亮分类中移除</span></div>
              </el-dropdown-item>
            </template>
          </UnifiedPhotoPage>
        </section>
      </template>
    </div>

    <PhotoLightbox
      :visible="!!lightboxPhoto"
      :image="lightboxPhoto"
      :has-prev="lightboxIndex > 0"
      :has-next="lightboxIndex >= 0 && lightboxIndex < lightboxPhotos.length - 1"
      @close="closeLightbox"
      @prev="moveLightbox(-1)"
      @next="moveLightbox(1)"
      @delete="handleLightboxDelete"
    >
      <template #context-overlay>
        <div v-if="lightboxObservation" class="pointer-events-none fixed inset-x-0 bottom-5 z-[103] flex justify-center px-4 md:bottom-8">
          <div class="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/65 px-4 py-2.5 text-white shadow-xl backdrop-blur-md">
            <MoonPhaseIcon :phase="lightboxObservation.phase" class="h-9 w-9 shrink-0" />
            <div>
              <p class="text-sm font-semibold">{{ lightboxObservation.label }} · {{ lightboxObservation.lunarDate }}</p>
              <p class="text-xs text-gray-300 dark:text-gray-300">月龄 {{ lightboxObservation.moonAge.toFixed(1) }} 天 · 亮面 {{ formatIllumination(lightboxObservation.illumination) }}</p>
            </div>
          </div>
        </div>
      </template>
    </PhotoLightbox>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, CalendarDays, ImageMinus } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'

import { classificationService } from '@/api/classification'
import MoonPhaseIcon from '@/components/moon/MoonPhaseIcon.vue'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import UnifiedPhotoPage from '@/components/UnifiedPhotoPage.vue'
import { createMoonObservation, findNextChineseLunarDay, formatChineseLunarDay, formatIllumination, getMoonPhaseForLunarDay, MOON_PHASES } from '@/composables/useMoonPhase'
import { mapPhotoToImage, usePhotoStore } from '@/stores/photoStore'
import type { AlbumImage } from '@/types/album'
import type { MoonObservation, MoonPhase, MoonPhaseGroup, MoonView } from '@/types/moon'

const MOON_TAG_NAME = '月亮'
const route = useRoute()
const router = useRouter()
const photoStore = usePhotoStore()

const viewTabs: Array<{ value: MoonView; label: string }> = [
  { value: 'phase', label: '月相' },
  { value: 'calendar', label: '农历日' },
  { value: 'all', label: '全部' },
]
const groupFilters: Array<{ value: 'all' | MoonPhaseGroup; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'waxing', label: '渐盈' },
  { value: 'full', label: '满月' },
  { value: 'waning', label: '渐亏' },
]
const phaseOptions = MOON_PHASES

const loading = ref(true)
const error = ref('')
const photos = ref<AlbumImage[]>([])
const selectedView = ref<MoonView>(['phase', 'calendar', 'all'].includes(String(route.query.view)) ? route.query.view as MoonView : 'phase')
const selectedGroup = ref<'all' | MoonPhaseGroup>('all')
const selectedPhase = ref<MoonPhase | null>(null)
const lightboxPhotos = ref<AlbumImage[]>([])
const lightboxIndex = ref(-1)

const queryLunarDay = Number.parseInt(String(route.query.day ?? ''), 10)
const selectedLunarDay = ref(queryLunarDay >= 1 && queryLunarDay <= 30 ? queryLunarDay : 15)

const initialPhaseFilter = typeof route.query.phase === 'string' ? route.query.phase : ''
if (MOON_PHASES.some((item) => item.phase === initialPhaseFilter)) {
  selectedPhase.value = initialPhaseFilter as MoonPhase
  selectedGroup.value = MOON_PHASES.find((item) => item.phase === initialPhaseFilter)!.group
} else if (['waxing', 'full', 'waning'].includes(initialPhaseFilter)) {
  selectedGroup.value = initialPhaseFilter as MoonPhaseGroup
}

const observations = computed(() => photos.value
  .map(createMoonObservation)
  .filter((item): item is MoonObservation => item !== null)
  .sort((a, b) => b.takenAt.getTime() - a.takenAt.getTime()))
const unknownTimePhotos = computed(() => photos.value.filter((photo) => !photo.hasPhotoTime))
const latestObservation = computed(() => observations.value[0] ?? null)
const heroPhoto = computed(() => latestObservation.value?.photo ?? photos.value[0] ?? null)
const coveredPhaseCount = computed(() => new Set(observations.value.map((item) => item.phase)).size)
const yearRange = computed(() => {
  if (!observations.value.length) return '暂无拍摄时间'
  const years = observations.value.map((item) => item.takenAt.getFullYear())
  const min = Math.min(...years)
  const max = Math.max(...years)
  return min === max ? `${min} 年` : `${min} — ${max}`
})
const phaseCounts = computed<Record<MoonPhase, number>>(() => {
  const counts = Object.fromEntries(MOON_PHASES.map((item) => [item.phase, 0])) as Record<MoonPhase, number>
  observations.value.forEach((item) => { counts[item.phase] += 1 })
  return counts
})
const filteredObservations = computed(() => observations.value.filter((item) => {
  if (selectedPhase.value) return item.phase === selectedPhase.value
  if (selectedGroup.value !== 'all') return item.group === selectedGroup.value
  return true
}))
const activeFilterLabel = computed(() => {
  if (selectedPhase.value) return MOON_PHASES.find((item) => item.phase === selectedPhase.value)?.label ?? '月相'
  return groupFilters.find((item) => item.value === selectedGroup.value)?.label ?? '全部月相'
})
const emptyPhase = computed<MoonPhase>(() => selectedPhase.value ?? (selectedGroup.value === 'waning' ? 'waning_crescent' : selectedGroup.value === 'full' ? 'full_moon' : 'waxing_crescent'))
const timeline = computed(() => {
  const stats = new Map<string, { year: number; month: number; day: number; count: number }>()
  photos.value.forEach((photo) => {
    const date = new Date(photo.timestamp)
    const key = toDateKey(date)
    const current = stats.get(key)
    if (current) current.count += 1
    else stats.set(key, { year: date.getFullYear(), month: date.getMonth() + 1, day: date.getDate(), count: 1 })
  })
  return Array.from(stats.values()).sort((a, b) => new Date(b.year, b.month - 1, b.day).getTime() - new Date(a.year, a.month - 1, a.day).getTime())
})

const observationsByLunarDay = computed(() => {
  const map = new Map<number, MoonObservation[]>()
  observations.value.forEach((item) => {
    map.set(item.lunarDay, [...(map.get(item.lunarDay) ?? []), item])
  })
  return map
})
const lunarDayCells = computed(() => Array.from({ length: 30 }, (_, index) => {
  const day = index + 1
  const dayObservations = observationsByLunarDay.value.get(day) ?? []
  return {
    day,
    label: formatChineseLunarDay(day),
    phase: getMoonPhaseForLunarDay(day),
    photos: dayObservations.map((item) => item.photo),
  }
}))
const lunarDayLanes = computed(() => [
  { label: '渐盈', range: '初一—十五', days: lunarDayCells.value.slice(0, 15) },
  { label: '渐亏', range: '十六—三十', days: lunarDayCells.value.slice(15) },
])
const recordedLunarDayCount = computed(() => lunarDayCells.value.filter((item) => item.photos.length > 0).length)
const selectedLunarDayObservations = computed(() => observationsByLunarDay.value.get(selectedLunarDay.value) ?? [])
const selectedLunarDayPhotos = computed(() => selectedLunarDayObservations.value.map((item) => item.photo))
const selectedLunarDayLabel = computed(() => formatChineseLunarDay(selectedLunarDay.value))
const selectedLunarDayPhase = computed(() => getMoonPhaseForLunarDay(selectedLunarDay.value))
const selectedLunarDayPhaseLabel = computed(() => MOON_PHASES.find((item) => item.phase === selectedLunarDayPhase.value)?.label ?? '月相')
const selectedLunarDayYearCount = computed(() => new Set(selectedLunarDayObservations.value.map((item) => item.takenAt.getFullYear())).size)
const nextCaptureDate = computed(() => findNextChineseLunarDay(selectedLunarDay.value))
const nextCaptureDateLabel = computed(() => nextCaptureDate.value
  ? new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }).format(nextCaptureDate.value)
  : '')
const lightboxPhoto = computed(() => lightboxIndex.value >= 0 ? lightboxPhotos.value[lightboxIndex.value] ?? null : null)
const lightboxObservation = computed(() => lightboxPhoto.value ? createMoonObservation(lightboxPhoto.value) : null)

function toDateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

const formatDate = (date: Date) => new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)

const loadPhotos = async () => {
  loading.value = true
  error.value = ''
  try {
    const result: AlbumImage[] = []
    const limit = 500
    let skip = 0
    while (true) {
      const page = await classificationService.getTagPhotos(MOON_TAG_NAME, skip, limit)
      result.push(...page.map(mapPhotoToImage))
      if (page.length < limit) break
      skip += limit
    }
    photos.value = result.sort((a, b) => b.timestamp - a.timestamp)
    if (!route.query.day && observations.value[0]) {
      selectedLunarDay.value = observations.value[0].lunarDay
    }
  } catch (cause) {
    console.error('Failed to load moon photos:', cause)
    error.value = '月亮照片加载失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

const selectGroup = (group: 'all' | MoonPhaseGroup) => {
  selectedGroup.value = group
  selectedPhase.value = null
}

const selectPhase = (phase: MoonPhase) => {
  if (selectedPhase.value === phase) {
    selectedPhase.value = null
    selectedGroup.value = 'all'
    return
  }
  selectedPhase.value = phase
  selectedGroup.value = MOON_PHASES.find((item) => item.phase === phase)!.group
}

const clearFilters = () => {
  selectedGroup.value = 'all'
  selectedPhase.value = null
}

const openLightbox = (photo: AlbumImage, context: AlbumImage[]) => {
  lightboxPhotos.value = context
  lightboxIndex.value = context.findIndex((item) => item.id === photo.id)
}

const closeLightbox = () => { lightboxIndex.value = -1 }
const moveLightbox = (offset: number) => {
  const next = lightboxIndex.value + offset
  if (next >= 0 && next < lightboxPhotos.value.length) lightboxIndex.value = next
}

const removeLocalPhotos = (ids: string[]) => {
  photos.value = photos.value.filter((photo) => !ids.includes(photo.id))
  lightboxPhotos.value = lightboxPhotos.value.filter((photo) => !ids.includes(photo.id))
}

const handleConfirmDelete = async (ids: string[], callback: (success: boolean) => void) => {
  try {
    await photoStore.deletePhotos(ids)
    removeLocalPhotos(ids)
    ElMessage.success('删除成功')
    callback(true)
  } catch {
    ElMessage.error('删除失败')
    callback(false)
  }
}

const handleLightboxDelete = async (id: string) => {
  try {
    await photoStore.deletePhotos([id])
    removeLocalPhotos([id])
    closeLightbox()
    ElMessage.success('删除成功')
  } catch {
    ElMessage.error('删除失败')
  }
}

const removeFromMoonTag = async (ids: string[]) => {
  try {
    await classificationService.removePhotosFromTag(MOON_TAG_NAME, ids)
    removeLocalPhotos(ids)
    ElMessage.success('已从月亮分类中移除')
  } catch {
    ElMessage.error('移除失败')
  }
}

watch([selectedView, selectedGroup, selectedPhase, selectedLunarDay], () => {
  const phase = selectedPhase.value ?? (selectedGroup.value === 'all' ? undefined : selectedGroup.value)
  router.replace({
    query: {
      ...route.query,
      view: selectedView.value === 'phase' ? undefined : selectedView.value,
      phase,
      month: undefined,
      date: undefined,
      day: selectedView.value === 'calendar' ? selectedLunarDay.value : undefined,
    },
  })
})

onMounted(loadPhotos)
</script>

<style scoped>
.moon-phase-scroller {
  scrollbar-width: none;
}

.moon-phase-scroller::-webkit-scrollbar {
  display: none;
}
</style>
