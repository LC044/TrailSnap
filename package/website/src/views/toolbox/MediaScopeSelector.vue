<template>
  <section class="space-y-4">
    <details :open="scopeExpanded" @toggle="scopeExpanded = ($event.target as HTMLDetailsElement).open">
      <summary class="cursor-pointer py-3 font-medium">选择照片</summary>
      <div class="space-y-4 pt-3">
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5" role="group" aria-label="范围来源">
      <button v-for="source in sources" :key="source.value" type="button"
        class="ts-button ts-button-secondary" :aria-pressed="scope.source === source.value"
        :class="scope.source === source.value ? 'scope-selected' : ''"
        @click="update({ source: source.value, excluded_ids: [] })">
        <Check v-if="scope.source === source.value" class="h-4 w-4 shrink-0" aria-hidden="true" /><component v-else :is="source.icon" class="h-4 w-4" />{{ source.label }}
      </button>
    </div>
    <button type="button" class="ts-button ts-button-secondary" @click="openFilters">
      <Filter class="h-4 w-4" aria-hidden="true" />筛选照片
      <span v-if="filterCount">（{{ filterCount }}）</span>
    </button>

    <el-form label-position="top">
      <el-form-item v-if="scope.source === 'albums'">
        <el-select :model-value="scope.album_ids" aria-label="搜索相册" multiple filterable remote :remote-method="searchAlbums"
          :loading="albumsLoading" placeholder="搜索相册" class="w-full" @update:model-value="update({ album_ids: $event })"
          @visible-change="value => value && searchAlbums('')">
          <el-option v-for="album in albums" :key="album.id" :value="album.id" :label="`${album.name} · ${album.num_photos} 项`" />
        </el-select>
        <p v-if="albumError" class="mt-2 text-sm text-red-600 dark:text-red-400" role="alert">
          {{ albumError }} <button type="button" class="underline" @click="searchAlbums('')">重试</button>
        </p>
      </el-form-item>

      <div v-if="scope.source === 'folders'" class="space-y-3">
        <div class="flex flex-wrap items-center gap-2">
          <el-button @click="folderPicker = true">选择</el-button>
          <el-checkbox :model-value="scope.include_children" @update:model-value="update({ include_children: !!$event })">包含子文件夹</el-checkbox>
        </div>
        <div v-for="path in scope.folders" :key="path" class="ts-divider flex min-w-0 items-center gap-2 rounded-xl border p-3">
          <Folder class="h-4 w-4 shrink-0 text-primary-500" />
          <span class="min-w-0 flex-1 break-all text-sm">{{ path }}</span>
          <button type="button" class="ts-icon-button" :aria-label="`移除 ${path}`" @click="update({ folders: scope.folders.filter(p => p !== path) })"><X class="h-4 w-4" /></button>
        </div>
      </div>

      <div v-if="scope.source === 'selected'" class="flex flex-wrap items-center gap-3">
        <el-button @click="photoPicker = true">选择照片</el-button>
        <span class="ts-muted text-sm">已选 {{ scope.photo_ids.length }} 项</span>
      </div>


      <details :open="scope.source === 'filter' || !!scope.start_date || !!scope.end_date || scope.upload_time_fallback || scope.media_type !== 'image'" class="mt-4">
        <summary class="cursor-pointer py-3 text-sm">日期与类型</summary>
        <el-form-item label="拍摄日期">
          <UnifiedDatePicker :model-value="dateRange" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期"
            end-placeholder="结束日期" class="w-full max-w-md" @update:model-value="setDates" />
        </el-form-item>
        <el-form-item label="媒体类型" class="mt-4">
          <el-select :model-value="scope.media_type" class="w-full max-w-md" @update:model-value="update({ media_type: $event })">
            <el-option label="照片" value="image" />
            <el-option label="视频" value="video" disabled />
          </el-select>
        </el-form-item>
      </details>
    </el-form>

      </div>
    </details>
    <DirectoryPickerDialog v-model:visible="folderPicker" :model-value="chosenFolder" @update:model-value="addFolder" />
    <PhotoSelectorDialog v-model="photoPicker" title="选择照片" :store="selectionStore" auto-load enable-filters
      :allowed-file-types="['image', 'panorama']" :initial-selected-ids="scope.photo_ids"
      @select="ids => { update({ photo_ids: ids }); photoPicker = false }" />
    <ResponsiveDialog v-model="showFilters" title="筛选照片" max-width="28rem" mobile-mode="fullscreen" mobile-back>
      <p v-if="filterError" role="alert" class="mb-3 text-sm text-red-600 dark:text-red-400">
        无法加载筛选条件 <button type="button" class="underline" @click="loadFilterOptions">重试</button>
      </p>
      <FilterPanel v-if="showFilters" :store="filterStore" />
      <template #footer>
        <div class="flex justify-end gap-2">
          <button type="button" class="ts-button ts-button-secondary" @click="showFilters = false">取消</button>
          <button type="button" class="ts-button ts-button-primary" @click="applyFilters">应用筛选</button>
        </div>
      </template>
    </ResponsiveDialog>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { CalendarDays, Check, Filter, Folder, Images, CheckSquare, Library, X } from 'lucide-vue-next'
