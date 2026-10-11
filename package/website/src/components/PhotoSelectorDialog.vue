<template>
  <ResponsiveDialog
    v-model="visible"
    :title="title"
    max-width="80rem"
    mobile-mode="fullscreen"
    mobile-back
    :before-close="() => !busy"
    panel-class="photo-selector-dialog"
  >
    <PhotoSelector
      v-if="visible"
      :is-selector="true"
      :store="store"
      :title="title"
      embedded
      :single-select="singleSelect"
      :busy="busy"
      @select="$emit('select', $event)"
      @cancel="visible = false"
    />
  </ResponsiveDialog>
</template>

<script setup lang="ts">
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import PhotoSelector from '@/components/PhotoSelector.vue'
const visible = defineModel<boolean>({ required: true })
defineProps<{ title: string; store?: any; singleSelect?: boolean; busy?: boolean }>()
defineEmits<{ select: [ids: string[]] }>()
</script>

<style>
.photo-selector-dialog.responsive-dialog-panel .responsive-dialog-body { display: flex; overflow: hidden; padding: 0; }
.photo-selector-dialog.responsive-dialog-panel.mobile-fullscreen .responsive-dialog-body { padding: 0; }
.photo-selector-dialog .photo-selector-container { flex: 1; min-height: 0; padding-bottom: var(--ts-safe-area-bottom); }
@media (min-width: 768px) {
  .photo-selector-dialog.responsive-dialog-panel { height: 90dvh; }
}
</style>
