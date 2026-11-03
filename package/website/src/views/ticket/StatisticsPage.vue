<template>
  <AppPage size="wide" class="ticket-dashboard ts-page-content">
    <header class="dashboard-header">
      <div class="dashboard-title">
        <BackButton label="返回列表" @click="goBack" />
        <h1 class="ts-page-title">出行概览</h1>
      </div>
      <TicketStatisticsFilters
        v-model:period="period"
        v-model:passenger="passenger"
        v-model:transport="transport"
        :years="years"
        :passengers="passengers"
        :loading="store.loading"
        @refresh="refresh"
      />
    </header>
    <div v-if="period === 'custom'" class="dashboard-toolbar">
      <UnifiedDatePicker
        v-model="dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        aria-label="自定义日期范围"
        class="range-picker"
      />
    </div>
    <div v-if="store.error" class="error-state ts-surface" role="alert">
      <span>{{ store.error }}</span
      ><button
        class="ts-button ts-button-secondary ts-button-sm"
        @click="refresh"
      >
        重试
      </button>
    </div>
    <div
      v-if="store.loading && !store.items.length"
      class="dashboard-skeleton"
      role="status"
      aria-label="正在加载统计"
    >
      <div v-for="n in 5" :key="n" class="ts-surface animate-pulse" />
    </div>
    <template v-else>
      <div class="metrics-grid" :aria-busy="store.loading">
        <SurfaceCard
          v-for="metric in metrics"
          :key="metric.key"
          class="metric-card"
          :data-testid="`metric-${metric.key}`"
          ><div class="metric-heading">
            <span class="metric-icon"
              ><component :is="metric.icon" class="h-4 w-4"
            /></span>
            <h2>{{ metric.label }}</h2>
          </div>
          <div class="metric-value">
            <span>{{ metric.value }}</span
            ><span class="metric-unit">{{ metric.unit }}</span>
          </div></SurfaceCard
        >
      </div>
      <TicketRouteExplorer
        ref="routeExplorer"
        v-model:selection="mapSelection"
        :summary="summary"
        ><template #filters
          ><TicketStatisticsFilters
            v-model:period="period"
            v-model:passenger="passenger"
            v-model:transport="transport"
            :years="years"
            :passengers="passengers"
            :loading="store.loading"
            @refresh="refresh"
          />
          <UnifiedDatePicker
            v-if="period === 'custom'"
            v-model="dateRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            aria-label="自定义日期范围"
            class="range-picker"
          /> </template
      ></TicketRouteExplorer>
      <div class="dashboard-main-grid">
        <SurfaceCard class="chart-card trend-card"
          ><div class="card-heading">
            <h2>出行趋势</h2>
            <div class="segmented compact" aria-label="趋势指标">
              <button
                v-for="item in trendMetrics"
                :key="item.key"
                :aria-pressed="trendMetric === item.key"
                :class="{ active: trendMetric === item.key }"
                @click="trendMetric = item.key"
              >
                {{ item.label }}
              </button>
            </div>
          </div>
          <div class="trend-plot">
            <StatisticsChart :option="trendOption" label="月度出行趋势" /></div
        ></SurfaceCard>
        <SurfaceCard class="chart-card mode-card"
          ><div class="card-heading"><h2>交通方式</h2></div>
          <div class="mode-content">
            <div class="donut-plot">
              <StatisticsChart :option="modeOption" label="交通方式分布" />
              <div class="donut-center">
                <strong>{{ formatNumber(summary.count) }}</strong
                ><span>行程段</span>
              </div>
            </div>
            <ul class="mode-legend">
              <li v-for="(mode, index) in summary.modes" :key="mode.key">
                <span
                  class="legend-dot"
                  :style="{ background: palette[index] }"
                /><span>{{ mode.label }}</span
                ><strong>{{ mode.count }}<small> 段</small></strong
                ><span class="mode-percentage"
                  >{{ percentage(mode.count, summary.count) }}%</span
                >
              </li>
            </ul>
          </div></SurfaceCard
        >
        <SurfaceCard class="chart-card ranking-card"
          ><div class="card-heading">
            <div class="ranking-tabs">
              <button
                :class="{ selected: rankingTab === 'routes' }"
                :aria-pressed="rankingTab === 'routes'"
                @click="rankingTab = 'routes'"
              >
                高频路线</button
              ><button
                :class="{ selected: rankingTab === 'cities' }"
                :aria-pressed="rankingTab === 'cities'"
                @click="rankingTab = 'cities'"
              >
                到达城市
              </button>
            </div>
            <el-checkbox
              v-if="rankingTab === 'routes'"
              v-model="mergeReturns"
              size="small"
              >往返合并</el-checkbox
            >
          </div>
          <ol v-if="rankingRows.length" class="ranking-list">
            <li v-for="(row, index) in rankingRows" :key="row.name">
              <button
                class="ranking-select"
                :aria-label="`在地图查看${row.name}`"
                :aria-pressed="sameMapSelection(mapSelection, row.selection)"
                @click="selectRanking(row)"
              >
                <span class="rank-number">{{
                  String(index + 1).padStart(2, "0")
                }}</span
                ><span class="rank-name" :title="row.name">{{ row.name }}</span
                ><span class="rank-track"
                  ><span
                    :style="{
                      width: `${percentage(row.count, rankingRows[0].count)}%`,
                    }" /></span
                ><strong>{{ row.count }}<small> 次</small></strong>
              </button>
            </li>
          </ol>
          <div v-else class="plot-state ranking-empty">暂无数据</div>
          <div class="ranking-footer">
            <span
              >出发天数 <strong>{{ summary.days }}</strong> 天</span
            ><span
              >票据 <strong>{{ summary.ticketCount }}</strong> 张</span
            >
          </div></SurfaceCard
        >
      </div>
      <div class="dashboard-bottom-grid">
        <SurfaceCard class="bottom-card"
          ><div class="card-heading"><h2>出发时段</h2></div>
          <table class="departure-heatmap" aria-label="星期与出发时段分布">
            <thead>
              <tr>
                <th />
                <th v-for="day in weekdays" :key="day" scope="col">
                  {{ day }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(label, slot) in timeSlots" :key="label">
                <th scope="row">{{ label }}</th>
                <td v-for="(day, index) in weekdays" :key="day">
                  <span
                    :style="heatStyle(summary.heatmap[slot][index])"
                    :title="`周${day} ${label} ${summary.heatmap[slot][index]}次`"
                    >{{ summary.heatmap[slot][index] || "" }}</span
                  >
                </td>
              </tr>
            </tbody>
          </table></SurfaceCard
        >
        <SurfaceCard class="bottom-card"
          ><div class="card-heading"><h2>席别偏好</h2></div>
          <ul v-if="summary.seats.length" class="seat-list">
            <li v-for="seat in summary.seats" :key="seat.name">
              <span :title="seat.name">{{ seat.name }}</span
              ><span class="rank-track"
                ><span
                  :style="{
                    width: `${percentage(seat.count, seatTotal)}%`,
                  }" /></span
              ><strong>{{ percentage(seat.count, seatTotal) }}%</strong>
            </li>
          </ul>
          <div v-else class="plot-state">暂无数据</div></SurfaceCard
        >
        <SurfaceCard class="bottom-card"
          ><div class="card-heading"><h2>旅途纪录</h2></div>
          <dl class="record-list">
            <div>
              <dt>最长路线</dt>
              <dd>
                <strong :title="longestRoute">{{ longestRoute }}</strong
                ><span>{{
                  summary.longestDistance
                    ? `${formatNumber(summary.longestDistance.distance)} km`
                    : "—"
                }}</span>
              </dd>
            </div>
            <div>
              <dt>最长乘坐</dt>
              <dd>
                <strong>{{
                  formatTravelDuration(summary.longestDuration?.duration || 0)
                }}</strong>
              </dd>
            </div>
            <div>
              <dt>最常乘车次</dt>
              <dd>
                <strong>{{ summary.codes[0]?.name || "—" }}</strong
                ><span>{{
                  summary.codes[0] ? `${summary.codes[0].count} 次` : "—"
                }}</span>
              </dd>
            </div>
          </dl></SurfaceCard
        >
      </div>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, ref, shallowRef, onMounted, onBeforeUnmount } from "vue";
