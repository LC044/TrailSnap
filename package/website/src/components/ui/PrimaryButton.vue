<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
    class="ts-button select-none"
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
  sm: 'ts-button-sm',
  md: '',
  lg: 'ts-button-lg',
}[props.size]))

const variantClass = computed(() => ({
  primary: 'ts-button-primary',
  secondary: 'ts-button-secondary',
  ghost: 'ts-button-ghost',
  danger: 'ts-button-danger',
}[props.variant]))
</script>
