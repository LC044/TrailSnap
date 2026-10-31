<template>
  <SurfaceCard padding="lg" :elevated="false">
    <div class="flex flex-wrap items-center justify-between gap-3 mb-5">
      <div><h2 class="stats-title">拍摄日历</h2><p class="stats-caption mt-1">{{ year }} 年 · {{ yearDays.length.toLocaleString() }} 个记录日 · {{ total.toLocaleString() }} 张照片</p></div>
      <select v-if="years.length" v-model.number="year" class="ts-input text-xs" aria-label="日历年份"><option v-for="y in years" :key="y" :value="y">{{ y }} 年</option></select>
    </div>
    <div v-if="loading" class="stats-empty"><el-skeleton-item variant="rect" style="width:100%;height:100px" /></div>
    <div v-else-if="error" class="stats-empty"><span>拍摄日历加载失败</span><button class="text-primary-500" @click="$emit('retry')">重试</button></div>
    <div v-else-if="!data.length" class="stats-empty">这段时间还没有拍摄记录</div>
    <template v-else>
      <div class="calendar-scroll overflow-x-auto pb-2" tabindex="0" aria-label="拍摄日历，可横向滚动">
        <div class="calendar-grid">
          <div class="calendar-week text-xs ts-muted pt-6"><span v-for="d in ['日', '一', '二', '三', '四', '五', '六']" :key="d">{{ d }}</span></div>
          <div v-for="w in weeks" :key="w.key" class="min-w-0">
            <div class="h-6 text-xs ts-muted whitespace-nowrap">{{ w.month }}</div>
            <div class="calendar-week">
              <template v-for="day in w.days" :key="day.date">
                <div v-if="day.outside" class="calendar-cell invisible"></div>
                <button v-else-if="day.count > 0" class="calendar-cell hover:ring-2 hover:ring-primary-500" :style="cellStyle(day.count)" :aria-label="`${day.date} · ${day.count} 张照片，查看照片`" :title="`${day.date} · ${day.count} 张照片`" @click="$emit('narrow-range', day.date, day.date)"></button>
                <div v-else class="calendar-cell" :title="`${day.date} · 无照片`"></div>
              </template>
            </div>
          </div>
        </div>
      </div>
      <div class="flex flex-wrap justify-between gap-3 mt-3 stats-caption"><span>颜色表示当天照片数，点击有记录的日期查看照片</span><div class="flex items-center gap-1.5"><span>0</span><i class="legend-cell"></i><i v-for="n in [1, 6, 20]" :key="n" class="legend-cell" :style="cellStyle(n)"></i><span>20+ 张</span></div></div>
    </template>
  </SurfaceCard>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import SurfaceCard from '@/components/ui/SurfaceCard.vue'
import { injectTheme } from '@/composables/useTheme'
import { calendarWeeks, statsYears } from '@/utils/locationStats'
import type { HeatmapItem } from '@/api/location'
const props = defineProps<{ data: HeatmapItem[]; loading: boolean; error: boolean }>()
defineEmits<{ (e: 'narrow-range', start: string, end: string): void; (e: 'retry'): void }>()
const { currentTheme } = injectTheme()
const years = computed(() => statsYears(props.data))
const year = ref(new Date().getFullYear())
watch(years, value => { if (!value.includes(year.value)) year.value = value[0] ?? new Date().getFullYear() }, { immediate: true })
const yearDays = computed(() => props.data.filter(d => Number(d.date.slice(0, 4)) === year.value && d.count > 0))
const total = computed(() => yearDays.value.reduce((sum, d) => sum + d.count, 0))
const weeks = computed(() => calendarWeeks(props.data, year.value))
function cellStyle(count: number) { return { backgroundColor: `rgba(${currentTheme.value.rgb}, ${count >= 20 ? .95 : count >= 6 ? .65 : .3})` } }
</script>
<style scoped>
.calendar-grid { display: flex; gap: 4px; min-width: 760px; }
.calendar-grid > div { flex: 1; }
.calendar-grid > div:first-child { flex: 0 0 20px; }
.calendar-week { display: grid; grid-template-rows: repeat(7, 13px); gap: 4px; }
.calendar-week > span { line-height: 13px; }
.calendar-cell { width: 100%; height: 13px; border-radius: 3px; background: var(--ts-color-surface-muted); }
.legend-cell { width: 12px; height: 12px; border-radius: 3px; background: var(--ts-color-surface-muted); }
</style>
