<template>
  <div class="emotion-calendar">
    <!-- 头部：标题 + 统计 + 图例 + 筛选 -->
    <div class="ec-header">
      <div class="ec-header-left">
        <div class="ec-title-row">
          <span class="ec-title-text">{{ selectedYear ? `${selectedYear} 年` : '过去一年' }}共拍摄</span>
          <span class="ec-title-num">{{ totalPhotos }}</span>
          <span class="ec-title-text">张照片</span>
          <span class="ec-stats">拍摄{{ totalDays }}天</span>
        </div>
        <div class="ec-legend">
          <span class="ec-legend-item"><span class="ec-legend-dot" style="background-color: var(--ec-warm)"></span>温暖</span>
          <span class="ec-legend-item"><span class="ec-legend-dot" style="background-color: var(--ec-cool)"></span>清冷</span>
          <span v-if="showVibrant" class="ec-legend-item"><span class="ec-legend-dot" style="background-color: var(--ec-vibrant)"></span>鲜活</span>
          <span class="ec-legend-item"><span class="ec-legend-dot" style="background-color: var(--ec-neutral)"></span>日常</span>
          <span class="ec-legend-item"><span class="ec-legend-dot" style="background-color: var(--ec-muted)"></span>平淡</span>
          <span class="ec-legend-item"><span class="ec-legend-dot" style="background-color: var(--ec-empty)"></span>无</span>
        </div>
        <span v-if="reanalysisRemaining > 0" class="ec-refresh-status">正在更新历史照片色彩，剩余 {{ reanalysisRemaining }} 张</span>
      </div>
      <el-select v-model="selectedYear" size="small" class="ec-select" @change="fetchData" placeholder="过去一年">
        <el-option label="过去一年" :value="undefined" />
        <el-option v-for="year in availableYears" :key="year" :label="`${year}年`" :value="year" />
      </el-select>
    </div>

    <!-- 日历色块主体 -->
    <div class="ec-year-view">
      <div class="ec-grid" :style="{ gridTemplateColumns: `repeat(${gridColumns.length}, minmax(0, 1fr))` }">
        <template v-for="(col, colIndex) in gridColumns" :key="colIndex">
          <div class="ec-col">
            <template v-for="(day, rowIndex) in col" :key="`${colIndex}-${rowIndex}`">
              <el-tooltip v-if="day.valid" placement="top" effect="dark" :show-after="120" :offset="4">
                <template #content>
                  <div class="ec-tip">
                    <div class="ec-tip-date">{{ day.displayDate }}</div>
                    <div v-if="day.count > 0" class="ec-tip-info">
                      <span>{{ day.count }} 张照片</span>
                      <span v-if="day.emotionHint" class="ec-tip-emotion">{{ getEmotionLabel(day.emotionHint) }}</span>
                      <span v-if="day.categories.length"> · {{ day.categories.join(' · ') }}</span>
                    </div>
                    <div v-else class="ec-tip-empty">无照片</div>
                  </div>
                </template>
                <div
                  class="ec-cell"
                  :class="{ 'ec-cell-empty': day.count === 0, 'ec-cell-photo': day.count > 0 }"
                  :style="day.count > 0 ? { ...getCellStyle(day), transform: `scale(${getCellScale(day.count)})` } : {}"
                  @click="day.count > 0 ? $router.push({ path: '/search', query: { q: day.date, type: 'date' } }) : undefined"
                ></div>
              </el-tooltip>
              <div v-else class="ec-cell ec-cell-void"></div>
            </template>
            <!-- 月份标签 -->
            <div v-if="monthLabelMap[colIndex]" class="ec-month-label">{{ monthLabelMap[colIndex] }}</div>
          </div>
        </template>
      </div>
    </div>
    <div class="ec-mobile-view">
      <div class="ec-month-nav">
        <button type="button" aria-label="上一个月" :disabled="mobileMonthIndex === 0" @click="changeMobileMonth(-1)">‹</button>
        <select v-model.number="mobileMonthIndex" aria-label="选择月份" @change="mobileSelectedDate = null">
          <option v-for="(month, index) in mobileMonths" :key="month" :value="index">{{ Number(month.slice(0, 4)) }}年{{ Number(month.slice(5, 7)) }}月</option>
        </select>
        <button type="button" aria-label="下一个月" :disabled="mobileMonthIndex >= mobileMonths.length - 1" @click="changeMobileMonth(1)">›</button>
      </div>
      <div class="ec-mobile-grid" role="grid" :aria-label="`${mobileMonthLabel}拍摄日历`">
        <span v-for="weekday in weekdays" :key="weekday" class="ec-weekday">{{ weekday }}</span>
        <template v-for="(day, index) in mobileMonthDays" :key="day?.date || `padding-${index}`">
          <span v-if="!day" />
          <button v-else type="button" class="ec-mobile-day" :class="{ 'ec-mobile-day-selected': mobileSelectedDate === day.date }"
            :aria-label="`${day.displayDate}，${day.count}张照片`" :aria-pressed="mobileSelectedDate === day.date"
            @click="mobileSelectedDate = day.date">
            <span class="ec-mobile-day-number">{{ Number(day.date.slice(-2)) }}</span>
            <span class="ec-mobile-dot" :class="{ 'ec-cell-empty': day.count === 0 }"
              :style="day.count > 0 ? { ...getCellStyle(day), transform: `scale(${getCellScale(day.count)})` } : {}" />
          </button>
        </template>
      </div>
      <div v-if="mobileSelectedDay" class="ec-mobile-detail">
        <span>{{ mobileSelectedDay.displayDate }} · {{ mobileSelectedDay.count }} 张照片<span v-if="mobileSelectedDay.count && mobileSelectedDay.emotionHint"> · {{ getEmotionLabel(mobileSelectedDay.emotionHint) }}</span></span>
        <button v-if="mobileSelectedDay.count" type="button" @click="$router.push({ path: '/search', query: { q: mobileSelectedDay.date, type: 'date' } })">查看照片 ›</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue';