import type { EChartsCoreOption } from "echarts/core";
import { Route, MapPin, Clock, Tickets, Wallet } from "lucide-vue-next";
import AppPage from "@/components/ui/AppPage.vue";
import SurfaceCard from "@/components/ui/SurfaceCard.vue";
import BackButton from "@/components/ui/BackButton.vue";
import UnifiedDatePicker from "@/components/ui/UnifiedDatePicker.vue";
import StatisticsChart from "./components/StatisticsChart.vue";
import TicketRouteExplorer from "./components/TicketRouteExplorer.vue";
import TicketStatisticsFilters from "./components/TicketStatisticsFilters.vue";
import { sameMapSelection, type MapSelection } from "@/utils/ticketMap";
import { useTicketWalletStore } from "@/stores/ticketWalletStore";
import { injectTheme } from "@/composables/useTheme";
import { useAppBack } from "@/composables/useAppBack";

import { ticketStatisticsApi } from "@/api/ticketStatistics";
import {
  aggregateTicketStatistics,
  formatTravelDuration,
  ticketDate,
  transportKinds,
  type TrendMetric,
} from "@/utils/ticketStatistics";

const store = useTicketWalletStore();
const { currentTheme, isDarkMode } = injectTheme();
const goBack = useAppBack("/ticket");
const period = ref("all"),
  passenger = ref(""),
  transport = ref("all");
