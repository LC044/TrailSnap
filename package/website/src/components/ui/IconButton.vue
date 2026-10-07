<template>
  <button
    :type="type"
    :aria-label="label"
    :title="title || label"
    :disabled="disabled"
    class="ts-icon-button"
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
  sm: 'ts-button-sm',
  md: '',
  lg: 'ts-button-lg',
}[props.size]))

const variantClass = computed(() => ({
  ghost: 'ts-button-ghost',
  primary: 'ts-button-primary',
  danger: 'ts-icon-danger',
}[props.variant]))
</script>
