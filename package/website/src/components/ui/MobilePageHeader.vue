<template>
  <PageHeader
    :title="title"
    :subtitle="subtitle"
    :fallback="fallback"
    :show-back="showBack"
    :sticky="sticky"
    mobile-only
    size="full"
    @back="emit('back')"
  >
    <template v-if="$slots.leading" #leading><slot name="leading" /></template>
    <template v-if="$slots.actions" #actions><slot name="actions" /></template>
  </PageHeader>
</template>

<script setup lang="ts">
import PageHeader from '@/components/ui/PageHeader.vue'

const props = withDefaults(defineProps<{
  title: string
  subtitle?: string
  fallback?: string
  showBack?: boolean
  sticky?: boolean
}>(), {
  fallback: '/',
  showBack: true,
  sticky: true,
})

const emit = defineEmits<{ back: [] }>()
</script>
