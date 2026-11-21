<template>
  <RouterLink :to="link" class="lm-tile lm-tile--frame">
    <span class="lm-tile-art" aria-hidden="true">
      <img v-if="framePhoto" :src="thumbnailUrl(framePhoto)" alt="" loading="lazy" @error="failedPhoto = framePhoto" />
      <i v-else></i><i></i><i></i>
    </span>
    <span class="lm-tile-body">
      <span class="lm-tile-icon"><Film class="h-4 w-4" /></span>
      <span class="lm-tile-text">
        <strong>一日一帧</strong>
        <span>{{ frameReady ? '今天已留下一帧' : '留下今天的一帧' }}</span>
      </span>
      <ArrowUpRight class="lm-tile-arrow" aria-hidden="true" />
    </span>
  </RouterLink>
</template>

<script setup lang="ts">
import { computed, onActivated, ref } from 'vue'
import { ArrowUpRight, Film } from 'lucide-vue-next'
import { dailyFrameApi } from '@/api/dailyFrame'
import { thumbnailUrl } from '@/utils/mediaUrl'
import type { DailyFrame } from '@/types/dailyFrame'

const frame = ref<DailyFrame | null>(null)
const day = ref('')
const failedPhoto = ref<string | null>(null)
const frameReady = computed(() => Boolean(frame.value?.available && !frame.value.removed))
const framePhoto = computed(() => frameReady.value && frame.value?.photo_id !== failedPhoto.value ? frame.value?.photo_id ?? null : null)
const link = computed(() => frameReady.value || !day.value ? '/daily-frame' : `/daily-frame?day=${day.value}`)

let loading = false
async function load() {
  if (loading) return
  loading = true
  try {
    const settings = await dailyFrameApi.settings()
    day.value = settings.initialized ? settings.today || '' : ''
    frame.value = day.value ? await dailyFrameApi.day(day.value) : null
  } catch {
    // The calendar link is still available if the daily frame request fails.
  } finally {
    loading = false
  }
}

onActivated(() => void load())
</script>