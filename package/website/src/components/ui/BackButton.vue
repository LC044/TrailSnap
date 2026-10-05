<template>
  <component
    :is="to ? RouterLink : 'button'"
    :to="to"
    :type="to ? undefined : 'button'"
    :aria-label="label"
    :title="label"
    :disabled="to ? undefined : disabled"
    class="ts-back-button"
  >
    <ChevronLeft class="h-6 w-6" />
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
  .ts-back-button { display: inline-flex; }
}
.ts-back-button {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 1px solid var(--ts-color-border);
  border-radius: 999px;
  color: var(--ts-color-text);
  background: var(--ts-glass-bg);
  box-shadow: var(--ts-shadow-glass);
  cursor: pointer;
  transition: transform var(--ts-motion-fast) var(--ts-ease);
}
.ts-back-button:active { transform: scale(.96); }
.ts-back-button:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 2px; }
.ts-back-button:disabled { opacity: .4; cursor: not-allowed; transform: none; }
</style>
