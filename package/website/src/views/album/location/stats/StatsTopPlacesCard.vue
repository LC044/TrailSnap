<template>
  <SurfaceCard padding="lg" :elevated="false">
    <div class="flex items-start justify-between gap-3">
      <div><h2 class="stats-title">留下最多照片的地方</h2><p class="stats-caption mt-1">{{ scope }} · 按照片数量排名</p></div>
      <MapPin class="w-4 h-4 ts-muted mt-1 shrink-0" aria-hidden="true" />
    </div>
    <div v-if="loading" class="stats-empty"><el-skeleton :rows="6" animated /></div>
    <div v-else-if="error" class="stats-empty"><span>地点统计加载失败</span><button class="text-primary-500" @click="$emit('retry')">重试</button></div>
    <div v-else-if="!places.length" class="stats-empty">这段时间还没有地点记录</div>
    <template v-else>
      <p class="stats-caption mt-4 mb-2">{{ places[0].name }}留下的照片最多</p>
      <ol class="space-y-1">
        <li v-for="(p, i) in places" :key="p.name">
          <button class="place-row w-full text-left flex items-center gap-3 rounded-xl py-2 px-1" :aria-label="`${p.name}，${p.photo_count} 张照片，查看照片`" @click="$emit('go-location', p.name)">
            <span class="text-xs tabular-nums w-4 shrink-0 ts-muted">{{ String(i + 1).padStart(2, '0') }}</span>
            <div class="w-10 h-10 rounded-lg shrink-0 overflow-hidden flex items-center justify-center bg-primary-500/10">
              <img v-if="covers[p.name] && !failedCovers.has(p.name)" :src="covers[p.name]" alt="" loading="lazy" class="w-full h-full object-cover" @error="failedCovers.add(p.name)" />
              <MapPin v-else class="w-4 h-4 text-primary-500" aria-hidden="true" />
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-center justify-between gap-2"><span class="text-sm font-medium truncate" :title="p.name">{{ p.name }}</span><span class="text-xs tabular-nums shrink-0">{{ p.photo_count.toLocaleString() }} <span class="ts-muted">张</span></span></div>
              <div class="mt-2 h-1 rounded-full overflow-hidden" style="background:var(--ts-color-surface-muted)"><div class="h-full bg-primary-500 rounded-full" :style="{ width: `${p.photo_count / maxCount * 100}%` }"></div></div>
            </div>
          </button>
        </li>
      </ol>
    </template>
  </SurfaceCard>
</template>
<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { MapPin } from 'lucide-vue-next'
import SurfaceCard from '@/components/ui/SurfaceCard.vue'
import type { PlaceStats } from '@/api/location'
const props = defineProps<{ places: PlaceStats[]; covers: Record<string, string>; scope: string; loading: boolean; error: boolean }>()
defineEmits<{ (e: 'go-location', name: string): void; (e: 'retry'): void }>()
const maxCount = computed(() => Math.max(...props.places.map(p => p.photo_count), 1))
const failedCovers = reactive(new Set<string>())
watch(() => props.covers, () => failedCovers.clear())
</script>
<style scoped>
.place-row:hover { background: var(--ts-color-surface-muted); }
</style>
