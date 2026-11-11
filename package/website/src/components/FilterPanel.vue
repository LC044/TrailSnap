<template>
  <div class="space-y-5 p-4">
    <p class="text-xs ts-muted">选择筛选条件。
      <span v-if="store.loading" role="status" class="text-xs ts-muted">正在更新筛选结果…</span>
      <p v-else-if="store.error" role="alert" class="text-sm ts-muted">{{ store.error }} 
        <button type="button" class="ts-button ts-button-ghost" @click="store.loadPhotos(true)">重试</button>
      </p>
    </p>
    <section v-for="group in primaryGroups" :key="group.key" class="space-y-2">
      <h3 class="text-sm font-medium ts-muted">{{ group.label }}</h3>
      <p v-if="baseGroup === group.key" class="text-xs text-primary-600 dark:text-primary-400">已包含搜索条件：{{ baseValue }}</p>
      <div v-if="group.key === 'file_types'" class="flex flex-wrap gap-2">
        <button v-for="value in group.options" :key="value" type="button"
          :data-testid="`filter-type-${value}`" :aria-pressed="isSelected(group.key, value)"
          class="ts-button rounded-full border text-sm"
          :class="isSelected(group.key, value) ? 'bg-primary-500 text-white border-primary-500' : 'ts-button-ghost'"
          @click="toggleFilter(group.key, value)">{{ formatFileType(String(value)) }}</button>
      </div>
      <div v-else class="space-y-2">
        <el-input :model-value="searchQueries[group.key] || ''" :aria-label="`搜索${group.label}`"
          :placeholder="`输入内容筛选${group.label}`" clearable
          @focus="activeGroup = group.key" @update:model-value="value => setSearch(group.key, String(value))" />
        <div v-if="selectedFilters[group.key]?.length" class="flex flex-wrap gap-2">
          <button v-for="value in selectedFilters[group.key]" :key="value" type="button"
            class="ts-button ts-button-ghost text-primary-600 dark:text-primary-400"
            :aria-label="`移除${group.label}：${optionLabel(group.key, value)}`" @click="toggleFilter(group.key, value)">{{ optionLabel(group.key, value) }} ×</button>
        </div>
        <div v-if="activeGroup === group.key" class="max-h-48 overflow-y-auto rounded-xl border border-[var(--ts-color-border)]">
          <p v-if="!filteredOptions(group.key, group.options).length" class="p-3 text-sm ts-muted">没有匹配的{{ group.label }}</p>
          <button v-for="value in filteredOptions(group.key, group.options)" :key="value" type="button"
            class="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-[var(--ts-color-surface-muted)]"
            :aria-label="`${group.label}：${optionLabel(group.key, value)}`" :aria-pressed="isSelected(group.key, value)"
            @click="toggleFilter(group.key, value)">
            <PersonAvatar v-if="group.key === 'people'" class="!w-8 shrink-0" :person="personAvatar(String(value))" />
            <span class="min-w-0 flex-1 truncate">{{ optionLabel(group.key, value) }}</span>
            <span v-if="group.key === 'people'" class="shrink-0 text-xs ts-muted">{{ personOption(String(value))?.photo_count || 0 }} 张</span>
            <span v-if="isSelected(group.key, value)" class="text-primary-600 dark:text-primary-400" aria-hidden="true">✓</span>
          </button>
        </div>
      </div>
    </section>

    <section class="border-t border-[var(--ts-color-border)] pt-3">
      <button type="button" class="ts-button ts-button-ghost w-full justify-between" :aria-expanded="showAdvanced" @click="showAdvanced = !showAdvanced">
        <span>高级筛选<span v-if="advancedCount">（已选 {{ advancedCount }} 项）</span></span>
        <ChevronDown class="h-4 w-4 transition-transform" :class="{ 'rotate-180': showAdvanced }" />
      </button>
      <div v-if="showAdvanced" class="mt-3 space-y-4 pl-3 border-l border-[var(--ts-color-border)]">
        <section v-for="group in advancedGroups" :key="group.key" class="space-y-2">
          <h3 class="text-sm font-medium ts-muted">{{ group.label }}</h3>
          <el-select multiple filterable clearable collapse-tags collapse-tags-tooltip
            :popper-style="popperStyle" @visible-change="raiseOptions"
            :model-value="selectedFilters[group.key] || []" :aria-label="group.label"
            :placeholder="`选择${group.label}`" class="w-full" @update:model-value="values => updateFilter(group.key, values)">
            <el-option v-for="value in group.options" :key="value" :value="value"
              :label="group.key === 'image_types' ? formatImageType(String(value)) : String(value)" />
          </el-select>
        </section>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { usePhotoStore, usePhotosPageStore } from '@/stores/photoStore'
