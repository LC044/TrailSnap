<template>
  <span v-if="enabled" ref="start" aria-hidden="true" class="pointer-events-none block h-px -mb-px shrink-0"></span>
  <header
    v-bind="$attrs"
    v-glass-refraction.rim="glass"
    :class="{ 'scroll-glass-header': enabled, 'ts-liquid-glass': glass }"
  >
    <slot />
  </header>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useIntersectionObserver } from '@vueuse/core'

defineOptions({ inheritAttrs: false })
const props = withDefaults(defineProps<{ enabled?: boolean }>(), { enabled: true })
const start = ref<HTMLElement | null>(null)
const scrolled = ref(false)
const glass = computed(() => props.enabled && scrolled.value)

useIntersectionObserver(start, ([entry]) => {
  if (entry) scrolled.value = !entry.isIntersecting
})
</script>

<style scoped>
.scroll-glass-header {
  position: sticky;
  top: 0;
  z-index: 30;
  --glass-tint: var(--ts-glass-bg);
  --glass-blur: var(--ts-glass-blur-panel);
}
.scroll-glass-header:not(.ts-liquid-glass) {
  background: var(--ts-color-page);
  border: var(--ts-border-unit, 1px) solid transparent;
  border-bottom-color: var(--ts-color-divider);
}
</style>
