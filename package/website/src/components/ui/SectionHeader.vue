<template>
  <div class="flex min-w-0 flex-wrap items-center justify-between gap-3">
    <div class="min-w-0">
      <div class="flex items-center gap-2">
        <span v-if="$slots.icon" class="shrink-0 text-primary-500"><slot name="icon" /></span>
        <h2 class="ts-section-title truncate">{{ title }}</h2>
      </div>
      <p v-if="description" class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="shrink-0"><slot name="actions" /></div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>
