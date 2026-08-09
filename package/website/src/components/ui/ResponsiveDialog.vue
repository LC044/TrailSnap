<template>
  <Teleport to="body">
    <Transition name="responsive-dialog">
      <div
        v-if="modelValue"
        class="fixed inset-0 z-[110] flex items-end justify-center md:items-center md:p-6"
        role="presentation"
      >
        <button
          class="absolute inset-0 cursor-default bg-black/50 backdrop-blur-sm focus:outline-none"
          type="button"
          aria-label="关闭弹窗"
          tabindex="-1"
          @click="closeOnBackdrop && close()"
        />
        <section
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          class="relative z-10 flex max-h-[90dvh] w-full flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl dark:bg-gray-900 md:rounded-2xl"
          :style="{ maxWidth }"
        >
          <div class="mx-auto mt-2 h-1 w-10 rounded-full bg-gray-300 dark:bg-gray-700 md:hidden" />
          <header class="flex min-h-14 items-center gap-3 border-b border-gray-100 px-4 dark:border-gray-800">
            <div class="min-w-0 flex-1">
              <h2 :id="titleId" class="truncate text-base font-semibold text-gray-900 dark:text-white">{{ title }}</h2>
              <p v-if="description" class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{{ description }}</p>
            </div>
            <IconButton label="关闭" size="sm" @click="close">
              <X class="h-4 w-4" />
            </IconButton>
          </header>
          <div class="min-h-0 flex-1 overflow-y-auto p-4">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="border-t border-gray-100 p-4 dark:border-gray-800">
            <slot name="footer" />
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'
import { X } from 'lucide-vue-next'
import IconButton from '@/components/ui/IconButton.vue'
import { useOverlayStack } from '@/composables/useOverlayStack'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title: string
  description?: string
  maxWidth?: string
  closeOnBackdrop?: boolean
  closeOnEscape?: boolean
}>(), {
  maxWidth: '32rem',
  closeOnBackdrop: true,
  closeOnEscape: true,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  close: []
}>()

const visible = computed(() => props.modelValue)
const titleId = `responsive-dialog-${Math.random().toString(36).slice(2)}`

const close = () => {
  emit('update:modelValue', false)
  emit('close')
}

useOverlayStack(visible, close)

const onKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && props.modelValue && props.closeOnEscape) close()
}

watch(visible, (isVisible) => {
  if (isVisible) window.addEventListener('keydown', onKeydown)
  else window.removeEventListener('keydown', onKeydown)
}, { immediate: true })

onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.responsive-dialog-enter-active,
.responsive-dialog-leave-active { transition: opacity 0.2s ease; }
.responsive-dialog-enter-active section,
.responsive-dialog-leave-active section { transition: transform 0.2s ease, opacity 0.2s ease; }
.responsive-dialog-enter-from,
.responsive-dialog-leave-to { opacity: 0; }
.responsive-dialog-enter-from section,
.responsive-dialog-leave-to section { transform: translateY(1.5rem); opacity: 0; }
@media (min-width: 768px) {
  .responsive-dialog-enter-from section,
  .responsive-dialog-leave-to section { transform: translateY(0.5rem) scale(0.98); }
}
</style>