const dateRange = ref<[string, string] | null>(null);
const trendMetrics = [
  { key: "count", label: "次数" },
  { key: "distance", label: "里程" },
  { key: "amount", label: "金额" },
] as const;
const trendMetric = ref<TrendMetric>("count");
const rankingTab = ref<"routes" | "cities">("routes");
const mergeReturns = ref(true);
const mapSelection = ref<MapSelection>(null);
const routeExplorer = ref<InstanceType<typeof TicketRouteExplorer>>();
function selectRanking(row: { selection: MapSelection }) {
  mapSelection.value = sameMapSelection(mapSelection.value, row.selection)
    ? null
    : row.selection;
  routeExplorer.value?.focus();
}
const stations = shallowRef(new Map<string, string>());
const years = computed(() =>
  [
    ...new Set(
      store.items
        .map((item) => ticketDate(item.date_time)?.year)
        .filter((year): year is number => !!year),
    ),
  ].sort((a, b) => b - a),
);
const passengers = computed(() =>
  [...new Set(store.items.map((item) => item.name).filter(Boolean))].sort(
    (a, b) => a.localeCompare(b, "zh-CN"),
  ),
);
const summary = computed(() =>
  aggregateTicketStatistics(
    store.items,
    {
      year: /^\d{4}$/.test(period.value) ? Number(period.value) : null,
      start: period.value === "custom" ? dateRange.value?.[0] : undefined,
      end: period.value === "custom" ? dateRange.value?.[1] : undefined,
      passenger: passenger.value,
      transport: transport.value,
    },
    store.stats,
    stations.value,
    mergeReturns.value,
  ),
);
const formatNumber = (value: number) =>
  value.toLocaleString("zh-CN", { maximumFractionDigits: 1 });
const percentage = (value: number, total: number) =>
  total > 0 ? Math.round((value / total) * 1000) / 10 : 0;
