<template>
  <div class="filter-panel">
    <!-- 状态行：当前条件数量 + 一键清除 -->
    <div class="flex items-center justify-between gap-3">
      <p class="flex min-w-0 items-center gap-1.5 text-xs ts-muted">
        <Loader2 v-if="store.loading" class="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden="true" />
        <SlidersHorizontal v-else class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span v-if="store.loading" role="status" class="truncate">正在更新筛选结果…</span>
        <span v-else-if="activeCount" role="status" class="truncate">已选 {{ activeCount }} 个条件</span>
        <span v-else role="status" class="truncate">选择筛选条件</span>
      </p>
      <button v-if="activeCount" type="button" class="filter-clear shrink-0" @click="clearAll">
        <RotateCcw class="h-3.5 w-3.5" aria-hidden="true" />清除全部
      </button>
    </div>

    <p v-if="store.error" role="alert" class="filter-alert">
      <span class="min-w-0 flex-1">{{ store.error }}</span>
      <button type="button" class="filter-clear shrink-0" @click="store.loadPhotos(true)">重试</button>
    </p>

    <section v-for="group in primaryGroups" :key="group.key" class="filter-group">
      <div class="flex items-baseline justify-between gap-2">
        <h3 class="filter-group-label">{{ group.label }}</h3>
        <span v-if="selectedCount(group.key)" class="filter-count">已选 {{ selectedCount(group.key) }}</span>
      </div>

      <p v-if="baseGroup === group.key" class="filter-note">
        <Search class="h-3 w-3 shrink-0" aria-hidden="true" />
        <span class="truncate">已包含搜索条件「{{ baseValue }}」</span>
      </p>

      <!-- 高频选项直接平铺：不用点开就能选，选中项填满主色 -->
      <div v-if="group.options.length" class="filter-chips">
        <button v-for="value in chipValues(group)" :key="value" type="button"
          :data-testid="group.key === 'file_types' ? `filter-type-${value}` : undefined"
          class="filter-choice" :class="{ 'is-active': isSelected(group.key, value), 'has-avatar': group.key === 'people' }"
          :aria-pressed="isSelected(group.key, value)"
          @click="toggleFilter(group.key, value)">
          <PersonAvatar v-if="group.key === 'people'" class="!h-5 !w-5 shrink-0 !border-0" :person="personAvatar(String(value))" />
          <span class="min-w-0 truncate">{{ chipLabel(group.key, value) }}</span>
        </button>
      </div>
      <p v-else class="text-xs ts-muted">暂无可选的{{ group.label }}</p>

      <!-- 选项过多时才提供检索：输入即筛，列表带人物头像与照片数 -->
      <button v-if="group.options.length > CHIP_LIMIT" type="button" class="filter-more"
        :aria-expanded="!!expanded[group.key]" @click="toggleExpand(group.key)">
        <span>{{ expanded[group.key] ? '收起检索' : `搜索全部 ${group.options.length} 项` }}</span>
        <ChevronDown class="h-3.5 w-3.5 shrink-0 transition-transform" :class="{ 'rotate-180': expanded[group.key] }" />
      </button>

      <div v-if="expanded[group.key]" class="filter-explore">
        <el-input class="filter-field" :ref="setInputRef(group.key)" :model-value="searchQueries[group.key] || ''"
          :aria-label="`搜索${group.label}`" :placeholder="`搜索${group.label}`" clearable
          @update:model-value="value => setSearch(group.key, String(value))" />
        <div class="filter-options" :aria-label="`${group.label}候选`">
          <p v-if="!filteredOptions(group.key, group.options).length" class="px-3 py-3 text-xs ts-muted">没有匹配的{{ group.label }}</p>
          <button v-for="value in filteredOptions(group.key, group.options)" :key="value" type="button"
            class="filter-option" :class="{ 'is-selected': isSelected(group.key, value) }"
            :aria-label="`${group.label}：${optionLabel(group.key, value)}`" :aria-pressed="isSelected(group.key, value)"
            @click="toggleFilter(group.key, value)">
            <PersonAvatar v-if="group.key === 'people'" class="!w-7 shrink-0" :person="personAvatar(String(value))" />
            <span class="min-w-0 flex-1 truncate">{{ optionLabel(group.key, value) }}</span>
            <span v-if="group.key === 'people'" class="shrink-0 text-[11px] tabular-nums ts-muted">{{ personOption(String(value))?.photo_count || 0 }} 张</span>
            <Check v-if="isSelected(group.key, value)" class="h-4 w-4 shrink-0" aria-hidden="true" />
          </button>
        </div>
      </div>
    </section>

    <section class="filter-advanced">
      <button type="button" class="filter-advanced-toggle" :aria-expanded="showAdvanced" @click="showAdvanced = !showAdvanced">
        <span class="flex min-w-0 items-center gap-2">
          <Settings2 class="h-4 w-4 shrink-0" aria-hidden="true" />
          <span class="truncate text-[13px] font-semibold text-[var(--ts-color-text)]">高级筛选</span>
          <span v-if="advancedCount" class="filter-badge">{{ advancedCount }}</span>
        </span>
        <ChevronDown class="h-4 w-4 shrink-0 text-[var(--ts-color-text-tertiary)] transition-transform" :class="{ 'rotate-180': showAdvanced }" />
      </button>
      <div v-if="showAdvanced" class="filter-advanced-body">
        <div v-for="group in advancedGroups" :key="group.key" class="space-y-1.5">
          <h3 class="filter-group-label">{{ group.label }}</h3>
          <el-select multiple filterable clearable collapse-tags collapse-tags-tooltip
            class="filter-select w-full" popper-class="photo-filter-options-popper"
            :popper-style="popperStyle" @visible-change="raiseOptions"
            :model-value="selectedFilters[group.key] || []" :aria-label="group.label"
            :placeholder="`选择${group.label}`" @update:model-value="values => updateFilter(group.key, values)">
            <el-option v-for="value in group.options" :key="value" :value="value"
              :label="group.key === 'image_types' ? formatImageType(String(value)) : String(value)" />
          </el-select>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { usePhotoStore } from '@/stores/photoStore'
