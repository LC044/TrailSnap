<template>
  <SurfaceCard padding="lg" :elevated="false" class="flex flex-col">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div><h2 class="stats-title">足迹随时间变化</h2><p class="stats-caption mt-1">有拍摄日期的全部照片 · {{ grain === 'year' ? '逐年记录' : `${year} 年逐月记录` }}</p></div>
      <div class="stats-tabs" aria-label="时间粒度">
        <button :aria-pressed="grain === 'year'" @click="grain = 'year'">按年</button>
        <button :aria-pressed="grain === 'month'" @click="grain = 'month'">按月</button>
      </div>
    </div>
    <div class="flex flex-wrap items-center justify-between gap-3 mt-5">
      <div class="stats-tabs" aria-label="统计指标">
        <button :aria-pressed="metric === 'photos'" @click="metric = 'photos'">照片数</button>
        <button :aria-pressed="metric === 'days'" @click="metric = 'days'">记录天数</button>
      </div>
      <select v-if="grain === 'month' && years.length" v-model.number="year" class="ts-input text-xs" aria-label="趋势年份">
        <option v-for="y in years" :key="y" :value="y">{{ y }} 年</option>
      </select>
    </div>
    <div v-if="loading" class="stats-empty"><el-skeleton-item variant="rect" style="width:100%;height:260px" /></div>
    <div v-else-if="error" class="stats-empty"><span>时间统计加载失败</span><button class="text-primary-500" @click="$emit('retry')">重试</button></div>
    <div v-else-if="!data.length" class="stats-empty">这段时间还没有拍摄记录</div>
    <template v-else>
      <p class="text-sm mt-5"><strong>{{ peak?.label }}{{ grain === 'year' ? ' 年' : '' }}</strong><span class="ts-muted">留下最多{{ metric === 'photos' ? '照片' : '记录' }}，共 </span><strong>{{ peak?.[metric].toLocaleString() }} {{ unit }}</strong></p>
      <div ref="chartEl" class="w-full h-72 min-h-[18rem] flex-1 mt-2" role="img" :aria-label="`${grain === 'year' ? '年度' : '月度'}${metric === 'photos' ? '照片数' : '记录天数'}柱状图`"></div>
      <div class="flex flex-wrap items-center gap-2 mt-3">
        <select v-model="selected" class="ts-input text-xs flex-1" aria-label="查看时间段">
          <option v-for="b in buckets.filter(b => b.photos > 0)" :key="b.start" :value="b.start">{{ grain === 'month' ? `${year} 年 ` : '' }}{{ b.label }} · {{ b[metric].toLocaleString() }} {{ unit }}</option>
        </select>
        <button class="ts-button ts-button-secondary ts-button-sm" @click="openSelected">查看照片</button>
        <button class="ts-icon-button ts-button-sm ts-button-ghost" aria-label="下载趋势图" @click="downloadPng"><Download class="w-4 h-4" /></button>
      </div>
      <p class="stats-caption mt-3">点击柱状图查看照片{{ buckets.length > 12 ? '；拖动图下滑块查看较早年份' : '' }}。无记录的时间段显示为 0。</p>
    </template>
  </SurfaceCard>
</template>
<script setup lang="ts">
import { computed, ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { useResizeObserver } from '@vueuse/core'
import { Download } from 'lucide-vue-next'
import SurfaceCard from '@/components/ui/SurfaceCard.vue'
import { echarts } from '@/utils/echarts'
import { injectTheme } from '@/composables/useTheme'
import { statsYears, timeBuckets, type TimeBucket } from '@/utils/locationStats'
import type { HeatmapItem } from '@/api/location'
const props = defineProps<{ data: HeatmapItem[]; loading: boolean; error: boolean }>()
const emit = defineEmits<{ (e: 'narrow-range', start: string, end: string, year?: number): void; (e: 'retry'): void }>()
const { currentTheme, isDarkMode } = injectTheme()
const grain = ref<'year' | 'month'>('year')
const metric = ref<'photos' | 'days'>('photos')
const years = computed(() => statsYears(props.data))
const year = ref(new Date().getFullYear())
watch(years, value => { if (!value.includes(year.value)) year.value = value[0] ?? new Date().getFullYear() }, { immediate: true })
const buckets = computed(() => timeBuckets(props.data, grain.value, year.value))
const unit = computed(() => metric.value === 'photos' ? '张' : '天')
const peak = computed(() => buckets.value.reduce<TimeBucket | undefined>((best, b) => !best || b[metric.value] > best[metric.value] ? b : best, undefined))
const selected = ref('')
watch(buckets, value => { selected.value = [...value].reverse().find(b => b.photos > 0)?.start ?? '' }, { immediate: true })
function openBucket(b?: TimeBucket) { if (b?.photos) emit('narrow-range', b.start, b.end, grain.value === 'year' ? Number(b.start.slice(0, 4)) : undefined) }
function openSelected() { openBucket(buckets.value.find(b => b.start === selected.value)) }
const chartEl = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null
function dispose() { chart?.dispose(); chart = null }
function render() {
  if (!chartEl.value || props.loading || props.error || !props.data.length) { dispose(); return }
  if (!chart || chart.getDom() !== chartEl.value) {
    dispose()
    chart = echarts.init(chartEl.value)
    chart.on('click', (params: any) => { if (params.componentType === 'series') openBucket(buckets.value[params.dataIndex]) })
  }
  const style = getComputedStyle(chartEl.value)
  const text = style.getPropertyValue('--ts-color-text-secondary').trim()
  const border = style.getPropertyValue('--ts-color-divider').trim()
  chart.setOption({
    animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (value: number) => `${value.toLocaleString()} ${unit.value}` },
    grid: { left: 12, right: 12, top: 30, bottom: buckets.value.length > 12 ? 60 : 28, outerBoundsMode: 'same', outerBoundsContain: 'axisLabel' },
    xAxis: { type: 'category', data: buckets.value.map(b => b.label), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: text } },
    yAxis: { type: 'value', minInterval: 1, name: metric.value === 'photos' ? '照片 / 张' : '记录 / 天', nameTextStyle: { color: text }, axisLabel: { color: text }, splitLine: { lineStyle: { color: border, type: 'dashed' } } },
    dataZoom: buckets.value.length > 12 ? [{ type: 'slider', startValue: Math.max(0, buckets.value.length - 10), endValue: buckets.value.length - 1, bottom: 0, height: 20, borderColor: border, textStyle: { color: text }, fillerColor: `rgba(${currentTheme.value.rgb}, .15)`, handleStyle: { color: currentTheme.value.primary } }] : [],
    series: [{ name: metric.value === 'photos' ? '照片数' : '记录天数', type: 'bar', barMaxWidth: 36, data: buckets.value.map(b => b[metric.value]), itemStyle: { color: currentTheme.value.primary, borderRadius: [5, 5, 0, 0] } }],
  }, true)
}
watch([chartEl, buckets, metric, () => props.loading, () => props.error, currentTheme, isDarkMode], () => nextTick(render), { deep: true })
useResizeObserver(chartEl, () => chart?.resize())
function downloadPng() {
  if (!chart) return
  const a = document.createElement('a')
  a.href = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: getComputedStyle(chartEl.value!).getPropertyValue('--ts-color-surface').trim() })
  a.download = '足迹时间趋势.png'; a.click()
}
onBeforeUnmount(dispose)
</script>
