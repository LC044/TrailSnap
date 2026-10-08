<template>
  <div class="unified-date-picker min-w-0" v-bind="$attrs">
    <el-date-picker
      v-if="!isMobile && type !== 'time'"
      :id="id"
      ref="desktopPicker"
      :model-value="modelValue"
      :type="type === 'datetime-local' ? 'datetime' : type"
      :value-format="valueFormat"
      :format="format"
      :placeholder="placeholder"
      :start-placeholder="startPlaceholder"
      :end-placeholder="endPlaceholder"
      :range-separator="rangeSeparator"
      :clearable="clearable"
      :disabled="disabled"
      :disabled-date="disabledDesktopDate"
      :shortcuts="shortcuts"
      :aria-label="String($attrs['aria-label'] || placeholder)"
      size="large"
      class="!w-full"
      @update:model-value="publish"
    />
    <div v-else class="flex min-w-0 items-center gap-2">
      <template v-if="isRange">
        <button type="button" class="picker-trigger" :disabled="disabled" @click="open(0, 'date')">{{ display(0, 'date') || startPlaceholder }}</button>
        <span class="shrink-0 text-xs text-gray-500 dark:text-gray-400">{{ rangeSeparator }}</span>
        <button type="button" class="picker-trigger" :disabled="disabled" @click="open(1, 'date')">{{ display(1, 'date') || endPlaceholder }}</button>
      </template>
      <template v-else>
        <button :id="id" ref="trigger" type="button" class="picker-trigger" :disabled="disabled" :aria-label="String($attrs['aria-label'] || placeholder)" @click="open(0, type === 'time' ? 'time' : 'date')">{{ display(0, type === 'time' ? 'time' : 'date') || placeholder }}</button>
        <button v-if="hasTime && type !== 'time'" type="button" class="picker-trigger !flex-none" :disabled="disabled" aria-label="调整时间" @click="open(0, 'time')">{{ display(0, 'time') || '时间' }}</button>
      </template>
      <button v-if="clearable && hasValue && !disabled" type="button" class="shrink-0 rounded-lg p-2 text-gray-500 dark:text-gray-400" aria-label="清空日期" @click="clear"><X class="h-4 w-4" /></button>
    </div>
    <input v-if="required" class="sr-only" tabindex="-1" type="text" :value="hasValue ? 'selected' : ''" required aria-label="请选择日期时间" @focus="open(0, 'date')" />
    <ResponsiveDialog v-model="visible" history :title="dialogTitle" max-width="28rem" :glass="false">
      <div v-if="hasTime && type !== 'time'" class="mb-4 grid grid-cols-2 gap-2">
        <button v-for="tab in (['date', 'time'] as const)" :key="tab" type="button" class="ts-button" :class="mode === tab ? 'ts-button-primary' : 'ts-button-secondary'" @click="mode = tab">{{ tab === 'date' ? '日期' : '时间' }}</button>
      </div>
      <div v-if="mode === 'date'" class="flex gap-3">
        <DateWheelColumn v-model="year" :options="years" label="年" />
        <DateWheelColumn v-model="month" :options="months" label="月" />
        <DateWheelColumn v-if="type !== 'month'" v-model="day" :options="days" label="日" />
      </div>
      <div v-else class="flex gap-3">
        <DateWheelColumn v-model="hour" :options="hours" label="时" />
        <DateWheelColumn v-model="minute" :options="minutes" label="分" />
        <DateWheelColumn v-if="showSeconds" v-model="second" :options="seconds" label="秒" />
      </div>
      <p class="mt-4 text-center text-sm" :class="validationMessage ? 'text-red-600 dark:text-red-400' : 'text-gray-600 dark:text-gray-300'">{{ validationMessage || preview }}</p>
      <div v-if="shortcuts.length" class="mt-3 flex flex-wrap justify-center gap-2">
        <button v-for="shortcut in shortcuts" :key="shortcut.text" type="button" class="ts-button ts-button-secondary text-xs" @click="applyShortcut(shortcut)">{{ shortcut.text }}</button>
      </div>
      <template #footer>
        <div class="flex gap-3"><button type="button" class="ts-button ts-button-secondary flex-1" @click="visible = false">取消</button><button type="button" class="ts-button ts-button-primary flex-1" :disabled="!!validationMessage" @click="confirm">确定</button></div>
      </template>
    </ResponsiveDialog>
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import type { DatePickerInstance } from 'element-plus'
import { X } from 'lucide-vue-next'
import { useFormItem } from 'element-plus'
import DateWheelColumn from './DateWheelColumn.vue'
import ResponsiveDialog from './ResponsiveDialog.vue'
import { daysInMonth, formatPickerDate, parsePickerDate } from '@/utils/pickerDate'
defineOptions({ inheritAttrs: false })
type DateValue = string | Date | number
type Shortcut = { text: string; value: Date | (() => Date) }
const props = withDefaults(defineProps<{
  modelValue?: DateValue | (DateValue | null)[] | null
  type?: 'date' | 'datetime' | 'datetime-local' | 'daterange' | 'month' | 'time'
  id?: string; placeholder?: string; startPlaceholder?: string; endPlaceholder?: string; rangeSeparator?: string
  valueFormat?: string; format?: string; clearable?: boolean; disabled?: boolean; required?: boolean
  min?: string; max?: string; disabledDate?: (date: Date) => boolean; shortcuts?: Shortcut[]
  start?: string; end?: string; step?: string
}>(), { type: 'date', placeholder: '选择日期', startPlaceholder: '开始日期', endPlaceholder: '结束日期', rangeSeparator: '至', clearable: true, disabled: false, shortcuts: () => [] })
const emit = defineEmits<{ 'update:modelValue': [any]; change: [any] }>()
const { formItem } = useFormItem()
const isMobile = useMediaQuery('(max-width: 767px)')
const desktopPicker = ref<DatePickerInstance | null>(null)
const visible = ref(false), mode = ref<'date' | 'time'>('date'), rangeIndex = ref(0), trigger = ref<HTMLButtonElement | null>(null)
const year = ref(2000), month = ref(1), day = ref(1), hour = ref(0), minute = ref(0), second = ref(0)
const isRange = computed(() => props.type === 'daterange')
const hasTime = computed(() => ['datetime', 'datetime-local', 'time'].includes(props.type))
const showSeconds = computed(() => (props.valueFormat || props.format || '').includes('ss'))
const hasValue = computed(() => Array.isArray(props.modelValue) ? props.modelValue.some(Boolean) : props.modelValue !== null && props.modelValue !== undefined && props.modelValue !== '')
const sequence = (length: number, first = 0) => Array.from({ length }, (_, index) => index + first)
const years = computed(() => {
  const selectedYear = parsePickerDate(raw(rangeIndex.value)).getFullYear()
  const from = props.min ? parsePickerDate(props.min).getFullYear() : Math.min(1900, selectedYear)
  const to = props.max ? parsePickerDate(props.max).getFullYear() : Math.max(new Date().getFullYear() + 100, selectedYear)
  return sequence(Math.max(1, to - from + 1), from)
})
const months = sequence(12, 1), hours = sequence(24), seconds = sequence(60)
const minuteStep = computed(() => props.step ? Math.max(1, Number(props.step.split(':')[1]) || 1) : 1)
const minutes = computed(() => sequence(Math.ceil(60 / minuteStep.value)).map(value => value * minuteStep.value))
const days = computed(() => sequence(daysInMonth(year.value, month.value), 1))
watch([year, month], () => { day.value = Math.min(day.value, daysInMonth(year.value, month.value)) }, { flush: 'sync' })
const candidate = computed(() => new Date(year.value, month.value - 1, props.type === 'month' ? 1 : day.value, hasTime.value ? hour.value : 0, hasTime.value ? minute.value : 0, hasTime.value ? second.value : 0))
const preview = computed(() => formatPickerDate(candidate.value, props.type === 'time' ? 'HH:mm' : props.type === 'month' ? 'YYYY年MM月' : hasTime.value ? 'YYYY-MM-DD HH:mm' + (showSeconds.value ? ':ss' : '') : 'YYYY年MM月DD日'))
const dialogTitle = computed(() => isRange.value ? rangeIndex.value === 0 ? props.startPlaceholder : props.endPlaceholder : props.type === 'month' ? '选择月份' : mode.value === 'date' ? '选择日期' : '选择时间')
function raw(index: number): DateValue | null | undefined { return Array.isArray(props.modelValue) ? props.modelValue[index] : props.modelValue }
function display(index: number, part: 'date' | 'time') {
  const value = raw(index)
  if (value === null || value === undefined || value === '') return ''
  const date = props.type === 'time' ? parsePickerDate(`2000-01-01T${value}`) : parsePickerDate(value)
  return formatPickerDate(date, part === 'time' ? 'HH:mm' + (showSeconds.value ? ':ss' : '') : props.type === 'month' ? 'YYYY年MM月' : props.format?.split(/[ T]HH/)[0] || 'YYYY-MM-DD')
}
function fill(date: Date) {
  year.value = date.getFullYear(); month.value = date.getMonth() + 1; day.value = date.getDate()
  hour.value = date.getHours(); minute.value = Math.floor(date.getMinutes() / minuteStep.value) * minuteStep.value; second.value = date.getSeconds()
}
function open(index = 0, part: 'date' | 'time' = 'date') {
  if (props.disabled) return
  if (!isMobile.value && props.type !== 'time') { desktopPicker.value?.handleOpen(); return }
  rangeIndex.value = index; mode.value = props.type === 'time' ? 'time' : part
  const value = raw(index) || (isRange.value ? raw(1 - index) : undefined)
  let date = props.type === 'time' && value ? parsePickerDate(`2000-01-01T${value}`) : parsePickerDate(value)
  if (props.min && date < parsePickerDate(props.min)) date = parsePickerDate(props.min)
  if (props.max && date > parsePickerDate(props.max)) date = parsePickerDate(props.max)
  fill(date); visible.value = true
}
function disabledDesktopDate(date: Date) {
  const day = formatPickerDate(date, 'YYYY-MM-DD')
  return Boolean(props.disabledDate?.(date)
    || props.min && day < formatPickerDate(parsePickerDate(props.min), 'YYYY-MM-DD')
    || props.max && day > formatPickerDate(parsePickerDate(props.max), 'YYYY-MM-DD'))
}
const validationMessage = computed(() => {
  const date = candidate.value
  if (props.min && date < parsePickerDate(props.min)) return '不能早于允许的开始日期'
  if (props.max && date > parsePickerDate(props.max)) return '不能晚于允许的结束日期'
  if (props.disabledDate?.(new Date(year.value, month.value - 1, day.value))) return '该日期不可选择'
  if (props.type === 'time') {
    const time = formatPickerDate(date, 'HH:mm')
    if ((props.start && time < props.start) || (props.end && time > props.end)) return '请选择允许范围内的时间'
  }
  const other = raw(1 - rangeIndex.value)
  if (isRange.value && other && (rangeIndex.value === 0 ? date > parsePickerDate(other) : date < parsePickerDate(other))) return '结束日期不能早于开始日期'
  return ''
})
function publish(value: unknown) {
  emit('update:modelValue', value); emit('change', value)
  void formItem?.validate('change').catch(() => undefined)
}
function confirm() {
  if (validationMessage.value) return
  const date = candidate.value
  const value = props.type === 'time' ? formatPickerDate(date, 'HH:mm') : props.valueFormat ? formatPickerDate(date, props.valueFormat) : new Date(date)
  if (isRange.value) {
    const values = Array.isArray(props.modelValue) ? [...props.modelValue] : [null, null]
    values[rangeIndex.value] = value
    // Range consumers expect two dates; the first selection starts a one-day range.
    if (!values[1 - rangeIndex.value]) values[1 - rangeIndex.value] = value instanceof Date ? new Date(value) : value
    publish(values)
  } else publish(value)
  visible.value = false
}
function clear() { publish(isRange.value || !props.valueFormat && props.type !== 'time' ? null : '') }
function applyShortcut(shortcut: Shortcut) { fill(typeof shortcut.value === 'function' ? shortcut.value() : shortcut.value) }
defineExpose({ open, focus: () => !isMobile.value && props.type !== 'time' ? desktopPicker.value?.focus() : trigger.value?.focus() })
</script>
<style scoped>
.unified-date-picker { width: 100%; }
.picker-trigger { display: flex; min-width: 0; min-height: 44px; flex: 1; align-items: center; justify-content: center; border: 1px solid var(--ts-color-border, var(--el-border-color)); border-radius: 10px; padding: 8px 10px; background: var(--ts-color-surface); color: var(--ts-color-text); font-size: 14px; font-variant-numeric: tabular-nums; }
.picker-trigger:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 2px; }
.picker-trigger:disabled { opacity: .5; cursor: not-allowed; }
</style>
