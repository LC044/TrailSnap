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
               class="px-4 py-2 text-gray-600 dark:text-gray-300 dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors font-medium text-sm"
             >
               {{ cancelText }}
             </button>
             <button 
               @click="confirm"
               class="px-4 py-2 text-white rounded-lg transition-colors shadow-lg font-medium text-sm"
               :class="type === 'danger' ? 'bg-red-500 hover:bg-red-600 shadow-red-500/30' : 'bg-primary-500 hover:bg-primary-600 shadow-primary-500/30'"
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
