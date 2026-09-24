<template>
  <ResponsiveDialog
    :model-value="modelValue"
    :title="title"
    :description="description"
    :close-on-backdrop="closeOnBackdrop"
    max-width="42rem"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <slot />

    <template #footer>
      <slot name="footer">
        <div class="flex items-center gap-3">
          <PrimaryButton variant="secondary" class="flex-1" @click="emit('reset')">
            {{ resetLabel }}
          </PrimaryButton>
          <PrimaryButton class="flex-[2]" :loading="loading" @click="emit('apply')">
            {{ resolvedApplyLabel }}
          </PrimaryButton>
        </div>
      </slot>
    </template>
  </ResponsiveDialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import PrimaryButton from '@/components/ui/PrimaryButton.vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title?: string
  description?: string
  resultCount?: number
  applyLabel?: string
  resetLabel?: string
  loading?: boolean
  closeOnBackdrop?: boolean
}>(), {
  title: '筛选',
  resetLabel: '重置',
  loading: false,
  closeOnBackdrop: true,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  apply: []
  reset: []
}>()

const resolvedApplyLabel = computed(() => {
  if (props.applyLabel) return props.applyLabel
  return props.resultCount === undefined ? '应用筛选' : `查看 ${props.resultCount} 张照片`
})
</script>
