<template>
  <div ref="sentinel" class="min-h-px min-w-px shrink-0" aria-hidden="true"></div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useIntersectionObserver } from '@vueuse/core'

const emit = defineEmits<{ load: [] }>()
const sentinel = ref<HTMLElement>()
useIntersectionObserver(sentinel, ([entry]) => {
  if (entry?.isIntersecting) emit('load')
})
</script>
