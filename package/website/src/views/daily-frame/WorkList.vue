<template>
  <section class="space-y-4">
    <div class="flex items-center justify-between"><h2 class="text-lg font-semibold">我的影片</h2><button class="df-button" type="button" :disabled="loading" @click="load(true)">刷新</button></div>
    <p v-if="error" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
    <div v-if="!items.length && !loading" class="df-panel py-14 text-center text-gray-500 dark:text-gray-400">还没有影片，先为几天选帧，再制作一部回忆影片。</div>
    <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <RouterLink v-for="work in items" :key="work.id" :to="`/daily-frame/works/${work.id}`" class="df-panel block transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500">
        <div class="mb-3 flex aspect-video items-center justify-center overflow-hidden rounded-xl bg-primary-50 dark:bg-primary-900/20"><img v-if="posters[work.id]" :src="posters[work.id]" alt="影片第一帧" class="h-full w-full object-contain" /><Film v-else class="h-12 w-12 text-primary-500" /></div>
        <h3 class="truncate font-semibold">{{ work.settings.title }}</h3>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{{ work.settings.start_date }} — {{ work.settings.end_date }}</p>
        <div class="mt-3 flex justify-between text-sm"><span>{{ work.duration }} 个瞬间 · {{ work.duration }} 秒</span><span class="text-primary-600 dark:text-primary-400">{{ workStatus(work.status) }}</span></div>
        <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">{{ work.settings.orientation === 'portrait' ? '竖屏' : '横屏' }} · {{ work.created_at.slice(0, 16).replace('T', ' ') }}</p>
      </RouterLink>
    </div>
    <button v-if="items.length < total" class="df-button w-full" type="button" :disabled="loading" @click="load(false)">加载更多</button>
  </section>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { Film } from 'lucide-vue-next'
import { dailyFrameApi, dailyFrameError } from '@/api/dailyFrame'
import { workStatus } from '@/utils/dailyFrame'
import type { DailyFilmWork } from '@/types/dailyFrame'
const items = ref<DailyFilmWork[]>([]), total = ref(0), loading = ref(false), error = ref('')
const posters = ref<Record<string, string>>({})
const posterLoading = new Set<string>()
let timer: ReturnType<typeof setTimeout> | undefined
let mounted = true
async function load(reset: boolean) {
  if (loading.value) return
  clearTimeout(timer); loading.value = true; error.value = ''
  try {
    const result = await dailyFrameApi.works(reset ? 0 : items.value.length)
    if (!mounted) return
    items.value = reset ? result.items : [...items.value, ...result.items]; total.value = result.total
    for (const work of items.value) if (work.file_available && !posters.value[work.id] && !posterLoading.has(work.id)) {
      posterLoading.add(work.id)
      void dailyFrameApi.poster(work.id).then(blob => {
        if (mounted) posters.value[work.id] = URL.createObjectURL(blob)
      }).catch(() => {}).finally(() => posterLoading.delete(work.id))
    }
    if (items.value.some(item => ['queued', 'processing'].includes(item.status))) timer = setTimeout(() => void load(true), 4000)
  } catch (err) { error.value = dailyFrameError(err) } finally { loading.value = false }
}
onMounted(() => void load(true))
onBeforeUnmount(() => { mounted = false; clearTimeout(timer); Object.values(posters.value).forEach(URL.revokeObjectURL) })
</script>