import { computed, nextTick, ref } from 'vue'
import { Check, ChevronDown, Loader2, RotateCcw, Search, Settings2, SlidersHorizontal } from 'lucide-vue-next'
import { useZIndex } from 'element-plus'
import { nextDialogZIndex } from '@/utils/pickerDate'
import PersonAvatar from '@/components/PersonAvatar.vue'

const props = defineProps<{
  store?: Pick<ReturnType<typeof usePhotoStore>, 'availableFilters' | 'selectedFilters' | 'loading' | 'error' | 'loadPhotos'>
    & Partial<Pick<ReturnType<typeof usePhotoStore>, 'searchFilters'>>
}>()
const store = props.store || usePhotoStore()
const availableFilters = computed(() => store.availableFilters)
const selectedFilters = store.selectedFilters
const showAdvanced = ref(false)
// 每个分组独立展开检索；高频项已平铺，展开只用于长列表。
const expanded = ref<Record<string, boolean>>({})
const searchQueries = ref<Record<string, string>>({})
const setSearch = (key: string, value: string) => {
  searchQueries.value[key] = value
}
const inputRefs = new Map<string, { focus: () => void }>()
const setInputRef = (key: string) => (el: unknown) => {
  if (el) inputRefs.set(key, el as { focus: () => void })
  else inputRefs.delete(key)
}
const toggleExpand = async (key: string) => {
  const next = !expanded.value[key]
  expanded.value[key] = next
  if (!next) return
  await nextTick()
  inputRefs.get(key)?.focus()
}
const filteredOptions = (key: string, options: (string | number)[]) => {
  const query = (searchQueries.value[key] || '').trim().toLocaleLowerCase()
  if (!query) return options
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
// 平铺胶囊需要把枚举值翻译成中文，否则会露出 image / live_photo 这种原始值。
const chipLabel = (key: FilterKey, value: string | number) => {
  if (key === 'file_types') return formatFileType(String(value))
  if (key === 'image_types') return formatImageType(String(value))
  return optionLabel(key, value)
}
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
// 平铺数量上限：后端已按使用频率排序，取前 N 个就是最可能被点的项。
const CHIP_LIMIT = 8
const chipValues = (group: { key: FilterKey, options: (string | number)[] }) => {
  const head = group.options.slice(0, CHIP_LIMIT)
  const selected = (selectedFilters[group.key] || []) as (string | number)[]
  // 已选但不在前 N 项里的必须补上，否则选中状态看不见。
  return [...head, ...selected.filter(value => !head.includes(value))]
}
const selectedCount = (key: FilterKey) => (selectedFilters[key] as (string | number)[] | undefined)?.length || 0
const advancedCount = computed(() => advancedGroups.value.reduce((count, group) => count + (selectedFilters[group.key]?.length || 0), 0))
const activeCount = computed(() => [...primaryGroups.value, ...advancedGroups.value]
  .reduce((count, group) => count + (selectedFilters[group.key]?.length || 0), 0))
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
const clearAll = () => {
  for (const values of Object.values(selectedFilters)) {
    if (Array.isArray(values)) values.splice(0)
  }
  searchQueries.value = {}
  expanded.value = {}
  void store.loadPhotos(true)
}
// 弹窗底部操作条（重置/完成）由宿主调用，筛选逻辑集中在本组件。
defineExpose({ clearAll })
const formatImageType = (value: string) => ({ Camera: '相机', Screenshot: '截屏', Other: '其他' }[value] || value)
const formatFileType = (value: string) => ({ image: '图片', video: '视频', live_photo: '实况图', panorama: '360° 全景' }[value] || value)
</script>

<style scoped>
/* 面板本身不设底色，由宿主提供实心表面；层次靠「平铺选项 + 凹槽检索」建立。 */
.filter-panel { display: flex; flex-direction: column; gap: 15px; }
.filter-group { display: flex; flex-direction: column; gap: 8px; }
.filter-group-label { font-size: 12px; font-weight: 600; line-height: 1.5; color: var(--ts-color-text-secondary); }
.filter-count { flex-shrink: 0; font-size: 11px; font-variant-numeric: tabular-nums; color: var(--ts-color-text-tertiary); }

.filter-clear {
  display: inline-flex; align-items: center; gap: 4px;
  height: 26px; padding: 0 8px; border: 1px solid transparent; border-radius: var(--ts-radius-pill);
  background: transparent; color: var(--ts-color-text-secondary);
  font-size: 12px; font-weight: 600; cursor: pointer;
  transition: background-color 140ms ease, color 140ms ease;
}
.filter-clear:hover { background: var(--ts-color-surface-muted); color: var(--ts-color-text); }
.filter-clear:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 2px; }