const metrics = computed(() => [
  {
    key: "count",
    label: "行程段数",
    value: formatNumber(summary.value.count),
    unit: "段",
    icon: Tickets,
  },
  {
    key: "distance",
    label: "累计里程",
    value: formatNumber(summary.value.distance),
    unit: "km",
    icon: Route,
  },
  {
    key: "duration",
    label: "乘坐时长",
    value: formatNumber(Math.round((summary.value.duration / 60) * 10) / 10),
    unit: "小时",
    icon: Clock,
  },
  {
    key: "cities",
    label: "覆盖城市",
    value: formatNumber(summary.value.cityCount),
    unit: "座",
    icon: MapPin,
  },
  {
    key: "amount",
    label: "票面金额",
    value: summary.value.amount.toLocaleString("zh-CN", {
      maximumFractionDigits: 2,
    }),
    unit: "元",
    icon: Wallet,
  },
]);
const rankingRows = computed(() =>
  (rankingTab.value === "routes"
    ? summary.value.routes.map((route) => ({
        name: `${route.from} ${mergeReturns.value ? "↔" : "→"} ${route.to}`,
        count: route.count,
        selection: {
          type: "route",
          from: route.from,
          to: route.to,
          directional: !mergeReturns.value,
        } as MapSelection,
      }))
    : summary.value.arrivals.map((city) => ({
        ...city,
        selection: { type: "city", name: city.name } as MapSelection,
      }))
  ).slice(0, 6),
);
const seatTotal = computed(() =>
  summary.value.seats.reduce((sum, seat) => sum + seat.count, 0),
);
const longestRoute = computed(() => {
  const row = summary.value.longestDistance;
  return row ? `${row.from} → ${row.to}` : "—";
});
const weekdays = ["一", "二", "三", "四", "五", "六", "日"];
const timeSlots = ["凌晨", "上午", "下午", "夜间"];
const heatMax = computed(() => Math.max(1, ...summary.value.heatmap.flat()));
const heatStyle = (count: number) => ({
  background: `rgba(${currentTheme.value.rgb}, ${count ? 0.15 + (count / heatMax.value) * 0.75 : 0.06})`,
  color:
    count / heatMax.value > 0.55 ? "#fff" : "var(--ts-color-text-secondary)",
});
const palette = computed(() => [
  currentTheme.value.primary,
  currentTheme.value.name === "emerald" ? "#e9a23b" : "#35b5a2",
  currentTheme.value.name === "violet" ? "#e49b53" : "#9b87e8",
]);
const textColor = computed(() => (isDarkMode.value ? "#a8b3c3" : "#7c899b"));
const gridColor = computed(() => (isDarkMode.value ? "#303b4c" : "#edf0f5"));
const reducedMotion = ref(false);
const commonOption = computed(() => ({
  animation: !reducedMotion.value,
  color: palette.value,
  textStyle: {
    fontFamily: "system-ui, Microsoft YaHei, sans-serif",
    color: textColor.value,
  },
  backgroundColor: "transparent",
  tooltip: {
    confine: true,
    backgroundColor: isDarkMode.value ? "#202938" : "#fff",
    borderColor: gridColor.value,
    textStyle: {
      color: isDarkMode.value ? "#e2e8f0" : "#334155",
      fontSize: 12,
    },
  },
}));
const trendOption = computed<EChartsCoreOption>(() => {
  const rows = summary.value.months,
    metric = trendMetric.value,
    zoom = rows.length > 24;
  return {
    ...commonOption.value,
    tooltip: { ...commonOption.value.tooltip, trigger: "axis" },
    legend: {
      top: 4,
      right: 0,
      itemWidth: 8,
      itemHeight: 8,
      icon: "circle",
      textStyle: { color: textColor.value, fontSize: 11 },
    },
    grid: {
      left: 46,
      right: 12,
      top: 46,
      bottom: zoom ? 66 : 30,
    },
    xAxis: {
      type: "category",
      data: rows.map((row) => row.month),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: textColor.value,
        fontSize: 10,
        formatter: (month: string) =>
          period.value !== "all" && period.value !== "custom"
            ? `${Number(month.slice(5))}月`
            : month.replace("-", "."),
      },
    },
    yAxis: {
      type: "value",
      minInterval: metric === "count" ? 1 : undefined,
      axisLabel: { color: textColor.value, fontSize: 10 },
      splitLine: { lineStyle: { color: gridColor.value, type: "dashed" } },
      name: metric === "distance" ? "km" : metric === "amount" ? "元" : "",
      nameTextStyle: { color: textColor.value, fontSize: 10 },
    },
    dataZoom: zoom
      ? [
          {
            type: "slider",
            height: 15,
            bottom: 0,
            startValue: Math.max(0, rows.length - 24),
            endValue: rows.length - 1,
            borderColor: "transparent",
            showDetail: false,
          },
          { type: "inside" },
        ]
      : [],
    series: transportKinds.map((mode) => ({
      name: mode.label,
      type: "bar",
      stack: "transport",
      barMaxWidth: 22,
      itemStyle: { borderRadius: [3, 3, 0, 0] },
      data: rows.map(
        (row) => Math.round(row.modes[mode.key][metric] * 100) / 100,
      ),
    })),
    graphic: summary.value.count
      ? []
      : [
          {
            type: "text",
            left: "center",
            top: "middle",
            style: { text: "暂无数据", fill: textColor.value, fontSize: 13 },
          },
        ],
  };
});
const modeOption = computed<EChartsCoreOption>(() => ({
  ...commonOption.value,
  series: [
    {
      type: "pie",
      stillShowZeroSum: false,
      radius: ["70%", "85%"],
      center: ["50%", "50%"],
      avoidLabelOverlap: true,
      label: { show: false },
      emphasis: { scaleSize: 3 },
      emptyCircleStyle: { color: gridColor.value },
      itemStyle: {
        borderRadius: 3,
        borderColor: isDarkMode.value ? "#161f2c" : "#fff",
        borderWidth: 3,
      },
      data: summary.value.modes.map((mode, index) => ({
        name: mode.label,
        value: mode.count,
        itemStyle: { color: palette.value[index] },
      })),
    },
  ],
}));
let disposed = false;
async function refresh() {
  await store.fetch();
}
onMounted(() => {
  reducedMotion.value = window.matchMedia(
    "(prefers-reduced-motion: reduce)",
  ).matches;
  void store.fetch();
  void ticketStatisticsApi
    .stationCities()
    .then((data) => {
      if (!disposed) stations.value = data;
    })
    .catch(() => {});
});
onBeforeUnmount(() => {
  disposed = true;
});
</script>

