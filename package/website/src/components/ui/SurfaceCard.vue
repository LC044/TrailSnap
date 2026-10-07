<template>
  <component
    :is="as"
    class="ts-surface"
    :style="{ borderRadius: `var(--ts-radius-${radius})`, boxShadow: elevated ? undefined : 'none' }"
    :class="[
      paddingClass,
      interactive && 'ts-focus-ring cursor-pointer transition duration-200 hover:shadow-md',
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

</script>