.filter-alert {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px 6px 10px; border-radius: 12px; font-size: 12px;
  border: 1px solid color-mix(in srgb, var(--ts-color-danger) 32%, transparent);
  background: color-mix(in srgb, var(--ts-color-danger) 8%, transparent);
  color: var(--ts-color-danger);
}

.filter-note {
  display: flex; align-items: center; gap: 5px;
  padding: 5px 8px; border-radius: 9px; font-size: 12px;
  background: rgba(var(--theme-rgb), .08); color: var(--theme-primary);
}

/* 平铺选项：默认中性胶囊，选中填满主色（对比度足够，弱光下也分得清） */
.filter-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.filter-choice {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  min-height: 31px; max-width: 100%; padding: 0 12px;
  border: 1px solid transparent; border-radius: var(--ts-radius-pill);
  background: var(--ts-color-surface-muted); color: var(--ts-color-text-secondary);
  font-size: 13px; font-weight: 600; line-height: 1.2; cursor: pointer;
  transition: background-color 140ms ease, color 140ms ease, border-color 140ms ease, box-shadow 140ms ease;
}
.filter-choice.has-avatar { padding-left: 6px; }
.filter-choice:hover { color: var(--ts-color-text); border-color: var(--ts-color-border); }
.filter-choice.is-active {
  background: var(--theme-primary); border-color: var(--theme-primary); color: #fff;
  box-shadow: 0 2px 8px rgba(var(--theme-rgb), .28);
}
.filter-choice.is-active:hover { color: #fff; }
.filter-choice:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 2px; }

.filter-more {
  display: inline-flex; align-items: center; gap: 4px; align-self: flex-start;
  min-height: 26px; padding: 0 8px 0 6px; border: 0; border-radius: 8px;
  background: transparent; color: var(--ts-color-text-secondary);
  font-size: 12px; font-weight: 600; cursor: pointer;
  transition: background-color 140ms ease, color 140ms ease;
}
.filter-more:hover { background: var(--ts-color-surface-muted); color: var(--ts-color-text); }
.filter-more:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 2px; }

.filter-explore { display: flex; flex-direction: column; gap: 8px; }

