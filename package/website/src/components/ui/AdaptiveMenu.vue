<template>
  <ResponsiveDialog v-if="mobile" :model-value="modelValue" :title="title" @update:model-value="emit('update:modelValue', $event)" glass>
    <div class="ts-action-content" @click="closeAfterAction"><slot /></div>
  </ResponsiveDialog>
  <div v-else-if="modelValue" class="ts-liquid-glass ts-desktop-menu" @click="closeAfterAction"><slot /></div>
</template>

<script setup lang="ts">
import { useMediaQuery } from '@vueuse/core'
import ResponsiveDialog from './ResponsiveDialog.vue'
const props = withDefaults(defineProps<{ modelValue: boolean; title: string; closeOnAction?: boolean }>(), { closeOnAction: false })
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const mobile = useMediaQuery('(max-width: 639px)')
const closeAfterAction = (event: MouseEvent) => {
  if (props.closeOnAction && (event.target as HTMLElement).closest('button:not(:disabled)')) emit('update:modelValue', false)
}
</script>