import { dashboardApi, type EmotionCalendarResponse } from '@/api/dashboard';
import { format, subDays, startOfYear, endOfYear, startOfMonth, endOfMonth, eachDayOfInterval, getDay } from 'date-fns';
import { ElMessage } from 'element-plus';

interface GridDay {
  date: string;
  displayDate: string;
  count: number;
  valid: boolean;
  dominantColor: string | null;
  brightness: number | null;
  saturation: number | null;
  categories: string[];
  emotionHint: string | null;
}

const selectedYear = ref<number | undefined>(undefined);
const totalPhotos = ref(0);
const totalDays = ref(0);
const availableYears = ref<number[]>([]);
const reanalysisRemaining = ref(0);
let reanalysisTimer: ReturnType<typeof setTimeout> | null = null;
let active = false;
const vibrantRatio = ref(0);

const gridColumns = ref<GridDay[][]>([]);
const monthLabels = ref<{ text: string; index: number }[]>([]);
const mobileMonths = ref<string[]>([]);
const mobileMonthIndex = ref(0);
const mobileSelectedDate = ref<string | null>(null);
const weekdays = ['日', '一', '二', '三', '四', '五', '六'];

const monthLabelMap = computed<Record<number, string>>(() =>
  Object.fromEntries(monthLabels.value.map(label => [label.index, label.text]))
);
const calendarDayMap = computed<Record<string, GridDay>>(() =>
  Object.fromEntries(gridColumns.value.flat().filter(day => day.valid).map(day => [day.date, day]))
);
const mobileMonthLabel = computed(() => {
  const key = mobileMonths.value[mobileMonthIndex.value];
  return key ? `${Number(key.slice(0, 4))}年${Number(key.slice(5, 7))}月` : '';
});
const mobileMonthDays = computed<(GridDay | null)[]>(() => {
  const key = mobileMonths.value[mobileMonthIndex.value];
  if (!key) return [];
  const first = new Date(Number(key.slice(0, 4)), Number(key.slice(5, 7)) - 1, 1);
  return [
    ...Array(getDay(first)).fill(null),
    ...eachDayOfInterval({ start: startOfMonth(first), end: endOfMonth(first) }).map(date =>
      calendarDayMap.value[format(date, 'yyyy-MM-dd')] || null
    ),
  ];
});
const mobileSelectedDay = computed(() => mobileSelectedDate.value ? calendarDayMap.value[mobileSelectedDate.value] : null);
const changeMobileMonth = (direction: number) => {
  mobileMonthIndex.value = Math.min(Math.max(mobileMonthIndex.value + direction, 0), mobileMonths.value.length - 1);
  mobileSelectedDate.value = null;
};

const showVibrant = computed(() => vibrantRatio.value >= 0.01);

// 情绪色值映射 - 使用 CSS 变量名
const emotionVarMap: Record<string, string> = {
  warm: 'var(--ec-warm)',
  cool: 'var(--ec-cool)',
  vibrant: 'var(--ec-vibrant)',
  muted: 'var(--ec-muted)',
  neutral: 'var(--ec-neutral)', // 为“日常”单独分配颜色
};

const getEmotionLabel = (hint: string | null): string => {
  const map: Record<string, string> = {
    warm: '温暖', cool: '清冷', vibrant: '鲜活', muted: '平淡', neutral: '日常',
  };
  return hint ? (map[hint] || hint) : '日常';
};

const getCellScale = (count: number): number =>
  Math.min(0.58 + 0.42 * Math.log1p(count) / Math.log1p(50), 1);

