<template>
  <div class="settings-form-row" :class="{ 'settings-form-row-inline': inline }">
    <div class="min-w-0">
      <label :id="labelId" :for="controlId" class="text-sm font-medium">{{ label }}</label>
      <p v-if="description" class="ts-muted mt-1 text-xs leading-5">{{ description }}</p>
    </div>
    <div class="settings-form-control min-w-0" role="group" :aria-label="label"><slot /></div>
  </div>
</template>
<script setup lang="ts">
defineProps<{ label: string; description?: string; labelId?: string; controlId?: string; inline?: boolean }>()
</script>
<style scoped>
.settings-form-row { display: grid; gap: 8px; padding-block: 10px; }
.settings-form-row-inline { grid-template-columns: minmax(0, 1fr) auto; align-items: center; column-gap: 12px; }
.settings-form-row-inline .settings-form-control { justify-content: flex-end; }
.settings-form-control { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
@container settings-content (min-width: 520px) {
  .settings-form-row { grid-template-columns: minmax(160px, 1fr) minmax(0, 1.3fr); align-items: center; column-gap: 24px; }
  .settings-form-control { justify-content: flex-end; }
}
</style>
