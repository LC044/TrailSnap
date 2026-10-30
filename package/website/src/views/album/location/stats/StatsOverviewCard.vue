<template>
  <section aria-label="足迹概览" class="stats-metrics">
    <SurfaceCard v-for="item in metrics" :key="item.label" padding="lg" :elevated="false">
      <div class="flex items-center justify-between gap-2">
        <span class="text-sm ts-muted">{{ item.label }}</span>
        <component :is="item.icon" class="w-4 h-4 text-primary-500" aria-hidden="true" />
      </div>
      <div v-if="item.loading" class="h-10 mt-3"><el-skeleton-item variant="h1" style="width: 65%" /></div>
      <p v-else class="stats-number">{{ item.value == null ? '—' : item.value.toLocaleString() }}<span>{{ item.unit }}</span></p>
      <p class="text-xs ts-muted mt-2">{{ item.hint }}</p>
    </SurfaceCard>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { Building2, MapPinned, CalendarDays, Globe2 } from 'lucide-vue-next'
import SurfaceCard from '@/components/ui/SurfaceCard.vue'
import type { OverviewStats } from '@/api/location'
const props = defineProps<{ overview: OverviewStats | null; loading: boolean }>()
const metrics = computed(() => [
  { label: '到访城市', value: props.overview?.city_count, unit: '座', hint: '按照片中的城市去重', icon: Building2, loading: props.loading },
  { label: '覆盖省份', value: props.overview?.province_count, unit: '个', hint: '按照片中的省级地区去重', icon: MapPinned, loading: props.loading },
  { label: '记录天数', value: props.overview?.travel_days, unit: '天', hint: '至少留下一张照片的日子', icon: CalendarDays, loading: props.loading },
  { label: '移动距离', value: props.overview?.has_location ? Math.round(props.overview.total_distance_km) : null, unit: '公里', hint: props.overview?.has_location ? `约绕地球 ${(props.overview.total_distance_km / 40075).toFixed(2)} 圈` : '暂无位置记录', icon: Globe2, loading: props.loading },
])
</script>