const getCellStyle = (day: GridDay): Record<string, string> => {
  if (day.count === 0) return { backgroundColor: 'var(--ec-empty)' };

  const emotionKey = day.emotionHint || 'neutral';
  const bgColorVar = emotionVarMap[emotionKey] || emotionVarMap.neutral;

  // 少量照片也保持足够对比度；数量增加时逐渐加深
  const opacity = Math.min(0.65 + day.count * 0.03, 1.0);

  if (day.dominantColor) {
    // 以代表照片的色彩为主，分类色只用于保持图例的识别性
    const mixedColor = `color-mix(in srgb, ${day.dominantColor} 60%, ${bgColorVar})`;
    return { backgroundColor: `color-mix(in srgb, ${mixedColor} ${opacity * 100}%, transparent)` };
  }

  return { backgroundColor: `color-mix(in srgb, ${bgColorVar} ${opacity * 100}%, transparent)` };
};

const buildGrid = (calendarData: EmotionCalendarResponse['data']) => {
  const dataMap = calendarData.reduce((acc, item) => {
    acc[item.date] = item;
    return acc;
  }, {} as Record<string, EmotionCalendarResponse['data'][0]>);

  // 统计 vibrant 占比
  const vibrantCount = calendarData.filter(d => d.emotion_hint === 'vibrant').length;
  const totalWithPhotos = calendarData.filter(d => d.photo_count > 0).length;
  vibrantRatio.value = totalWithPhotos > 0 ? vibrantCount / totalWithPhotos : 0;

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
      if (!date) return { date: '', displayDate: '', count: 0, valid: false, dominantColor: null, brightness: null, saturation: null, categories: [], emotionHint: null };
      const dateStr = format(date, 'yyyy-MM-dd');
      const displayDateStr = format(date, 'M月d日');
      const item = dataMap[dateStr];
      return {
        date: dateStr,
        displayDate: displayDateStr,
        count: item?.photo_count || 0,
        valid: true,
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

  // 滚动年度可能从月底开始，短暂的首月标签会与下月重叠。
  const firstMonth = days[0].getMonth();
  if (days.filter(day => day.getMonth() === firstMonth && day.getFullYear() === days[0].getFullYear()).length < 14) {
    labels.shift();
  }

  gridColumns.value = columns;
  monthLabels.value = labels;
  const previousMonth = mobileMonths.value[mobileMonthIndex.value];
  mobileMonths.value = [...new Set(days.map(day => format(day, 'yyyy-MM')))];
  const previousIndex = mobileMonths.value.indexOf(previousMonth);
  mobileMonthIndex.value = previousIndex >= 0 ? previousIndex : mobileMonths.value.length - 1;
  if (mobileSelectedDate.value && !days.some(day => format(day, 'yyyy-MM-dd') === mobileSelectedDate.value)) {
    mobileSelectedDate.value = null;
  }
};

const fetchData = async () => {
  try {
    const res = await dashboardApi.getEmotionCalendar(selectedYear.value || undefined);
    totalPhotos.value = res.total_photos;
    totalDays.value = res.total_days;
    reanalysisRemaining.value = res.reanalysis_remaining || 0;
    if (res.available_years) {
      availableYears.value = res.available_years;
    }
    buildGrid(res.data);
    if (reanalysisTimer) clearTimeout(reanalysisTimer);
    if (active && reanalysisRemaining.value > 0) {
      reanalysisTimer = setTimeout(fetchData, 60_000);
    }
  } catch (error) {
    console.error('Failed to fetch emotion calendar data:', error);
    ElMessage.error('加载拍摄情况失败');
  }
};

onMounted(() => {
  active = true;
  fetchData();
});
onUnmounted(() => {
  active = false;
  if (reanalysisTimer) clearTimeout(reanalysisTimer);
});
</script>

<!-- 非 scoped：CSS 变量需要在 html.dark 层级正确覆盖 -->
<style>
.emotion-calendar {
  --ec-warm: #E8B89E;
  --ec-cool: #9FB8D0;
  --ec-vibrant: #CDB4E0;
  --ec-neutral: #C2D5C4; /* 增加一个柔和的自然色（如浅灰绿色）作为日常色 */
  --ec-muted: #D8DCE3;
  --ec-empty: #E4E7EC;
  --ec-bg: #F7F8FA;
  --ec-title-color: #1D2129;
  --ec-num-color: #1D2129;
  --ec-stats-color: #4E5969;
  --ec-legend-text: #6B7785;
  --ec-month-color: #4E5969;
  --ec-hover-ring: #9CA3AF;
}
html.dark .emotion-calendar {
  --ec-warm: #D99A7C;
  --ec-cool: #8AA7C2;
  --ec-vibrant: #B996CC;
  --ec-neutral: #94A896; /* 日常色对应的暗色版 */
  --ec-muted: #C5C8CD;
  --ec-empty: #2A2D34;
  --ec-bg: #16181D;
  --ec-title-color: #FFFFFF;
  --ec-num-color: #FFFFFF;
  --ec-stats-color: #D0D2D6;
  --ec-legend-text: #B0B4BB;
  --ec-month-color: #D0D2D6;
  --ec-hover-ring: #606773;
}
</style>

<style scoped>

/* ===== 容器 ===== */
.emotion-calendar {
  width: 100%;
}

/* ===== 头部 ===== */
.ec-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
  gap: 12px;
}
.ec-header-left {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ec-title-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex-wrap: wrap;
}
.ec-title-text {
  font-size: 16px;
  font-weight: 400;
  color: var(--ec-stats-color);
}
.ec-title-num {
  font-size: 28px;
  font-weight: 600;
  color: var(--ec-num-color);
  letter-spacing: -0.5px;
  line-height: 1;
}
.ec-stats {
  font-size: 14px;
  font-weight: 400;
  color: var(--ec-stats-color);
  margin-left: 4px;
}
.ec-legend {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.ec-legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--ec-legend-text);
}
.ec-legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.ec-select {
  width: 96px;
  flex-shrink: 0;
}

