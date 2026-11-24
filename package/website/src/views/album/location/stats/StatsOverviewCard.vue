<template>
  <section aria-label="足迹概览" class="stats-metrics stats-ticket">
    <div class="stats-ticket-head">
      <div class="stats-ticket-heading">
        <p class="la-panel-kicker">FOOTPRINT OVERVIEW</p>
        <h2 class="stats-ticket-title">足迹概览</h2>
      </div>
      <span v-if="overview" class="la-chip la-chip--accent">
        <span class="stats-ticket-dot" aria-hidden="true"></span>
        {{ coverageCount }} / 34 个省份
      </span>
      <span v-else-if="loading" class="la-chip">正在整理足迹</span>
    </div>

    <div class="stats-ticket-grid">
      <div v-for="(item, index) in metrics" :key="item.label" class="stats-ticket-cell">
        <span class="stats-ticket-index" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
        <component :is="item.icon" class="stats-ticket-icon" aria-hidden="true" />
        <span class="la-stat-label">{{ item.label }}</span>
        <div v-if="item.loading" class="stats-ticket-skeleton" aria-hidden="true">
          <el-skeleton-item variant="h1" style="width: 58%" />
        </div>
        <p v-else class="stats-ticket-value">
          {{ item.value == null ? '—' : item.value.toLocaleString() }}<small>{{ item.unit }}</small>
        </p>
        <p class="stats-ticket-hint">{{ item.hint }}</p>
      </div>
    </div>

    <div v-if="overview" class="stats-coverage">
      <div class="stats-coverage-head">
        <span class="la-stat-label">省份覆盖</span>
        <span class="stats-coverage-value">{{ coveragePercent }}<small>%</small></span>
      </div>
      <div
        class="stats-coverage-track"
        role="img"
        :aria-label="`已点亮 ${coverageCount} 个省份，共 34 个省级行政区`"
      >
        <span
          v-for="n in 34"
          :key="n"
          class="stats-coverage-seg"
          :class="{ 'is-lit': n <= coverageCount }"
          :style="{ '--seg-index': n }"
          aria-hidden="true"
        ></span>
      </div>
      <p class="stats-coverage-note">
        累计覆盖 <span class="la-num">{{ coverageCount }}</span> / 34 个省级行政区
      </p>
    </div>
    <div v-else-if="loading" class="stats-coverage-skeleton" aria-hidden="true"></div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Building2, MapPinned, CalendarDays, Globe2 } from 'lucide-vue-next'
import type { OverviewStats } from '@/api/location'

const props = defineProps<{ overview: OverviewStats | null; loading: boolean }>()

const coverageCount = computed(() => Math.max(0, Math.min(34, props.overview?.province_count ?? 0)))
const coveragePercent = computed(() => Math.round((coverageCount.value / 34) * 100))

const metrics = computed(() => {
  const distance = props.overview?.has_location ? (props.overview.total_distance_km ?? null) : null
  const useWan = distance != null && distance >= 10000
  const distanceValue = distance == null
    ? null
    : useWan
      ? Number((distance / 10000).toFixed(1))
      : Math.round(distance)

  return [
    {
      label: '到访城市',
      value: props.overview?.city_count,
      unit: '座',
      hint: '照片里去重后的城市',
      icon: Building2,
      loading: props.loading,
    },
    {
      label: '覆盖省份',
      value: props.overview?.province_count,
      unit: '个',
      hint: '点亮过的省级行政区',
      icon: MapPinned,
      loading: props.loading,
    },
    {
      label: '记录天数',
      value: props.overview?.travel_days,
      unit: '天',
      hint: '至少留下一张照片的日子',
      icon: CalendarDays,
      loading: props.loading,
    },
    {
      label: '移动距离',
      value: distanceValue,
      unit: useWan ? '万公里' : '公里',
      hint: distance != null
        ? `约绕地球 ${(distance / 40075).toFixed(2)} 圈`
        : '暂无位置记录',
      icon: Globe2,
      loading: props.loading,
    },
  ]
})
</script>