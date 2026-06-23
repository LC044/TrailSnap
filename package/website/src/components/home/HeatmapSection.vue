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
      </div>
      <el-select v-model="selectedYear" size="small" class="ec-select" @change="fetchData" placeholder="过去一年">
        <el-option label="过去一年" :value="undefined" />
        <el-option v-for="year in availableYears" :key="year" :label="`${year}年`" :value="year" />
      </el-select>
    </div>

    <!-- 日历色块主体 -->
    <div class="ec-grid-scroll" ref="scrollContainer">
      <div class="ec-grid" :style="{ gridTemplateColumns: gridTemplateCols }">
        <template v-for="(col, colIndex) in flatColumns" :key="colIndex">
          <div class="ec-col" :style="{ width: col.width + 'px' }">
            <template v-for="(day, rowIndex) in col.days" :key="`${colIndex}-${rowIndex}`">
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
                  :style="day.count > 0 ? getCellStyle(day) : {}"
                  @click="day.count > 0 ? $router.push({ path: '/search', query: { q: day.date } }) : undefined"
                ></div>
              </el-tooltip>
              <div v-else class="ec-cell ec-cell-void"></div>
            </template>
            <!-- 月份标签 -->
            <div v-if="col.monthLabel" class="ec-month-label">{{ col.monthLabel }}</div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, nextTick } from 'vue';
import { dashboardApi, type EmotionCalendarResponse } from '@/api/dashboard';
import { format, subDays, startOfYear, endOfYear, eachDayOfInterval, getDay } from 'date-fns';
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

interface FlatColumn {
  days: GridDay[];
  width: number;
  monthLabel: string;
  compressed: boolean;
}

const selectedYear = ref<number | undefined>(undefined);
const totalPhotos = ref(0);
const totalDays = ref(0);
const availableYears = ref<number[]>([]);
const scrollContainer = ref<HTMLElement | null>(null);
const vibrantRatio = ref(0);

const gridColumns = ref<GridDay[][]>([]);
const monthLabels = ref<{ text: string; index: number }[]>([]);

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

// 计算每列宽度：有照片的列按拍摄数量映射 14px-36px，无照片固定 12px
const getColWidth = (days: GridDay[]): number => {
  const hasPhoto = days.some(d => d.valid && d.count > 0);
  if (!hasPhoto) return 12;
  const maxCount = Math.max(...days.filter(d => d.valid).map(d => d.count), 0);
  // 映射 1-50+ → 14px-36px
  if (maxCount <= 0) return 12;
  return Math.min(14 + Math.floor(maxCount * 0.44), 36);
};

// 检测连续无照片列，压缩宽度
const isCompressedCol = (days: GridDay[]): boolean => {
  const allEmpty = days.every(d => !d.valid || d.count === 0);
  return allEmpty;
};

const flatColumns = computed<FlatColumn[]>(() => {
  const monthMap: Record<number, string> = {};
  monthLabels.value.forEach(l => { monthMap[l.index] = l.text; });

  // 检测连续压缩区段
  const compressedFlags = gridColumns.value.map(col => isCompressedCol(col));

  // 连续30天以上无照片的区域压缩
  let inCompressedRun = false;
  let runStart = 0;
  const compressed = compressedFlags.slice(); // copy

  for (let i = 0; i < compressedFlags.length; i++) {
    if (compressedFlags[i]) {
      if (!inCompressedRun) {
        inCompressedRun = true;
        runStart = i;
      }
    } else {
      if (inCompressedRun) {
        const runLen = i - runStart;
        // 连续4周以上无照片（约28天）压缩
        if (runLen >= 4) {
          // 保留首尾各1列，中间折叠为1列
          for (let j = runStart + 1; j < i - 1; j++) {
            compressed[j] = true; // 标记为需要压缩
          }
        }
        inCompressedRun = false;
      }
    }
  }
  // 尾部处理
  if (inCompressedRun) {
    const runLen = compressedFlags.length - runStart;
    if (runLen >= 4) {
      for (let j = runStart + 1; j < compressedFlags.length - 1; j++) {
        compressed[j] = true;
      }
    }
  }

  return gridColumns.value.map((col, idx) => {
    const isCompressed = compressed[idx];
    const width = isCompressed ? 6 : getColWidth(col);
    return {
      days: col,
      width,
      monthLabel: monthMap[idx] || '',
      compressed: isCompressed,
    };
  });
});

const gridTemplateCols = computed(() => {
  return flatColumns.value.map(c => c.width + 'px').join(' ');
});

const getCellStyle = (day: GridDay): Record<string, string> => {
  if (day.count === 0) return { backgroundColor: 'var(--ec-empty)' };

  const emotionKey = day.emotionHint || 'neutral';
  const bgColorVar = emotionVarMap[emotionKey] || emotionVarMap.neutral;

  // 照片数量越多颜色越深（不透明度越高），映射 0.4-1.0
  const opacity = Math.min(0.4 + day.count * 0.05, 1.0);

  if (day.dominantColor) {
    // 核心优化：将照片提取的主题色与情绪规范色进行混合（如 55%主题色 + 45%情绪色）
    // 既保留了每天照片真实的色彩倾向，又能统一到整体色系中，解决单纯提取颜色导致画面"脏、乱"的问题
    const mixedColor = `color-mix(in srgb, ${day.dominantColor} 55%, ${bgColorVar})`;
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
    totalPhotos.value = res.total_photos;
    totalDays.value = res.total_days;
    if (res.available_years) {
      availableYears.value = res.available_years;
    }
    buildGrid(res.data);
  } catch (error) {
    console.error('Failed to fetch emotion calendar data:', error);
    ElMessage.error('加载拍摄情况失败');
  }
};

onMounted(() => {
  fetchData();
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
html.dark .ec-grid-scroll::-webkit-scrollbar-thumb {
  background-color: #3A3F48;
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
  border-radius: 3px;
  flex-shrink: 0;
}
.ec-select {
  width: 96px;
  flex-shrink: 0;
}

/* ===== 日历网格滚动区 ===== */
.ec-grid-scroll {
  overflow-x: auto;
  padding-bottom: 28px;
}
.ec-grid-scroll::-webkit-scrollbar {
  height: 5px;
}
.ec-grid-scroll::-webkit-scrollbar-track {
  background: transparent;
}
.ec-grid-scroll::-webkit-scrollbar-thumb {
  background-color: #cbd5e1;
  border-radius: 4px;
}

/* ===== 网格 ===== */
.ec-grid {
  display: flex;
  gap: 2px;
}
.ec-col {
  display: flex;
  flex-direction: column;
  gap: 4px;
  position: relative;
  flex-shrink: 0;
}

/* ===== 色块 ===== */
.ec-cell {
  width: 100%;
  aspect-ratio: 1;
  border-radius: 4px;
  transition: opacity 0.15s ease, box-shadow 0.15s ease;
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
  color: rgba(255, 255, 255, 0.85);
}
.ec-tip-emotion {
  margin-left: 2px;
}
.ec-tip-empty {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
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
  }
}
</style>
