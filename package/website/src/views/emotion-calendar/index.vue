<template>
  <div class="w-full max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
      <div>
        <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">情绪色彩日历</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {{ selectedYear ? `${selectedYear} 年` : '过去一年' }}共拍摄
          <span class="font-semibold text-gray-700 dark:text-gray-200">{{ data?.total_photos || 0 }}</span>
          张照片，
          覆盖
          <span class="font-semibold text-gray-700 dark:text-gray-200">{{ data?.total_days || 0 }}</span>
          天
        </p>
      </div>
      <div class="flex items-center gap-3">
        <!-- Legend -->
        <div class="hidden sm:flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          <span>情绪:</span>
          <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-sm bg-orange-400"></span>温暖</span>
          <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-sm bg-blue-400"></span>清冷</span>
          <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-sm bg-fuchsia-500"></span>鲜活</span>
          <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-sm bg-gray-400"></span>平淡</span>
        </div>
        <el-select v-model="selectedYear" size="default" class="w-28" @change="fetchData" placeholder="过去一年">
          <el-option label="过去一年" :value="undefined" />
          <el-option v-for="year in availableYears" :key="year" :label="`${year}年`" :value="year" />
        </el-select>
      </div>
    </div>

    <!-- Mobile Legend -->
    <div class="flex sm:hidden items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mb-4">
      <span>情绪:</span>
      <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-sm bg-orange-400"></span>温暖</span>
      <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-sm bg-blue-400"></span>清冷</span>
      <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-sm bg-fuchsia-500"></span>鲜活</span>
      <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-sm bg-gray-400"></span>平淡</span>
    </div>

    <!-- Calendar Grid -->
    <div class="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-4 sm:p-6">
      <!-- Weekday headers -->
      <div class="flex gap-[2px] sm:gap-[3px] mb-2">
        <div class="flex-1 text-center text-[10px] sm:text-xs text-gray-400 dark:text-gray-500">日</div>
        <div class="flex-1 text-center text-[10px] sm:text-xs text-gray-400 dark:text-gray-500">一</div>
        <div class="flex-1 text-center text-[10px] sm:text-xs text-gray-400 dark:text-gray-500">二</div>
        <div class="flex-1 text-center text-[10px] sm:text-xs text-gray-400 dark:text-gray-500">三</div>
        <div class="flex-1 text-center text-[10px] sm:text-xs text-gray-400 dark:text-gray-500">四</div>
        <div class="flex-1 text-center text-[10px] sm:text-xs text-gray-400 dark:text-gray-500">五</div>
        <div class="flex-1 text-center text-[10px] sm:text-xs text-gray-400 dark:text-gray-500">六</div>
      </div>

      <!-- Heatmap Grid -->
      <div class="overflow-x-auto pb-6 scrollbar-thin scrollbar-thumb-gray-200 dark:scrollbar-thumb-gray-700" ref="scrollContainer">
        <div class="flex gap-[2px] sm:gap-[3px] xl:gap-[4px] w-full min-w-[600px]">
          <div v-for="(col, colIndex) in gridColumns" :key="colIndex" class="flex-1 flex flex-col gap-[2px] sm:gap-[3px] xl:gap-[4px] relative">
            <template v-for="(day, rowIndex) in col" :key="`${colIndex}-${rowIndex}`">
              <el-tooltip
                v-if="day.count !== -1"
                placement="top"
                effect="dark"
                :show-after="100"
              >
                <template #content>
                  <div class="text-center">
                    <div class="font-medium">{{ day.displayDate }}</div>
                    <div v-if="day.count > 0" class="text-xs mt-1">
                      <div>{{ day.count }} 张照片</div>
                      <div v-if="day.emotionHint" class="mt-0.5">
                        <span :class="getEmotionTextClass(day.emotionHint)">{{ getEmotionLabel(day.emotionHint) }}</span>
                        <span v-if="day.categories.length" class="ml-1">· {{ day.categories.join(' · ') }}</span>
                      </div>
                      <div v-if="day.dominantColor" class="mt-0.5 flex items-center justify-center gap-1">
                        <span class="inline-block w-2.5 h-2.5 rounded-full border border-white/30" :style="{ backgroundColor: day.dominantColor }"></span>
                        <span>{{ day.dominantColor }}</span>
                      </div>
                    </div>
                    <div v-else class="text-xs text-gray-400 mt-1">无照片</div>
                  </div>
                </template>
                <div
                  class="w-full aspect-square rounded-[2px] sm:rounded-[3px] cursor-pointer transition-all hover:ring-1 hover:ring-gray-400 dark:hover:ring-gray-500"
                  :class="day.count === 0 ? 'bg-slate-100 dark:bg-slate-800/50' : ''"
                  :style="day.count > 0 ? getCellStyle(day) : {}"
                  @click="day.count > 0 ? handleDayClick(day) : undefined"
                >
                </div>
              </el-tooltip>
              <div v-else class="w-full aspect-square bg-transparent"></div>
            </template>

            <!-- Month labels -->
            <div v-if="monthLabelMap[colIndex]" class="absolute -bottom-5 left-0 text-[10px] sm:text-[12px] text-gray-400 whitespace-nowrap">
              {{ monthLabelMap[colIndex] }}
            </div>
          </div>
        </div>
      </div>

      <!-- Month labels spacing -->
      <div class="h-6"></div>
    </div>

    <!-- Day Detail Panel -->
    <div v-if="selectedDay" class="mt-4 bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-4 sm:p-6">
      <div class="flex justify-between items-center mb-3">
        <div>
          <h3 class="text-lg font-semibold text-gray-800 dark:text-gray-100">{{ selectedDay.displayDate }}</h3>
          <p class="text-sm text-gray-500 dark:text-gray-400">
            {{ selectedDay.count }} 张照片
            <span v-if="selectedDay.emotionHint" class="ml-2">
              <span :class="getEmotionTextClass(selectedDay.emotionHint)">{{ getEmotionLabel(selectedDay.emotionHint) }}</span>
            </span>
          </p>
        </div>
        <div class="flex items-center gap-3">
          <div v-if="selectedDay.dominantColor" class="flex items-center gap-1.5">
            <span class="w-6 h-6 rounded-md border border-slate-200 dark:border-slate-600" :style="{ backgroundColor: selectedDay.dominantColor }"></span>
            <span class="text-sm text-gray-600 dark:text-gray-300">{{ selectedDay.dominantColor }}</span>
          </div>
          <button
            @click="viewDayPhotos"
            class="px-4 py-1.5 text-sm bg-primary-600 hover:bg-primary-700 text-white rounded-lg transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            查看照片
          </button>
        </div>
      </div>
      <div v-if="selectedDay.categories.length" class="flex gap-2">
        <span
          v-for="cat in selectedDay.categories"
          :key="cat"
          class="px-2 py-0.5 text-xs rounded-full bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
        >{{ cat }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { dashboardApi, type EmotionCalendarResponse } from '@/api/dashboard';
import { format, subDays, startOfYear, endOfYear, eachDayOfInterval, getDay } from 'date-fns';
import { ElMessage } from 'element-plus';

const router = useRouter();
const selectedYear = ref<number | undefined>(undefined);
const data = ref<EmotionCalendarResponse | null>(null);
const availableYears = ref<number[]>([]);
const scrollContainer = ref<HTMLElement | null>(null);
const selectedDay = ref<{
  date: string;
  displayDate: string;
  count: number;
  dominantColor: string | null;
  brightness: number | null;
  saturation: number | null;
  categories: string[];
  emotionHint: string | null;
} | null>(null);

interface GridDay {
  date: string;
  displayDate: string;
  count: number;
  dominantColor: string | null;
  brightness: number | null;
  saturation: number | null;
  categories: string[];
  emotionHint: string | null;
}

const gridColumns = ref<GridDay[][]>([]);
const monthLabels = ref<{ text: string; index: number }[]>([]);

const monthLabelMap = computed(() => {
  const map: Record<number, string> = {};
  monthLabels.value.forEach(label => {
    map[label.index] = label.text;
  });
  return map;
});

const getEmotionLabel = (hint: string | null): string => {
  const map: Record<string, string> = {
    warm: '温暖',
    cool: '清冷',
    vibrant: '鲜活',
    muted: '平淡',
    neutral: '日常',
  };
  return hint ? (map[hint] || hint) : '日常';
};

const getEmotionTextClass = (hint: string | null): string => {
  const map: Record<string, string> = {
    warm: 'text-orange-400',
    cool: 'text-blue-400',
    vibrant: 'text-fuchsia-400',
    muted: 'text-gray-400',
    neutral: 'text-gray-300',
  };
  return hint ? (map[hint] || 'text-gray-300') : 'text-gray-300';
};

/**
 * Get the cell background style based on emotion data.
 * If dominant_color exists, use it as base; otherwise fall back to a neutral color.
 * Adjust opacity/saturation based on photo count for visual density.
 */
const getCellStyle = (day: GridDay): Record<string, string> => {
  if (day.count === 0) return {};

  let bgColor: string;

  if (day.dominantColor) {
    // Use the dominant color directly with some opacity control
    const opacity = Math.min(0.4 + day.count * 0.06, 1.0);
    bgColor = day.dominantColor;

    // Parse hex to rgba for opacity control
    const r = parseInt(bgColor.slice(1, 3), 16);
    const g = parseInt(bgColor.slice(3, 5), 16);
    const b = parseInt(bgColor.slice(5, 7), 16);
    return { backgroundColor: `rgba(${r}, ${g}, ${b}, ${opacity})` };
  }

  // Fallback: derive color from emotion hint
  const emotionColors: Record<string, string> = {
    warm: 'rgba(251, 146, 60, 0.6)',   // orange-400
    cool: 'rgba(96, 165, 250, 0.6)',    // blue-400
    vibrant: 'rgba(217, 70, 239, 0.6)', // fuchsia-500
    muted: 'rgba(156, 163, 175, 0.4)',  // gray-400
    neutral: 'rgba(148, 163, 184, 0.4)', // slate-400
  };

  bgColor = day.emotionHint ? (emotionColors[day.emotionHint] || emotionColors.neutral) : emotionColors.neutral;

  // Adjust opacity by count
  if (day.count > 0) {
    const baseOpacity = 0.3;
    const maxOpacity = 0.9;
    const opacity = Math.min(baseOpacity + day.count * 0.04, maxOpacity);
    // Reconstruct with new opacity
    const match = bgColor.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (match) {
      return { backgroundColor: `rgba(${match[1]}, ${match[2]}, ${match[3]}, ${opacity})` };
    }
  }

  return { backgroundColor: bgColor };
};

const buildGrid = (calendarData: EmotionCalendarResponse['data']) => {
  const dataMap = calendarData.reduce((acc, item) => {
    acc[item.date] = item;
    return acc;
  }, {} as Record<string, EmotionCalendarResponse['data'][0]>);

  const today = new Date();
  let startDate: Date;
  let endDate: Date;

  if (selectedYear.value) {
    startDate = startOfYear(new Date(selectedYear.value, 0, 1));
    endDate = endOfYear(new Date(selectedYear.value, 0, 1));
  } else {
    endDate = today;
    startDate = subDays(today, 364);
  }

  const days = eachDayOfInterval({ start: startDate, end: endDate });
  const firstDayOfWeek = getDay(startDate);

  const paddedDays: (Date | null)[] = Array(firstDayOfWeek).fill(null).concat(days);

  const columns: GridDay[][] = [];
  const labels: { text: string; index: number }[] = [];
  let currentMonth = -1;

  for (let i = 0; i < paddedDays.length; i += 7) {
    const colDays = paddedDays.slice(i, i + 7);
    while (colDays.length < 7) {
      colDays.push(null);
    }

    columns.push(colDays.map(date => {
      if (!date) return { date: '', displayDate: '', count: -1, dominantColor: null, brightness: null, saturation: null, categories: [], emotionHint: null };
      const dateStr = format(date, 'yyyy-MM-dd');
      const displayDateStr = format(date, 'yyyy年M月d日');
      const item = dataMap[dateStr];
      return {
        date: dateStr,
        displayDate: displayDateStr,
        count: item?.photo_count || 0,
        dominantColor: item?.dominant_color || null,
        brightness: item?.brightness || null,
        saturation: item?.saturation || null,
        categories: item?.top_categories || [],
        emotionHint: item?.emotion_hint || null,
      };
    }));

    const firstValidDay = colDays.find(d => d !== null);
    if (firstValidDay) {
      const month = firstValidDay.getMonth();
      if (month !== currentMonth) {
        labels.push({ text: `${month + 1}月`, index: columns.length - 1 });
        currentMonth = month;
      }
    }
  }

  gridColumns.value = columns;
  monthLabels.value = labels;

  if (!selectedYear.value || selectedYear.value === today.getFullYear()) {
    nextTick(() => {
      if (scrollContainer.value) {
        scrollContainer.value.scrollLeft = scrollContainer.value.scrollWidth;
      }
    });
  }
};

const fetchData = async () => {
  try {
    const res = await dashboardApi.getEmotionCalendar(selectedYear.value || undefined);
    data.value = res;
    if (res.available_years) {
      availableYears.value = res.available_years;
    }
    buildGrid(res.data);
    selectedDay.value = null;
  } catch (error) {
    console.error('Failed to fetch emotion calendar data:', error);
    ElMessage.error('加载情绪日历失败');
  }
};

const handleDayClick = (day: GridDay) => {
  selectedDay.value = day;
};

const viewDayPhotos = () => {
  if (selectedDay.value) {
    // Navigate to search with the date as query - this is the most reliable way
    // to find photos from a specific date in the current system
    const dateDisplay = selectedDay.value.date; // yyyy-MM-dd format
    router.push({ path: '/search', query: { q: dateDisplay } });
  }
};

onMounted(() => {
  fetchData();
});
</script>

<style scoped>
.scrollbar-thin::-webkit-scrollbar {
  height: 6px;
}

.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}

.scrollbar-thin::-webkit-scrollbar-thumb {
  background-color: #cbd5e1;
  border-radius: 4px;
}

.dark .scrollbar-thin::-webkit-scrollbar-thumb {
  background-color: #475569;
}
</style>
