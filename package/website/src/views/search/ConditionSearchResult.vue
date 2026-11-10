<template>
  <UnifiedPhotoPage
    :key="searchKey"
    :title="query"
    :subtitle="subtitle"
    stable-title
    enable-time-browse
    :loading="store.loading"
    :error="dateError || store.error"
    :photos="store.images"
    :timeline-items="store.timelineStats?.timeline || []"
    :timeline-stats="store.timelineStats"
    :has-more="store.hasMore"
    :store="store"
    confirm-remove
    @back="goBack"
    @clear-filters="clearSearch"
    @retry="reload"
    @load-more="store.loadPhotos"
    @confirm-delete="deletePhotos"
    @photo-update="refresh"
    @refresh-data="refresh"
  >
    <template #header-controls-start>
      <button type="button" class="ts-glass-button" aria-label="添加筛选" title="添加筛选" @click="showFilters = true">
        <Filter class="h-5 w-5" />
      </button>
    </template>
    <template #header-extension>
      <div class="flex min-w-0 flex-wrap items-center gap-2 pb-3">
        <button type="button" class="ts-button ts-button-ghost max-w-full text-primary-600 dark:text-primary-400" :aria-label="`移除${typeLabel}条件：${query}`" @click="clearSearch">
          <span class="truncate">{{ typeLabel }}：{{ query }}</span><X class="h-4 w-4 shrink-0" />
        </button>
        <button v-for="chip in extraFilters" :key="chip.key + chip.value" type="button" class="ts-button ts-button-ghost max-w-full" :aria-label="`移除筛选：${chip.label}`" @click="removeFilter(chip.key, chip.value)">
          <span class="truncate">{{ chip.label }}</span><X class="h-4 w-4 shrink-0" />
        </button>
        <button type="button" class="ts-button ts-button-ghost ts-muted" @click="showFilters = true">添加筛选</button>
      </div>
    </template>
    <template #empty>
      <div class="py-20 text-center ts-muted">
        <p>没有符合条件的照片</p>
        <button v-if="extraFilters.length" type="button" class="ts-button ts-button-primary mt-4" @click="clearExtraFilters">清除附加筛选</button>
        <button v-else type="button" class="ts-button ts-button-primary mt-4" @click="clearSearch">重新搜索</button>
      </div>
    </template>
    <template #extra-modals>
      <ResponsiveDialog v-model="showFilters" title="筛选搜索结果" glass>
        <FilterPanel :store="store" />
      </ResponsiveDialog>
    </template>
  </UnifiedPhotoPage>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Filter, X } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import UnifiedPhotoPage from '@/components/UnifiedPhotoPage.vue'
import FilterPanel from '@/components/FilterPanel.vue'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import { useSearchPhotosStore } from '@/stores/photoStore'
import { useAppBack } from '@/composables/useAppBack'
import { parseDateRange } from '@/utils/date'
import { conditionSearchLabels, formatConditionFilter } from '@/utils/conditionSearch'
import type { FilterState } from '@/types/album'

const route = useRoute()
const router = useRouter()
const goBack = useAppBack('/photos')
const store = useSearchPhotosStore()
const query = computed(() => String(route.query.q || ''))
const type = computed(() => String(route.query.type || ''))
const typeLabel = computed(() => conditionSearchLabels[type.value])
const searchKey = computed(() => JSON.stringify([type.value, query.value]))
const showFilters = ref(false)
const dateError = ref('')
const extraFilters = computed(() => Object.entries(store.selectedFilters).flatMap(([key, values]) =>
  (Array.isArray(values) ? values : []).map((value: string | number) => ({ key: key as keyof FilterState, value, label: formatConditionFilter(key,
    key === 'people' ? store.availableFilters?.person_options?.find(person => person.id === value)?.name || value : value) }))))
const subtitle = computed(() => {
  if (store.loading && !store.timelineStats?.total_photos) return '搜索中…'
  const stats = store.timelineStats
  if (!stats) return ''
  const range = stats.time_range
  const startYear = range?.start?.slice(0, 4)
  const endYear = range?.end?.slice(0, 4)
  const years = startYear && endYear ? `${startYear === endYear ? startYear : `${startYear}—${endYear}`} 年` : ''
  return [`共 ${stats.total_photos} 张照片`, years].filter(Boolean).join(' · ')
})
const clearSearch = () => router.push('/mobile-search')
const clearExtraFilters = () => {
  Object.values(store.selectedFilters).forEach(values => { if (Array.isArray(values)) values.splice(0) })
  void reload()
}
const removeFilter = (key: keyof FilterState, value: string | number) => {
  const values = store.selectedFilters[key] as (string | number)[]
  values.splice(values.indexOf(value), 1)
  void reload()
}
const reload = async () => {
  if (!dateError.value) await store.loadPhotos(true)
}
const refresh = async (done?: unknown) => {
  let success = false
  try { await store.refreshCurrentContext(); success = !store.error }
  catch { ElMessage.error('刷新失败，请重试') }
  if (typeof done === 'function') done(success)
}
const deletePhotos = async (ids: string[], done: (success: boolean) => void) => {
  try { await store.deletePhotos(ids); done(true) }
  catch { ElMessage.error('删除失败'); done(false) }
}
watch(searchKey, () => {
  store.resetAll()
  Object.values(store.selectedFilters).forEach(values => { if (Array.isArray(values)) values.splice(0) })
  store.browseEnabled = true
  store.browseGranularity = route.query.view === 'year' || route.query.view === 'month' ? route.query.view : 'day'
  store.timeField = route.query.time === 'upload_time' ? 'upload_time' : 'photo_time'
  dateError.value = ''
  store.searchFilters = { search_type: type.value, search_text: query.value }
  if (type.value === 'date') {
    const range = parseDateRange(query.value)
    if (!range) { dateError.value = '无法识别日期，请重新搜索'; return }
    store.searchFilters.start_time = range.start
    // Include subsecond captures in the final second of the requested date.
    store.searchFilters.end_time = range.end.replace('59Z', '59.999999Z')
  }
  void reload()
  void store.fetchAvailableFilters()
}, { immediate: true })
onBeforeUnmount(() => store.resetAll())
</script>