import { albumService } from '@/api/album'
import type { ApiAlbum, FilterOptions, FilterState } from '@/types/album'
import type { MediaScope } from '@/api/toolboxWorkflows'
import { useUserStore } from '@/stores/user'
import { useSelectionStore } from '@/stores/selectionStore'
import DirectoryPickerDialog from '@/components/DirectoryPickerDialog.vue'
import PhotoSelectorDialog from '@/components/PhotoSelectorDialog.vue'
import FilterPanel from '@/components/FilterPanel.vue'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import UnifiedDatePicker from '@/components/ui/UnifiedDatePicker.vue'

const props = defineProps<{ scope: MediaScope; count: number | null; checking: boolean }>()
const emit = defineEmits<{ 'update:scope': [scope: MediaScope]; check: [] }>()
const update = (change: Partial<MediaScope>) => emit('update:scope', { ...props.scope, ...change })
const sources = [
  { value: 'all', label: '全部', icon: Library },
  { value: 'selected', label: '手动选', icon: CheckSquare },
  { value: 'albums', label: '相册', icon: Images }, { value: 'folders', label: '文件夹', icon: Folder },
  { value: 'filter', label: '按日期筛选', icon: CalendarDays },
] as const
const valid = computed(() => {
  const s = props.scope
  return s.source === 'all' || (s.source === 'albums' && s.album_ids.length > 0)
    || (s.source === 'folders' && s.folders.length > 0) || (s.source === 'selected' && s.photo_ids.length > 0)
    || (s.source === 'filter' && !!(s.start_date || s.end_date))
})
const scopeExpanded = ref(props.scope.source === 'all' || !valid.value)
const dateRange = computed(() => props.scope.start_date && props.scope.end_date ? [props.scope.start_date, props.scope.end_date] : null)
const setDates = (value: unknown) => {
  const range = Array.isArray(value) ? value as string[] : []
  update({ start_date: range[0] || null, end_date: range[1] || null })
}
const albums = ref<ApiAlbum[]>([])
const albumsLoading = ref(false)
const albumError = ref('')
const user = useUserStore()
let searchVersion = 0
const searchAlbums = async (search: string) => {
  const version = ++searchVersion
  albumsLoading.value = true
  albumError.value = ''
  try {
    const rows = await albumService.getAlbums(0, 1000)
    if (version !== searchVersion) return
    albums.value = rows.filter(a => a.type === 'user' && a.owner_id === user.userInfo?.id
      && (a.name.includes(search) || props.scope.album_ids.includes(a.id)))
  } catch { if (version === searchVersion) albumError.value = '相册加载失败' }
  finally { if (version === searchVersion) albumsLoading.value = false }
}
const folderPicker = ref(false)
const chosenFolder = ref('')
const addFolder = (path: string) => {
  chosenFolder.value = path
  if (path && !props.scope.folders.includes(path)) {
    update({ folders: [...props.scope.folders, path] })
  }
}
const photoPicker = ref(false)
const selectionStore = useSelectionStore()
const emptyFilters = (): FilterState => ({
  years: [], cities: [], makes: [], models: [], image_types: [], file_types: [], people: [], categories: [],
})
const showFilters = ref(false)
const filterOptions = ref<FilterOptions | null>(null)
const filtersLoading = ref(false)
const filterError = ref(false)
const draftFilters = reactive(emptyFilters())
const filterCount = computed(() => Object.values(props.scope.filters || {}).reduce((total, values) => total + values.length, 0))
const filterStore = {
  selectedFilters: draftFilters,
  get availableFilters() { return filterOptions.value },
  get loading() { return filtersLoading.value },
  error: null,
  // FilterPanel updates the draft. Applying the draft updates the tool scope.
  async loadPhotos() {},
}
const loadFilterOptions = async () => {
  if (filtersLoading.value) return
  filtersLoading.value = true
  filterError.value = false
  try {
    const options = await albumService.getFilterOptions()
    filterOptions.value = { ...options, file_types: options.file_types.filter(type => type === 'image' || type === 'panorama') }
  } catch {
    filterError.value = true
  } finally {
    filtersLoading.value = false
  }
}
const openFilters = () => {
  Object.assign(draftFilters, emptyFilters(), JSON.parse(JSON.stringify(props.scope.filters || {})))
  showFilters.value = true
  if (!filterOptions.value) void loadFilterOptions()
}
const applyFilters = () => {
  const filters = Object.fromEntries(Object.entries(draftFilters).filter(([, values]) => values.length)
    .map(([key, values]) => [key, [...values]])) as Partial<FilterState>
  update({ filters: Object.keys(filters).length ? filters : null })
  showFilters.value = false
}
</script>

<style scoped>
.scope-selected {
  border-color: var(--theme-primary);
  background: rgba(var(--theme-rgb), .12);
  color: var(--theme-primary);
}
</style>