<style scoped>
.ticket-dashboard {
  color: var(--ts-color-text);
  padding-bottom: 32px;
}
.dashboard-header,
.dashboard-title,
.dashboard-filters,
.dashboard-toolbar,
.card-heading {
  display: flex;
  align-items: center;
}
.dashboard-header {
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 18px;
  margin-bottom: 20px;
}
.dashboard-title {
  gap: 14px;
}
.dashboard-filters {
  flex-wrap: wrap;
  gap: 10px;
}
.period-select {
  width: 130px;
}
.passenger-select {
  width: 150px;
}
.transport-select {
  width: 160px;
}
.dashboard-toolbar {
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 22px;
}
.range-picker {
  width: 290px;
  max-width: 100%;
}
.segmented {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 3px;
  padding: 4px;
  border-radius: 12px;
  background: var(--ts-color-surface-muted);
}
.segmented button {
  padding: 7px 17px;
  border-radius: 9px;
  font-size: 12px;
  color: var(--ts-color-text-secondary);
  transition:
    background 0.15s,
    color 0.15s;
}
.segmented button.active {
  background: var(--ts-color-surface);
  color: var(--theme-primary);
  box-shadow: 0 1px 4px rgb(0 0 0 / 5%);
  font-weight: 600;
}
.segmented.compact {
  padding: 3px;
  border-radius: 9px;
}
.segmented.compact button {
  padding: 5px 11px;
  border-radius: 7px;
  font-size: 11px;
}
button:focus-visible {
  outline: 2px solid var(--theme-primary);
  outline-offset: 2px;
}
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}
.metric-card {
  min-width: 0;
  container-type: inline-size;
}
.metric-heading {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 18px;
}
.metric-heading h2 {
  font-size: 12px;
  color: var(--ts-color-text-secondary);
  font-weight: 500;
}
.metric-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  color: var(--theme-primary);
  background: rgba(var(--theme-rgb), 0.09);
}
.metric-value {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
  font-size: clamp(20px, 16cqi, 36px);
  font-weight: 700;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.8px;
}
.metric-unit {
  font-size: 11px;
  font-weight: 400;
  letter-spacing: 0;
  color: var(--ts-color-text-secondary);
}
.dashboard-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(350px, 1fr);
  gap: 20px;
  margin-bottom: 20px;
}
.chart-card,
.bottom-card {
  min-width: 0;
  overflow: hidden;
}
.card-heading {
  justify-content: space-between;
  gap: 12px;
  min-height: 32px;
  margin-bottom: 12px;
}
.card-heading h2 {
  font-size: 15px;
  font-weight: 650;
}
.trend-plot {
  height: 227px;
}
.mode-content {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 227px;
}
.donut-plot {
  position: relative;
  width: 47%;
  min-width: 130px;
  max-width: 210px;
  height: 195px;
}
.donut-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  pointer-events: none;
  gap: 3px;
}
.donut-center strong {
  font-size: 28px;
  font-variant-numeric: tabular-nums;
}
.donut-center span {
  color: var(--ts-color-text-secondary);
  font-size: 10px;
}
.mode-legend {
  display: flex;
  flex-direction: column;
  gap: 25px;
  flex: 1;
  font-size: 11px;
}
.mode-legend li {
  display: flex;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
}
.legend-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.mode-legend strong {
  margin-left: auto;
  font-size: 12px;
  font-weight: 600;
}
.mode-legend small {
  font-size: 10px;
  font-weight: 400;
}
.mode-percentage {
  color: var(--ts-color-text-secondary);
  width: 30px;
  text-align: right;
}

