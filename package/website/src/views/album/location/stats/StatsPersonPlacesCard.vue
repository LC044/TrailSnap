<template>
  <SurfaceCard padding="lg" :elevated="false">
    <h2 class="stats-title flex items-center gap-2"><UsersRound class="w-4 h-4 text-primary-500" />人物足迹</h2>
    <p class="stats-caption mt-1">当前时间与地区内，地点照片最多的前 5 位人物</p>
    <div v-if="loading" class="stats-empty"><el-skeleton :rows="5" animated /></div>
    <div v-else-if="error" class="stats-empty" role="alert"><span>人物足迹加载失败</span><button class="text-primary-500" @click="fetchPeople">重试</button></div>
    <div v-else-if="!people.length" class="stats-empty">当前时间和地区内还没有人物地点记录</div>
    <div v-else class="divide-y stats-rule mt-3">
      <section v-for="(person, index) in people" :key="person.person_id" class="person-footprint py-5 stats-rule" :aria-label="`${person.person_name}的足迹`">
        <header class="flex items-center gap-3 mb-4">
          <span class="text-xs ts-muted tabular-nums shrink-0">{{ String(index + 1).padStart(2, '0') }}</span>
          <div class="w-11 h-11 rounded-full overflow-hidden shrink-0 bg-primary-500/10 flex items-center justify-center">
            <img v-if="person.cover_photo_id && !failedCovers.has(person.person_id)" :src="thumbnailUrl(person.cover_photo_id, 'small')" alt="" loading="lazy" class="w-full h-full object-cover" @error="failedCovers.add(person.person_id)" />
            <UsersRound v-else class="w-5 h-5 text-primary-500" aria-hidden="true" />
          </div>
          <div class="min-w-0"><h3 class="text-sm font-semibold break-words">{{ person.person_name }}</h3><p class="stats-caption mt-1">{{ person.total_places }} 个{{ levelLabel }} · {{ person.total_photos.toLocaleString() }} 张照片 · {{ person.total_days }} 个记录日</p></div>
        </header>
        <div class="person-place-grid">
          <button v-for="place in expanded.has(person.person_id) ? person.places : person.places.slice(0, 3)" :key="place.place_key || place.scene_id || place.name" class="person-place-item text-left rounded-xl p-4" :aria-label="`查看${person.person_name}在${place.name}的 ${place.photo_count} 张照片`" @click="openPlace(person, place)">
            <div class="flex items-start justify-between gap-3"><span class="text-sm font-semibold break-words">{{ place.name }}</span><span class="text-sm font-semibold tabular-nums shrink-0">{{ place.photo_count.toLocaleString() }} <span class="stats-caption">张</span></span></div>
            <p v-if="place.parent_label" class="stats-caption mt-1">{{ place.parent_label }}</p>
            <div class="flex flex-wrap justify-between gap-2 mt-3 stats-caption"><span>{{ place.record_days }} 个记录日</span><span>{{ place.first_date ? `${place.first_date} 至 ${place.last_date}` : '暂无拍摄日期' }}</span></div>
            <div class="mt-3 h-1 rounded-full overflow-hidden" style="background:var(--ts-color-divider)"><div class="h-full bg-primary-500 rounded-full" :style="{ width: `${place.photo_count / Math.max(person.places[0]?.photo_count || 1, 1) * 100}%` }"></div></div>
          </button>
        </div>
        <button v-if="person.places.length > 3" class="ts-button ts-button-ghost ts-button-sm mt-2" :aria-expanded="expanded.has(person.person_id)" @click="toggle(person.person_id)">{{ expanded.has(person.person_id) ? '收起地点' : `查看${person.person_name}的全部 ${person.total_places} 个地点` }}</button>
      </section>
    </div>
    <p v-if="people.length && !loading && !error" class="stats-caption mt-1">按出现该人物的照片统计，点击地点查看对应照片。</p>
  </SurfaceCard>
</template>
<script setup lang="ts">
import { computed, reactive, ref, watch, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { UsersRound } from 'lucide-vue-next'
import SurfaceCard from '@/components/ui/SurfaceCard.vue'
import { locationService, type PersonPlaceStats, type TopPersonPlaces } from '@/api/location'
import { thumbnailUrl } from '@/utils/mediaUrl'
const props = defineProps<{ startDate?: string; endDate?: string; level: string; parentRegion?: string }>()
const router = useRouter()
const people = ref<TopPersonPlaces[]>([])
const loading = ref(true), error = ref(false)
const expanded = reactive(new Set<string>())
const failedCovers = reactive(new Set<string>())
let request = 0
const levelLabel = computed(() => (({ city: '城市', province: '省份', district: '区县', scene: '景区' } as Record<string, string>)[props.level] || '城市'))
async function fetchPeople() {
  const id = ++request
  loading.value = true; error.value = false; expanded.clear(); failedCovers.clear()
  try {
    const result = await locationService.getTopPersonPlaces(props.level, props.startDate, props.endDate, props.parentRegion)
    if (id === request) people.value = result
  } catch { if (id === request) error.value = true }
  finally { if (id === request) loading.value = false }
}
function toggle(id: string) { expanded.has(id) ? expanded.delete(id) : expanded.add(id) }
function openPlace(person: TopPersonPlaces, place: PersonPlaceStats) {
  router.push({ name: 'LocationDetail', params: { name: place.name }, query: {
    level: place.level, place_key: place.place_key || undefined, sceneId: place.scene_id || undefined,
    personId: person.person_id, personName: person.person_name, startDate: props.startDate, endDate: props.endDate,
  } })
}
watch(() => [props.level, props.startDate, props.endDate, props.parentRegion], fetchPeople, { immediate: true })
onBeforeUnmount(() => { request++ })
</script>
<style scoped>
.person-place-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 12px; }
.person-place-item { border: 1px solid var(--ts-color-border); background: var(--ts-color-surface); transition: background-color 160ms; }
.person-place-item:hover { background: var(--ts-color-surface-muted); }
</style>
