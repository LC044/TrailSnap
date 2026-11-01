<template>
  <header class="ts-settings-page-header">
    <div class="min-w-0 flex-1">
      <h1 class="ts-page-title">{{ title }}</h1>
      <p v-if="description" class="ts-muted mt-2 text-sm leading-6">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="ts-settings-page-actions ts-form-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>
