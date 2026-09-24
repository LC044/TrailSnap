<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    class="inline-flex select-none items-center justify-center gap-2 rounded-[var(--ts-radius-control)] font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:scale-[.98] disabled:pointer-events-none disabled:opacity-50 dark:focus-visible:ring-offset-gray-900"
    :class="[sizeClass, variantClass, block && 'w-full']"
  >
    <span v-if="loading" class="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" aria-hidden="true" />
    <slot name="leading" />
    <span><slot /></span>
    <slot name="trailing" />
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  type?: 'button' | 'submit' | 'reset'
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  loading?: boolean
  block?: boolean
}>(), {
  type: 'button',
  variant: 'primary',
  size: 'md',
  disabled: false,
  loading: false,
  block: false,
})

const sizeClass = computed(() => ({
  sm: 'min-h-9 px-3 text-sm',
  md: 'min-h-11 px-4 text-sm',
  lg: 'min-h-12 px-5 text-base',
}[props.size]))

const variantClass = computed(() => ({
  primary: 'bg-primary-500 text-white shadow-sm shadow-primary-500/20 hover:bg-primary-600',
  secondary: 'border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700',
  ghost: 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800',
  danger: 'bg-red-500 text-white shadow-sm hover:bg-red-600',
}[props.variant]))
</script>