import { computed, ref } from 'vue'
import { ChevronDown } from 'lucide-vue-next'
import { useZIndex } from 'element-plus'
import { nextDialogZIndex } from '@/utils/pickerDate'
import PersonAvatar from '@/components/PersonAvatar.vue'

const props = defineProps<{
  store?: ReturnType<typeof usePhotoStore> | ReturnType<typeof usePhotosPageStore>
}>()
const store = props.store || usePhotoStore()
const availableFilters = computed(() => store.availableFilters)
const selectedFilters = store.selectedFilters
const showAdvanced = ref(false)
const activeGroup = ref<string>('')
const searchQueries = ref<Record<string, string>>({})
const setSearch = (key: string, value: string) => {
  searchQueries.value[key] = value
  activeGroup.value = key
}
const filteredOptions = (key: string, options: (string | number)[]) => {
  const query = (searchQueries.value[key] || '').trim().toLocaleLowerCase()
  return options.filter(value => optionLabel(key, value).toLocaleLowerCase().includes(query))
}
const { nextZIndex } = useZIndex()
const popperStyle = ref({ zIndex: 2000 })
// Teleported options must be above the currently open dialog/lightbox layer.
const raiseOptions = (visible: boolean) => {
  if (visible) popperStyle.value = { zIndex: nextDialogZIndex(nextZIndex) }
}
const peopleById = computed(() => new Map((availableFilters.value?.person_options || []).map(person => [person.id, person])))
const personOption = (id: string) => peopleById.value.get(id)
const optionLabel = (key: string, value: string | number) => key === 'people' ? personOption(String(value))?.name || String(value) : String(value)
const personAvatar = (id: string) => {
  const person = personOption(id)
  return { cover_photo: person?.photo_id ? {
    photo_id: person.photo_id, face_rect: person.face_rect || null,
    face_confidence: null, recognize_confidence: null,
  } : null }
}
type FilterKey = 'file_types' | 'years' | 'cities' | 'people' | 'categories' | 'image_types' | 'makes' | 'models'
const primaryGroups = computed(() => [
  { key: 'file_types' as const, label: '媒体类型', options: availableFilters.value?.file_types || [] },
  { key: 'years' as const, label: '拍摄年份', options: availableFilters.value?.years || [] },
  { key: 'cities' as const, label: '地点', options: availableFilters.value?.cities || [] },
  { key: 'people' as const, label: '人物', options: (availableFilters.value?.person_options || []).map(person => person.id) },
  { key: 'categories' as const, label: '类别', options: availableFilters.value?.categories || [] },
])
const advancedGroups = computed(() => [
  { key: 'image_types' as const, label: '来源', options: availableFilters.value?.image_types || [] },
  { key: 'makes' as const, label: '相机品牌', options: availableFilters.value?.makes || [] },
  { key: 'models' as const, label: '相机型号', options: availableFilters.value?.models || [] },
])
const advancedCount = computed(() => advancedGroups.value.reduce((count, group) => count + (selectedFilters[group.key]?.length || 0), 0))
const baseGroup = computed(() => ({ location: 'cities', person: 'people', tag: 'categories', date: 'years' }[store.searchFilters?.search_type || '']))
const baseValue = computed(() => store.searchFilters?.search_text || '')
const isSelected = (key: FilterKey, value: string | number) => (selectedFilters[key] as (string | number)[] | undefined)?.includes(value) || false
const updateFilter = (key: FilterKey, values: (string | number)[]) => {
  // Element Plus may emit the same array instance. Snapshot before splicing.
  const next = [...values]
  // Keep raw values for API filtering; labels are presentation only.
  const current = selectedFilters[key] as (string | number)[] | undefined
  if (current) current.splice(0, current.length, ...next)
  else Object.assign(selectedFilters, { [key]: next })
  void store.loadPhotos(true)
}
const toggleFilter = (key: FilterKey, value: string | number) => {
  const values = [...(selectedFilters[key] || [])] as (string | number)[]
  const index = values.indexOf(value)
  if (index < 0) values.push(value)
  else values.splice(index, 1)
  updateFilter(key, values)
}
const formatImageType = (value: string) => ({ Camera: '相机', Screenshot: '截屏', Other: '其他' }[value] || value)
const formatFileType = (value: string) => ({ image: '图片', video: '视频', live_photo: '实况图', panorama: '360° 全景' }[value] || value)
</script>
