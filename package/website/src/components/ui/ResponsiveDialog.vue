<template>
  <Teleport to="body">
    <Transition name="responsive-dialog">
      <div
        v-if="modelValue"
        class="fixed inset-0 z-[110] flex items-end justify-center md:items-center md:p-6"
        role="presentation"
      >
        <button
          class="absolute inset-0 cursor-default bg-[var(--ts-color-overlay)] backdrop-blur-sm focus:outline-none"
          type="button"
          aria-label="关闭弹窗"
          tabindex="-1"
          @click="closeOnBackdrop && close()"
        />
        <section
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          class="responsive-dialog-panel relative z-10 flex w-full flex-col overflow-hidden bg-white shadow-[var(--ts-shadow-floating)] dark:bg-gray-900 md:max-h-[90dvh] md:rounded-[var(--ts-radius-dialog)]"
          :class="mobileMode === 'fullscreen' ? 'mobile-fullscreen h-[100dvh] rounded-none' : 'max-h-[92dvh] rounded-t-[var(--ts-radius-dialog)]'"
          :style="{ '--responsive-dialog-max-width': maxWidth }"
        >
          <div v-if="mobileMode === 'sheet'" class="mx-auto mt-2 h-1 w-10 rounded-full bg-gray-300 dark:bg-gray-700 md:hidden" />
          <header class="responsive-dialog-header flex min-h-14 items-center gap-3 border-b border-gray-100 px-4 dark:border-gray-800 md:px-5">
            <IconButton v-if="mobileBack" class="md:hidden" label="返回" size="sm" @click="close">
              <ChevronLeft class="h-5 w-5" />
            </IconButton>
            <div class="min-w-0 flex-1">
              <h2 :id="titleId" class="truncate text-base font-semibold text-gray-900 dark:text-white">{{ title }}</h2>
              <p v-if="description" class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{{ description }}</p>
            </div>
            <IconButton :class="{ 'hidden md:inline-flex': mobileBack }" label="关闭" size="sm" @click="close">
              <X class="h-4 w-4" />
            </IconButton>
          </header>
          <div class="responsive-dialog-body min-h-0 flex-1 overflow-y-auto p-4 md:p-5">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="border-t border-gray-100 bg-white p-4 pb-[calc(1rem_+_env(safe-area-inset-bottom))] dark:border-gray-800 dark:bg-gray-900 md:p-5">
            <slot name="footer" />
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'
import { ChevronLeft, X } from 'lucide-vue-next'
import IconButton from '@/components/ui/IconButton.vue'
import { useOverlayStack } from '@/composables/useOverlayStack'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title: string
  description?: string
  maxWidth?: string
  mobileMode?: 'sheet' | 'fullscreen'
  mobileBack?: boolean
  closeOnBackdrop?: boolean
  closeOnEscape?: boolean
}>(), {
  maxWidth: '32rem',
  mobileMode: 'sheet',
  mobileBack: false,
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
.responsive-dialog-panel { max-width: 100%; }
.responsive-dialog-enter-active,
.responsive-dialog-leave-active { transition: opacity 0.2s ease; }
.responsive-dialog-enter-active section,
.responsive-dialog-leave-active section { transition: transform 0.2s ease, opacity 0.2s ease; }
.responsive-dialog-enter-from,
.responsive-dialog-leave-to { opacity: 0; }
.responsive-dialog-enter-from section,
.responsive-dialog-leave-to section { transform: translateY(1.5rem); opacity: 0; }
@media (max-width: 767px) {
  .mobile-fullscreen .responsive-dialog-header {
    min-height: calc(3.5rem + env(safe-area-inset-top));
    padding-top: env(safe-area-inset-top);
  }
  .mobile-fullscreen .responsive-dialog-body {
    padding-bottom: calc(1rem + env(safe-area-inset-bottom));
  }
  .responsive-dialog-enter-active .mobile-fullscreen,
  .responsive-dialog-leave-active .mobile-fullscreen {
    transition: transform 0.28s cubic-bezier(0.32, 0.72, 0, 1);
  }
  .responsive-dialog-enter-from .mobile-fullscreen,
  .responsive-dialog-leave-to .mobile-fullscreen {
    transform: translateX(100%);
    opacity: 1;
  }
}
@media (min-width: 768px) {
  .responsive-dialog-panel { max-width: var(--responsive-dialog-max-width); }
  .responsive-dialog-enter-from section,
  .responsive-dialog-leave-to section { transform: translateY(0.5rem) scale(0.98); }
}
</style>
