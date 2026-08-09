<template>
  <button
    :type="type"
    :aria-label="label"
    :title="title || label"
    :disabled="disabled"
    class="inline-flex shrink-0 items-center justify-center rounded-xl transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 dark:focus-visible:ring-offset-gray-900"
    :class="[sizeClass, variantClass]"
  >
    <slot />
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  label: string
  title?: string
  type?: 'button' | 'submit' | 'reset'
  size?: 'sm' | 'md' | 'lg'
  variant?: 'ghost' | 'primary' | 'danger'
  disabled?: boolean
}>(), {
  type: 'button',
  size: 'md',
  variant: 'ghost',
  disabled: false,
})

const sizeClass = computed(() => ({
  sm: 'h-8 w-8',
  md: 'h-10 w-10',
  lg: 'h-12 w-12',
}[props.size]))

const variantClass = computed(() => ({
  ghost: 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-white',
  primary: 'bg-primary-500 text-white shadow-sm hover:bg-primary-600',
  danger: 'text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40',
}[props.variant]))
</script>