.plot-state {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 14px;
  color: var(--ts-color-text-tertiary);
  font-size: 12px;
  min-height: 150px;
  height: 100%;
}

.ranking-card {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
}
.ranking-tabs {
  display: flex;
  align-items: center;
  gap: 16px;
}
.ranking-tabs button {
  font-size: 14px;
  color: var(--ts-color-text-tertiary);
  font-weight: 600;
}
.ranking-tabs button.selected {
  color: var(--ts-color-text);
}
.ranking-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 32px;
  justify-content: space-around;
  flex: 1;
  min-height: 150px;
}
.ranking-select {
  width: 100%;
  min-height: 44px;
  text-align: left;
  border-radius: 8px;
  padding: 4px;
}
.ranking-select:hover,
.ranking-select[aria-pressed="true"] {
  background: rgba(var(--theme-rgb), 0.07);
}
.ranking-list li > button {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 11px;
}
.rank-number {
  font-size: 10px;
  color: var(--ts-color-text-tertiary);
  width: 18px;
  flex-shrink: 0;
}
.rank-name {
  width: 135px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rank-track {
  display: block;
  flex: 1;
  min-width: 25px;
  height: 7px;
  border-radius: 10px;
  background: rgba(var(--theme-rgb), 0.07);
  overflow: hidden;
}
.rank-track > span {
  display: block;
  height: 100%;
  min-width: 2px;
  border-radius: inherit;
  background: rgba(var(--theme-rgb), 0.72);
  transition: width 0.2s;
}
.ranking-list li:first-child .rank-track > span {
  background: var(--theme-primary);
}
.ranking-list strong {
  width: 40px;
  text-align: right;
  font-size: 12px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.ranking-list small {
  color: var(--ts-color-text-secondary);
  font-size: 10px;
  font-weight: 400;
}
.ranking-empty {
  flex: 1;
}
.ranking-footer {
  display: flex;
  gap: 24px;
  border-top: 1px solid var(--ts-color-divider);
  padding-top: 13px;
  margin-top: 10px;
  font-size: 11px;
  color: var(--ts-color-text-secondary);
}
.ranking-footer strong {
  color: var(--ts-color-text);
  font-weight: 600;
}
.dashboard-bottom-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
}
.bottom-card {
  min-height: 215px;
}
.departure-heatmap {
  width: 100%;
  border-collapse: separate;
  border-spacing: 6px 7px;
  table-layout: fixed;
}
.departure-heatmap th {
  font-weight: 400;
  color: var(--ts-color-text-tertiary);
  font-size: 10px;
}
.departure-heatmap th:first-child {
  width: 30px;
  text-align: left;
}
.departure-heatmap td {
  padding: 0;
}
.departure-heatmap td span {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 21px;
  border-radius: 5px;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}
.seat-list {
  display: flex;
  flex-direction: column;
  gap: 17px;
  max-height: 155px;
  overflow-y: auto;
  padding: 5px 3px 5px 0;
}
.seat-list li {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 11px;
}
.seat-list li > span:first-child {
  width: 65px;
  color: var(--ts-color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.seat-list strong {
  width: 36px;
  text-align: right;
  font-size: 11px;
  font-weight: 500;
  color: var(--ts-color-text-secondary);
}
.record-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding-top: 6px;
}
.record-list > div {
  display: flex;
  gap: 12px;
  align-items: center;
}
.record-list dt {
  width: 60px;
  flex-shrink: 0;
  color: var(--ts-color-text-secondary);
  font-size: 11px;
}
.record-list dd {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.record-list strong {
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.record-list dd > span {
  white-space: nowrap;
  font-size: 10px;
  color: var(--ts-color-text-secondary);
}
.error-state {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 18px;
  margin-bottom: 20px;
  font-size: 13px;
}
.dashboard-skeleton {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
}
.dashboard-skeleton > div {
  height: 132px;
}
@media (prefers-reduced-motion: reduce) {
  .rank-track > span {
    transition: none;
  }
}
@media (max-width: 1200px) {
  .dashboard-main-grid {
    grid-template-columns: minmax(0, 1.35fr) minmax(315px, 1fr);
  }
  .mode-content {
    gap: 5px;
  }
  .mode-legend {
    font-size: 10px;
  }
  .rank-name {
    width: 110px;
  }
  .record-list dd {
    flex-wrap: wrap;
    gap: 2px 8px;
  }
  .dashboard-bottom-grid {
    gap: 14px;
  }
}
@media (max-width: 1023px) {
  .metrics-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .dashboard-bottom-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .dashboard-bottom-grid > :last-child {
    grid-column: 1 / -1;
  }
  .metrics-grid {
    gap: 10px;
  }
  .metric-heading {
    gap: 6px;
  }
  .metric-icon {
    width: 25px;
    height: 25px;
  }
  .metric-heading h2 {
    font-size: 11px;
  }
  .metric-value {
    gap: 4px;
  }
}
@media (max-width: 900px) {
  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .metric-card:last-child {
    grid-column: 1 / -1;
  }
  .dashboard-main-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .mode-content {
    justify-content: flex-start;
    gap: 30px;
    min-height: 190px;
  }
  .mode-legend {
    font-size: 12px;
    max-width: 320px;
  }
  .mode-card .donut-plot {
    height: 180px;
    width: 180px;
  }

  .ranking-list {
    grid-template-columns: minmax(0, 1fr);
    min-height: 240px;
    gap: 8px;
  }
  .rank-name {
    width: 160px;
  }
}
@media (max-width: 639px) {
  .dashboard-header {
    gap: 16px;
  }
  .dashboard-title {
    gap: 10px;
  }
  .dashboard-filters {
    width: 100%;
    gap: 8px;
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 40px;
  }
  .period-select,
  .passenger-select,
  .transport-select {
    width: 100%;
    min-width: 0;
  }
  .transport-select {
    grid-column: 1 / 3;
    grid-row: 2;
  }
  .dashboard-filters > button {
    grid-column: 3;
    grid-row: 1;
    width: 40px;
  }
  .dashboard-toolbar {
    margin-bottom: 16px;
  }
  .range-picker {
    width: 100%;
  }
  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    margin-bottom: 16px;
  }
  .metric-card:last-child {
    grid-column: 1 / -1;
  }
  .metric-heading {
    margin-bottom: 14px;
  }
  .metric-heading h2 {
    font-size: 12px;
  }
  .metric-value {
    font-size: clamp(22px, 16cqi, 29px);
  }
  .metric-card:last-child .metric-value {
    font-size: 32px;
  }
  .dashboard-main-grid,
  .dashboard-bottom-grid {
    gap: 16px;
  }
  .dashboard-main-grid {
    margin-bottom: 16px;
  }
  .dashboard-bottom-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .dashboard-bottom-grid > :last-child {
    grid-column: auto;
  }
  .mode-content {
    gap: 10px;
  }
  .mode-card .donut-plot {
    width: 43%;
    min-width: 110px;
    height: 180px;
  }
  .mode-legend {
    gap: 22px;
    font-size: 11px;
  }
  .mode-legend li {
    gap: 5px;
  }
  .mode-percentage {
    width: 28px;
    font-size: 10px;
  }
  .trend-plot {
    height: 230px;
  }

  .ranking-tabs {
    gap: 12px;
  }
  .ranking-tabs button {
    font-size: 13px;
  }
  .rank-name {
    width: 116px;
  }
  .ranking-list li {
    gap: 7px;
  }
  .dashboard-skeleton {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
