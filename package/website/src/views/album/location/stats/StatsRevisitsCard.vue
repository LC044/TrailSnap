<template>
  <SurfaceCard padding="lg" :elevated="false">
    <h2 class="stats-title">多日记录的地方</h2><p class="stats-caption mt-1">{{ scope }} · 按有照片的天数排列，不代表独立到访次数</p>
    <div v-if="loading" class="stats-empty"><el-skeleton :rows="3" animated /></div>
    <div v-else-if="error" class="stats-empty"><span>地点记录加载失败</span><button class="text-primary-500" @click="$emit('retry')">重试</button></div>
    <div v-else-if="!revisits.length" class="stats-empty">还没有在多个日期留下照片的地点</div>
    <template v-else>
      <ul class="mt-4 divide-y stats-rule">
        <li v-for="r in visible" :key="r.name" class="stats-rule">
          <button class="w-full flex items-center justify-between gap-3 py-3 text-left" @click="$emit('go-location', r.name)">
            <div class="min-w-0"><p class="text-sm font-medium truncate">{{ r.name }}</p><p class="stats-caption mt-1">{{ r.first_date }} 至 {{ r.last_date }}</p></div>
            <span class="text-sm font-semibold shrink-0 tabular-nums">{{ r.visit_count.toLocaleString() }} <span class="text-xs ts-muted font-normal">天</span></span>
          </button>
        </li>
      </ul>
      <button v-if="revisits.length > 5" class="ts-button ts-button-ghost ts-button-sm mt-2" :aria-expanded="expanded" @click="expanded = !expanded">{{ expanded ? '收起' : `展开全部 ${revisits.length} 个地点` }}</button>
    </template>
  </SurfaceCard>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import SurfaceCard from '@/components/ui/SurfaceCard.vue'
import type { PlaceStats } from '@/api/location'
const props = defineProps<{ revisits: PlaceStats[]; scope: string; loading: boolean; error: boolean }>()
defineEmits<{ (e: 'retry'): void; (e: 'go-location', name: string): void }>()
const expanded = ref(false)
const visible = computed(() => expanded.value ? props.revisits : props.revisits.slice(0, 5))
</script>
