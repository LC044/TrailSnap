<template><div ref="container" class="footprint-trend" role="img" :aria-label="description" /></template>
<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { init, use, type EChartsType } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { injectTheme } from '@/composables/useTheme'
import type { FootprintData } from '@/types/footprint'
use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])
const props = defineProps<{ items: FootprintData['timeline']; year: number | null }>()
const emit = defineEmits<{ select: [year: number] }>()
const { currentTheme } = injectTheme()
const container = ref<HTMLElement>()
const description = computed(() => props.items.map(item => `${item.year}年 ${item.photo_count} 张照片`).join('，'))
let chart: EChartsType | undefined
let observer: ResizeObserver | undefined
function render() {
  chart?.setOption({
    animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    grid: { top: 12, right: 5, bottom: 24, left: 5 },
    tooltip: { trigger: 'axis', confine: true },
    xAxis: { type: 'category', data: props.items.map(item => String(item.year)), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#9ca3af', fontSize: 10 } },
    yAxis: { type: 'value', show: false },
    series: [{ type: 'bar', name: '照片', barMaxWidth: 22, data: props.items.map(item => ({ value: item.photo_count, itemStyle: { color: currentTheme.value.primary, opacity: props.year === null || item.year === props.year ? 1 : .3, borderRadius: [3, 3, 0, 0] } })) }],
  })
}
onMounted(() => {
  if (!container.value) return
  chart = init(container.value)
  chart.on('click', params => emit('select', Number(params.name)))
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(container.value)
  render()
})
watch(() => [props.items, props.year, currentTheme.value.primary], render)
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>
<style scoped>.footprint-trend { width: 100%; height: 118px; }</style>
