<template>
  <RouterLink :to="link" class="flex items-center gap-4 rounded-xl border border-primary-200 bg-primary-50 p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-primary-900 dark:bg-primary-900/20">
    <img v-if="frame?.available && frame.photo_id && !frame.removed" :src="thumbnailUrl(frame.photo_id)" alt="今天的一帧" class="h-14 w-14 rounded-lg object-cover" />
    <span v-else class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary-100 text-primary-600 dark:bg-primary-900 dark:text-primary-300"><Film class="h-6 w-6" /></span>
    <div class="min-w-0 flex-1"><h2 class="text-sm font-semibold text-primary-800 dark:text-primary-200">{{ frame?.available && !frame.removed ? '今天的瞬间已留下' : '为今天留一个瞬间' }}</h2><p class="mt-1 text-xs text-primary-600 dark:text-primary-300">{{ frame?.available && !frame.removed ? '查看本月 · 一日一帧' : '每天一秒，把生活拼成一部影片' }}</p></div>
    <ChevronRight class="h-5 w-5 text-primary-500" />
  </RouterLink>
</template>

<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { Film, ChevronRight } from 'lucide-vue-next'
import { dailyFrameApi } from '@/api/dailyFrame'
import { thumbnailUrl } from '@/utils/mediaUrl'
import type { DailyFrame } from '@/types/dailyFrame'
const frame = ref<DailyFrame | null>(null), day = ref('')
const link = computed(() => frame.value?.available && !frame.value.removed ? '/daily-frame' : day.value ? `/daily-frame?day=${day.value}` : '/daily-frame')
let loading = false
async function load() {
  if (loading) return
  loading = true
  try {
    const settings = await dailyFrameApi.settings()
    if (settings.initialized && settings.today) { day.value = settings.today; frame.value = await dailyFrameApi.day(day.value) }
  } catch { /* The entry stays usable when the optional status request fails. */ } finally { loading = false }
}
onMounted(() => void load())
onActivated(() => void load())
</script>
