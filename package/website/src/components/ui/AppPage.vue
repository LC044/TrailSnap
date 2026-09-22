<template>
  <div
    class="mx-auto w-full"
    :class="[widthClass, padded && 'px-[var(--ts-page-gutter)]', bottomSafe && 'ts-bottom-safe']"
  >
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  size?: 'full' | 'wide' | 'content' | 'form'
  padded?: boolean
  bottomSafe?: boolean
}>(), {
  size: 'content',
  padded: true,
  bottomSafe: false,
})

const widthClass = computed(() => ({
  full: 'max-w-none',
  wide: 'max-w-screen-2xl',
  content: 'max-w-7xl',
  form: 'max-w-4xl',
}[props.size]))
</script>
