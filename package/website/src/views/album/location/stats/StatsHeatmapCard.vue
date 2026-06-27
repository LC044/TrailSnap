<template>
  <div class="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
    <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">旅行日历热力图</h2>
    <div v-if="loading" class="h-40 flex items-center justify-center">
      <el-skeleton-item variant="rect" style="width: 100%; height: 80px" animated />
    </div>
    <div v-else-if="error" class="flex flex-col items-center gap-2 py-8 text-gray-400 dark:text-gray-500">
      <span class="text-sm">统计加载失败</span>
      <button @click="$emit('retry')" class="text-sm text-primary-500 hover:text-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none rounded">重试</button>
    </div>
    <div v-else-if="!data.length" class="py-8 text-center text-gray-400 dark:text-gray-500 text-sm">暂无数据</div>
    <div v-else class="flex gap-2 text-xs overflow-x-auto">
      <!-- weekday labels -->
      <div class="flex flex-col gap-[2px] pt-5 flex-shrink-0">
        <div class="h-3 leading-3 text-gray-400 dark:text-gray-500"></div>
        <div class="h-3 leading-3 text-gray-400 dark:text-gray-500">一</div>
        <div class="h-3 leading-3"></div>
        <div class="h-3 leading-3 text-gray-400 dark:text-gray-500">三</div>
        <div class="h-3 leading-3"></div>
        <div class="h-3 leading-3 text-gray-400 dark:text-gray-500">五</div>
        <div class="h-3 leading-3"></div>
      </div>
      <div class="flex-1 min-w-0">
        <!-- month labels -->
        <div class="flex gap-[2px] h-4 mb-1">
          <div v-for="w in weeks" :key="w.key" class="w-3 flex-shrink-0 text-gray-400 dark:text-gray-500 leading-4">
            <span v-if="w.monthLabel">{{ w.monthLabel }}</span>
          </div>
        </div>
        <!-- weeks -->
        <div class="flex gap-[2px]">
          <div v-for="w in weeks" :key="w.key" class="flex flex-col gap-[2px] flex-shrink-0">
            <template v-for="(day, i) in w.days" :key="i">
              <button
                v-if="day.count > 0"
                @click="$emit('narrow-range', day.date, day.date)"
                class="w-3 h-3 rounded-sm border-0 p-0 cursor-pointer hover:ring-1 hover:ring-primary-500 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
                :style="cellStyle(day.count)"
                :title="`${day.date} · ${day.count} 张照片`"
              ></button>
              <div v-else class="w-3 h-3 rounded-sm bg-gray-100 dark:bg-gray-700" :title="`${day.date} · 无照片`"></div>
            </template>
          </div>
        </div>
        <!-- legend -->
        <div class="flex items-center gap-1 mt-3 text-gray-400 dark:text-gray-500">
          <span>少</span>
          <div class="w-3 h-3 rounded-sm bg-gray-100 dark:bg-gray-700"></div>
          <div v-for="a in [0.4, 0.65, 0.9]" :key="a" class="w-3 h-3 rounded-sm" :style="{ backgroundColor: `rgba(${rgb}, ${a})` }"></div>
          <span>多</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { injectTheme } from '@/composables/useTheme';
import type { HeatmapItem } from '@/api/location';

const props = defineProps<{ data: HeatmapItem[]; loading: boolean; error: boolean }>();
defineEmits<{ (e: 'narrow-range', start: string, end: string): void; (e: 'retry'): void }>();

const { currentTheme } = injectTheme();
const rgb = computed(() => currentTheme.value.rgb);

interface Day { date: string; count: number }
interface Week { key: string; days: Day[]; monthLabel: string }

function fmt(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

const weeks = computed<Week[]>(() => {
  if (!props.data.length) return [];
  const countMap = new Map(props.data.map(d => [d.date, d.count]));
  const sorted = [...props.data].map(d => d.date).sort();
  const minD = new Date(sorted[0]);
  const maxD = new Date(sorted[sorted.length - 1]);
  const start = new Date(minD);
  start.setDate(minD.getDate() - minD.getDay());
  const end = new Date(maxD);
  end.setDate(maxD.getDate() + (6 - maxD.getDay()));

  const out: Week[] = [];
  let lastMonth = -1;
  const cur = new Date(start);
  while (cur <= end) {
    const days: Day[] = [];
    let monthLabel = '';
    if (cur.getMonth() !== lastMonth) {
      monthLabel = `${cur.getMonth() + 1}月`;
      lastMonth = cur.getMonth();
    }
    for (let i = 0; i < 7; i++) {
      const ds = fmt(cur);
      days.push({ date: ds, count: countMap.get(ds) || 0 });
      cur.setDate(cur.getDate() + 1);
    }
    out.push({ key: days[0].date, days, monthLabel });
  }
  return out;
});

function cellStyle(count: number) {
  let alpha = 0.4;
  if (count >= 20) alpha = 0.9;
  else if (count >= 6) alpha = 0.65;
  return { backgroundColor: `rgba(${currentTheme.value.rgb}, ${alpha})` };
}
</script>
