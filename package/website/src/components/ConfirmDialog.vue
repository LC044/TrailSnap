<template>
  <ResponsiveDialog
    :model-value="visible"
    :title="title"
    max-width="24rem"
    @update:model-value="value => !value && cancel()"
  >
    <p class="text-sm text-gray-600 dark:text-gray-300">{{ message }}</p>
    <template #footer>
          <div class="flex gap-3 justify-end">
             <button 
               @click="cancel"
               class="ts-button ts-button-secondary"
             >
               {{ cancelText }}
             </button>
             <button 
               @click="confirm"
               class="ts-button"
               :class="type === 'danger' ? 'ts-button-danger' : 'ts-button-primary'"
             >
               {{ confirmText }}
             </button>
          </div>
    </template>
  </ResponsiveDialog>
</template>

<script setup lang="ts">
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
const props = withDefaults(defineProps<{
  visible: boolean
  title?: string
  message?: string
  confirmText?: string
  cancelText?: string
  type?: 'danger' | 'primary'
}>(), {
  title: '提示',
  message: '',
  confirmText: '确认',
  cancelText: '取消',
  type: 'danger'
})

const emit = defineEmits(['update:visible', 'confirm', 'cancel'])

const cancel = () => {
  emit('update:visible', false)
  emit('cancel')
}

const confirm = () => {
  emit('update:visible', false)
  emit('confirm')
}
</script>