/* ===== 全年概览：周等宽，始终铺满容器 ===== */
.ec-year-view { padding-bottom: 28px; }
.ec-mobile-view { display: none; }

/* ===== 网格 ===== */
.ec-grid {
  display: grid;
  gap: 2px;
  width: 100%;
}
.ec-refresh-status { font-size: 12px; color: var(--ec-stats-color); }
.ec-col {
  display: flex;
  flex-direction: column;
  gap: 2px;
  position: relative;
  min-width: 0;
}

/* ===== 色块 ===== */
.ec-cell {
  width: 100%;
  aspect-ratio: 1;
  border-radius: 50%;
  transition: opacity 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}
.ec-cell-empty {
  background-color: var(--ec-empty);
}
.ec-cell-void {
  background: transparent;
}
.ec-cell-photo {
  cursor: pointer;
}
.ec-cell-photo:hover {
  opacity: 0.85;
  box-shadow: 0 0 0 1px var(--ec-hover-ring);
}

/* ===== 月份标签 ===== */
.ec-month-label {
  position: absolute;
  bottom: -20px;
  left: 0;
  font-size: 13px;
  color: var(--ec-month-color);
  white-space: nowrap;
  pointer-events: none;
}

/* ===== Tooltip ===== */
.ec-tip {
  text-align: center;
  padding: 2px 0;
}
.ec-tip-date {
  font-size: 13px;
  font-weight: 500;
}
.ec-tip-info {
  font-size: 12px;
  margin-top: 3px;
  opacity: 0.85;
}
.ec-tip-emotion {
  margin-left: 2px;
}
.ec-tip-empty {
  font-size: 12px;
  opacity: 0.5;
  margin-top: 2px;
}

/* ===== 移动端适配 ===== */
@media (max-width: 640px) {
  .ec-title-num {
    font-size: 24px;
  }
  .ec-title-text {
    font-size: 14px;
  }
  .ec-legend {
    gap: 8px;
  }
  .ec-legend-item {
    font-size: 11px;
  }
  .ec-legend-dot {
    width: 8px;
    height: 8px;
  }
  .ec-header {
    margin-bottom: 18px;
    flex-wrap: wrap;
  }
}

@media (max-width: 767px) {
  .ec-year-view { display: none; }
  .ec-mobile-view { display: block; }
  .ec-month-nav { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; color: var(--ec-title-color); }
  .ec-month-nav button { width: 40px; height: 40px; border-radius: 8px; font-size: 28px; line-height: 1; }
  .ec-month-nav button:disabled { opacity: 0.3; }
  .ec-month-nav button:not(:disabled):hover { background: var(--ec-empty); }
  .ec-month-nav select { min-height: 40px; padding: 0 8px; border-radius: 8px; background: var(--ec-bg); color: var(--ec-title-color); font-weight: 600; }
  .ec-mobile-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 2px; }
  .ec-weekday { text-align: center; font-size: 12px; color: var(--ec-month-color); padding-bottom: 4px; }
  .ec-mobile-day { min-width: 0; min-height: 48px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; border-radius: 8px; color: var(--ec-title-color); }
  .ec-mobile-day-selected { box-shadow: inset 0 0 0 2px var(--ec-hover-ring); }
  .ec-mobile-day-number { font-size: 11px; line-height: 1; }
  .ec-mobile-dot { width: min(26px, 70%); aspect-ratio: 1; border-radius: 50%; }
  .ec-mobile-detail { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-top: 12px; padding: 10px 12px; border-radius: 8px; background: var(--ec-bg); color: var(--ec-stats-color); font-size: 12px; }
  .ec-mobile-detail button { color: var(--ec-cool); font-weight: 600; white-space: nowrap; }
}
</style>