/* 检索输入框：比面板低一层的实心凹槽，聚焦时抬高并画出主色描边 */
.filter-field :deep(.el-input__wrapper) {
  min-height: 38px; padding: 1px 8px 1px 12px;
  border-radius: 12px;
  background: var(--ts-color-surface-muted);
  box-shadow: inset 0 0 0 1px transparent;
  transition: background-color 160ms ease, box-shadow 160ms ease;
}
.filter-field :deep(.el-input__wrapper:hover) { box-shadow: inset 0 0 0 1px var(--ts-color-border); }
.filter-field :deep(.el-input__wrapper.is-focus) {
  background: var(--ts-color-surface);
  box-shadow: inset 0 0 0 1px var(--theme-primary), 0 0 0 3px rgba(var(--theme-rgb), .14);
}
.filter-field :deep(.el-input__inner) { font-size: 14px; color: var(--ts-color-text); }
.filter-field :deep(.el-input__inner::placeholder) { color: var(--ts-color-text-tertiary); }

/* 候选列表：白底浮层压住凹槽输入 */
.filter-options {
  max-height: 208px; overflow-y: auto; overscroll-behavior: contain;
  padding: 4px; border: 1px solid var(--ts-color-border); border-radius: 12px;
  background: var(--ts-color-surface); box-shadow: var(--ts-shadow-card);
}
.filter-option {
  display: flex; align-items: center; gap: 8px; width: 100%;
  min-height: 38px; padding: 6px 10px; border: 0; border-radius: 9px;
  background: transparent; color: var(--ts-color-text);
  font-size: 13px; text-align: left; cursor: pointer;
  transition: background-color 120ms ease, color 120ms ease;
}
.filter-option:hover { background: var(--ts-color-surface-muted); }
.filter-option.is-selected { background: rgba(var(--theme-rgb), .12); color: var(--theme-primary); font-weight: 600; }

/* 分组多时面板会滚动；高级筛选保持在内容末尾，由宿主决定是否吸附。 */
.filter-advanced {
  border-top: 1px solid var(--ts-color-divider);
  padding-top: 12px;
}
.filter-advanced-toggle {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  width: 100%; min-height: 42px; padding: 0 12px;
  border: 1px solid var(--ts-color-border); border-radius: 12px;
  background: var(--ts-color-surface); color: var(--ts-color-text); cursor: pointer;
  transition: background-color 140ms ease, border-color 140ms ease;
}
.filter-advanced-toggle:hover { background: var(--ts-color-surface-muted); }
.filter-advanced-toggle[aria-expanded='true'] { background: var(--ts-color-surface-muted); }
.filter-advanced-toggle:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 2px; }
.filter-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 18px; height: 18px; padding: 0 5px; border-radius: var(--ts-radius-pill);
  background: var(--theme-primary); color: #fff;
  font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums;
}
/* 高级筛选与主筛选共用同一套字段样式，只靠折叠行分隔，避免多一层底色把控件反色 */
.filter-advanced-body { display: flex; flex-direction: column; gap: 12px; margin-top: 10px; }
.filter-select :deep(.el-select__wrapper) {
  min-height: 38px; padding: 1px 8px 1px 12px;
  border-radius: 12px;
  background: var(--ts-color-surface-muted);
  box-shadow: inset 0 0 0 1px transparent;
  transition: background-color 160ms ease, box-shadow 160ms ease;
}
.filter-select :deep(.el-select__wrapper:hover) { box-shadow: inset 0 0 0 1px var(--ts-color-border); }
.filter-select :deep(.el-select__wrapper.is-focused) {
  background: var(--ts-color-surface);
  box-shadow: inset 0 0 0 1px var(--theme-primary), 0 0 0 3px rgba(var(--theme-rgb), .14);
}
.filter-select :deep(.el-select__placeholder) { color: var(--ts-color-text-tertiary); font-size: 14px; }
.filter-select :deep(.el-select__wrapper.is-focused .el-select__placeholder),
.filter-select :deep(.el-select__selected-item:not(.el-select__placeholder)) { color: var(--ts-color-text); font-size: 14px; }
.filter-select :deep(.el-select__caret) { color: var(--ts-color-text-tertiary); }
.filter-select :deep(.el-tag) { border-radius: 7px; }

@media (max-width: 767px) {
  .filter-choice { min-height: 36px; }
}
@media (prefers-reduced-motion: reduce) {
  .filter-choice, .filter-option, .filter-clear, .filter-more, .filter-advanced-toggle { transition: none; }
}
</style>
