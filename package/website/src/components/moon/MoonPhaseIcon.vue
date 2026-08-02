<template>
  <svg viewBox="0 0 48 48" role="img" :aria-label="label" class="block">
    <defs>
      <clipPath :id="clipId">
        <circle cx="24" cy="24" r="19" />
      </clipPath>
    </defs>
    <circle cx="24" cy="24" r="20" class="fill-gray-950 stroke-gray-600 dark:fill-gray-950 dark:stroke-gray-500" stroke-width="1.5" />
    <g :clip-path="`url(#${clipId})`" class="fill-gray-50 dark:fill-gray-100">
      <circle v-if="phase === 'full_moon'" cx="24" cy="24" r="19" />
      <path v-else-if="phase === 'first_quarter'" d="M24 5a19 19 0 0 1 0 38z" />
      <path v-else-if="phase === 'last_quarter'" d="M24 5a19 19 0 0 0 0 38z" />
      <path v-else-if="phase === 'waxing_crescent'" d="M24 5a19 19 0 1 1 0 38c8-5 11-12 11-19S32 10 24 5z" />
      <path v-else-if="phase === 'waxing_gibbous'" d="M24 5a19 19 0 1 1 0 38c-5-5-7-12-7-19s2-14 7-19z" />
      <path v-else-if="phase === 'waning_gibbous'" d="M24 5a19 19 0 1 0 0 38c5-5 7-12 7-19s-2-14-7-19z" />
      <path v-else-if="phase === 'waning_crescent'" d="M24 5a19 19 0 1 0 0 38c-8-5-11-12-11-19S16 10 24 5z" />
    </g>
  </svg>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue'
import type { MoonPhase } from '@/types/moon'
import { MOON_PHASES } from '@/composables/useMoonPhase'

const props = defineProps<{ phase: MoonPhase }>()
const clipId = `moon-phase-${useId().replace(/:/g, '')}`
const label = computed(() => MOON_PHASES.find((item) => item.phase === props.phase)?.label ?? '月相')
</script>
