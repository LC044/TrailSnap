<template>
  <div 
    @click="onClick"
    class="ts-surface stats-card p-4 md:p-5"
    :class="[compact && 'stats-compact', clickable ? 'hover:shadow-md cursor-pointer group relative overflow-hidden' : '']"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable ? 0 : undefined"
    @keydown.enter.prevent="onClick"
    @keydown.space.prevent="onClick"
  >
    <div class="flex justify-between items-start z-10 relative">
      <div class="min-w-0">
        <div class="stats-value flex flex-wrap items-baseline gap-1">
          <slot name="value"></slot>
        </div>
        <p class="ts-muted text-xs mt-1">{{ label }}</p>
      </div>
      <div 
        class="stats-icon shrink-0"
        :class="['p-2 rounded-lg transition-colors', clickable ? 'bg-primary-50 dark:bg-slate-700 group-hover:bg-primary-500 group-hover:text-white' : 'bg-primary-50 dark:bg-slate-700']"
      >
        <component 
          :is="icon" 
          :class="['w-5 h-5 text-primary-600 dark:text-primary-400', clickable ? 'group-hover:text-white' : '']" 
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue';

interface Props {
  label: string;
  icon: Component;
  clickable?: boolean;
  compact?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  clickable: false
});

const emit = defineEmits<{
  (e: 'click'): void
}>();

const onClick = () => {
  if (props.clickable) emit('click');
};
</script>
<style scoped>
.stats-card:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 3px; }
@media (max-width: 639px) {
  .stats-compact { padding: 12px 8px; }
  .stats-compact .stats-icon { display: none; }
  .stats-compact .stats-value :deep(.text-3xl) { font-size: 18px; line-height: 1.4; }
  .stats-compact .stats-value :deep(.text-lg) { font-size: 14px; }
  .stats-compact .stats-value :deep(.text-sm) { font-size: 11px; }
  .stats-compact .stats-value :deep(.text-xs) { font-size: 10px; }
}
</style>
