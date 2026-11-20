<template>
  <component
    v-glass-refraction
    :is="to ? RouterLink : 'button'"
    :to="to"
    :type="to ? undefined : 'button'"
    :aria-label="label"
    :title="label"
    :disabled="to ? undefined : disabled"
    class="ts-back-button ts-liquid-glass ts-glass-toolbar"
  >
    <ChevronLeft aria-hidden="true" class="h-6 w-6" />
  </component>
</template>

<script setup lang="ts">
import { ChevronLeft } from 'lucide-vue-next'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

withDefaults(defineProps<{ label?: string; disabled?: boolean; to?: RouteLocationRaw }>(), {
  label: '返回',
  disabled: false,
})
</script>

<style scoped>
@layer ts-control-layout {
  .ts-back-button.ts-glass-toolbar { display: inline-flex; }
}
.ts-back-button {
  width: 44px;
  height: 44px;
  justify-content: center;
  padding: 0;
  cursor: pointer;
  transition: transform var(--ts-motion-fast) var(--ts-ease);
}
.ts-back-button:active { transform: scale(.96); }
.ts-back-button:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 2px; }
.ts-back-button:disabled { opacity: .4; cursor: not-allowed; transform: none; }
@media (max-width: 767px) {
  .ts-back-button {
    width: 36px;
    height: 36px;
  }
  .ts-back-button::after { content: ''; position: absolute; inset: -4px; }
  .ts-back-button > svg { width: 20px; height: 20px; }
}
</style>
