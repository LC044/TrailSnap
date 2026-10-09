<template>
  <div class="min-w-0 flex-1">
    <p class="mb-2 text-center text-xs text-gray-500 dark:text-gray-400">{{ label }}</p>
    <div class="relative">
      <div class="pointer-events-none absolute inset-x-0 top-[88px] h-11 rounded-lg bg-primary-50 dark:bg-primary-900/30" />
      <div ref="wheel" class="date-wheel relative h-[220px] overflow-y-auto overscroll-contain"
        role="listbox" :aria-label="label" :aria-activedescendant="`${id}-${modelValue}`" tabindex="0"
        @scroll="onScroll" @keydown="onKeydown">
        <div class="h-[88px]" aria-hidden="true" />
        <div v-for="value in options" :id="`${id}-${value}`" :key="value" role="option"
          :aria-selected="value === modelValue" class="flex h-11 cursor-pointer snap-center items-center justify-center text-lg tabular-nums"
          :class="value === modelValue ? 'font-semibold text-primary-600 dark:text-primary-400' : 'text-gray-400 dark:text-gray-500'"
          @click="select(value)">{{ String(value).padStart(label === '年' ? 4 : 2, '0') }}</div>
        <div class="h-[88px]" aria-hidden="true" />
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch, useId } from 'vue'
const props = defineProps<{ modelValue: number; options: number[]; label: string }>()
const emit = defineEmits<{ 'update:modelValue': [number] }>()
const id = useId(), wheel = ref<HTMLElement | null>(null)
let scrolling = false, timer: ReturnType<typeof setTimeout> | undefined
const align = () => {
  if (wheel.value) wheel.value.scrollTop = Math.max(0, props.options.indexOf(props.modelValue)) * 44
}
function onScroll() {
  scrolling = true
  const index = Math.max(0, Math.min(props.options.length - 1, Math.round((wheel.value?.scrollTop || 0) / 44)))
  const value = props.options[index]
  if (value !== undefined && value !== props.modelValue) emit('update:modelValue', value)
  clearTimeout(timer)
  timer = setTimeout(() => { scrolling = false; align() }, 160)
}
function select(value: number) {
  scrolling = false
  emit('update:modelValue', value)
  void nextTick(align)
}
function onKeydown(event: KeyboardEvent) {
  const delta = event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : event.key === 'PageDown' ? 10 : event.key === 'PageUp' ? -10 : 0
  if (!delta && event.key !== 'Home' && event.key !== 'End') return
  event.preventDefault()
  const index = event.key === 'Home' ? 0 : event.key === 'End' ? props.options.length - 1 : Math.max(0, Math.min(props.options.length - 1, props.options.indexOf(props.modelValue) + delta))
  select(props.options[index]!)
}
watch(() => props.modelValue, () => { if (!scrolling) void nextTick(align) })
watch(() => props.options, () => { scrolling = false; void nextTick(align) })
onMounted(align)
onBeforeUnmount(() => clearTimeout(timer))
</script>
<style scoped>
.date-wheel { scrollbar-width: none; scroll-snap-type: y mandatory; touch-action: pan-y; }
.date-wheel::-webkit-scrollbar { display: none; }
.date-wheel:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 2px; border-radius: 8px; }
</style>
