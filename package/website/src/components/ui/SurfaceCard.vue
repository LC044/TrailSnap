<template>
  <component
    :is="as"
    class="border border-gray-200/80 bg-white text-gray-900 dark:border-gray-800 dark:bg-gray-800 dark:text-gray-100"
    :class="[
      radiusClass,
      paddingClass,
      elevated && 'shadow-[var(--ts-shadow-card)]',
      interactive && 'ts-focus-ring cursor-pointer transition duration-200 hover:-translate-y-0.5 hover:shadow-md',
    ]"
  >
    <slot />
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  as?: string
  padding?: 'none' | 'sm' | 'md' | 'lg'
  radius?: 'control' | 'card' | 'dialog'
  elevated?: boolean
  interactive?: boolean
}>(), {
  as: 'section',
  padding: 'md',
  radius: 'card',
  elevated: true,
  interactive: false,
})

const paddingClass = computed(() => ({
  none: '',
  sm: 'p-3',
  md: 'p-4 md:p-5',
  lg: 'p-5 md:p-6',
}[props.padding]))

const radiusClass = computed(() => ({
  control: 'rounded-[var(--ts-radius-control)]',
  card: 'rounded-[var(--ts-radius-card)]',
  dialog: 'rounded-[var(--ts-radius-dialog)]',
}[props.radius]))
</script>
