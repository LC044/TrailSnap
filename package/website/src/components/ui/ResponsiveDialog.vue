<template>
  <Teleport to="body">
    <Transition name="responsive-dialog">
      <div
        v-if="modelValue"
        class="fixed inset-0 z-[110] flex items-end justify-center md:items-center md:p-6"
        role="presentation"
        :style="{ visibility: navigationDismissed ? 'hidden' : undefined, height: `${viewportHeight}px`, top: `${viewportTop}px`, '--dialog-viewport-height': `${viewportHeight}px` }"
        @wheel.self.prevent
        :class="{ 'responsive-dialog-right': placement === 'right' }"
      >
        <button
          class="absolute inset-0 cursor-default bg-[var(--ts-color-overlay)] focus:outline-none"
          type="button"
          aria-label="关闭弹窗"
          tabindex="-1"
          @click="closeOnBackdrop && close()"
        />
        <section
          ref="panelRef"
          tabindex="-1"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          class="responsive-dialog-panel relative z-10 flex w-full flex-col overflow-hidden bg-[var(--ts-color-surface)] shadow-[var(--ts-shadow-floating)] md:max-h-[90dvh] md:rounded-[var(--ts-radius-dialog)]"
          :class="[glass ? 'ts-liquid-glass ts-glass-sheet' : '', mobileMode === 'fullscreen' ? 'mobile-fullscreen h-[100dvh] rounded-none' : 'max-h-[92dvh] rounded-t-[var(--ts-radius-dialog)]']"
          :style="{ '--responsive-dialog-max-width': maxWidth, ...sheet.style.value }"
        >
          <div v-if="mobileMode === 'sheet'" class="sheet-drag-zone flex h-7 shrink-0 items-center justify-center md:hidden" @pointerdown="sheet.start" @pointermove="sheet.move" @pointerup="sheet.finish" @pointercancel="sheet.finish" @lostpointercapture="sheet.finish">
            <span class="h-1 w-10 rounded-full bg-gray-300 dark:bg-gray-700" />
          </div>
          <header class="responsive-dialog-header ts-divider flex min-h-[var(--ts-header-height)] shrink-0 items-center gap-3 border-b px-4 md:px-6" :class="{ 'sheet-drag-zone': mobileMode === 'sheet' }" @pointerdown="sheet.start" @pointermove="sheet.move" @pointerup="sheet.finish" @pointercancel="sheet.finish" @lostpointercapture="sheet.finish">
            <BackButton v-if="mobileBack" class="md:hidden" label="返回" @click="close" />
            <div class="min-w-0 flex-1">
              <h2 :id="titleId" class="truncate text-base font-semibold text-[var(--ts-color-text)]">{{ title }}</h2>
              <p v-if="description" class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{{ description }}</p>
            </div>
            <IconButton :class="{ 'hidden md:inline-flex': mobileBack }" label="关闭" size="sm" @click="close">
              <X class="h-4 w-4" />
            </IconButton>
          </header>
          <div class="responsive-dialog-body min-h-0 flex-1 overflow-y-auto p-4 md:p-6" :class="!$slots.footer && 'pb-[calc(1rem_+_var(--ts-safe-area-bottom))] md:pb-6'">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="ts-divider shrink-0 border-t p-4 pb-[calc(1rem_+_var(--ts-safe-area-bottom))] md:p-6">
            <slot name="footer" />
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import BackButton from '@/components/ui/BackButton.vue'
import { computed, nextTick, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { X } from 'lucide-vue-next'
import IconButton from '@/components/ui/IconButton.vue'
import { useOverlayStack } from '@/composables/useOverlayStack'
import { useSheetGesture } from '@/composables/useSheetGesture'
import { useRouteDismiss } from '@/composables/useRouteDismiss'
import { isTopOverlay } from '@/composables/useOverlayStack'
import { useModalScrollLock } from '@/composables/useModalScrollLock'
import { useDialogHistory } from '@/composables/useDialogHistory'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title: string
  description?: string
  maxWidth?: string
  mobileMode?: 'sheet' | 'fullscreen'
  mobileBack?: boolean
  closeOnBackdrop?: boolean
  closeOnEscape?: boolean
  glass?: boolean
  placement?: 'center' | 'right'
  beforeClose?: () => boolean | Promise<boolean>
  history?: boolean
}>(), {
  maxWidth: '32rem',
  mobileMode: 'sheet',
  mobileBack: false,
  closeOnBackdrop: true,
  closeOnEscape: true,
  glass: true,
  placement: 'center',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  close: []
}>()

const panelRef = ref<HTMLElement | null>(null)
const viewportHeight = ref(window.visualViewport?.height ?? window.innerHeight)
const viewportTop = ref(window.visualViewport?.offsetTop ?? 0)
const updateViewport = () => { viewportHeight.value = window.visualViewport?.height ?? window.innerHeight; viewportTop.value = window.visualViewport?.offsetTop ?? 0 }
window.addEventListener('resize', updateViewport)
window.visualViewport?.addEventListener('resize', updateViewport)
window.visualViewport?.addEventListener('scroll', updateViewport)
const navigationDismissed = ref(false)
let returnFocus: HTMLElement | null = null
const visible = computed(() => props.modelValue)
const titleId = `responsive-dialog-${Math.random().toString(36).slice(2)}`

const close = async () => {
  if (props.beforeClose && !await props.beforeClose()) return
  emit('update:modelValue', false)
  emit('close')
}

useOverlayStack(visible, close)
useModalScrollLock(visible)
useDialogHistory(visible, () => Boolean(props.history))
const dismissForNavigation = () => {
  if (!props.modelValue) return
  navigationDismissed.value = true
  close()
}
useRouteDismiss(dismissForNavigation)
onDeactivated(dismissForNavigation)
const sheet = useSheetGesture(panelRef, visible, computed(() => props.mobileMode === 'sheet'), close)

const onKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Tab' && props.modelValue && isTopOverlay(close)) {
    const items = Array.from(panelRef.value?.querySelectorAll<HTMLElement>('button:not(:disabled), input, select, textarea, a[href], [tabindex="0"]') ?? []).filter(item => item.getClientRects().length > 0)
    const first = items[0], last = items.at(-1)
    if (!first) { event.preventDefault(); panelRef.value?.focus() }
    else if (event.shiftKey && (document.activeElement === first || document.activeElement === panelRef.value)) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }
  if (event.key === 'Escape' && props.modelValue && props.closeOnEscape && isTopOverlay(close)) { event.preventDefault(); event.stopImmediatePropagation(); void close() }
}

watch(visible, (isVisible) => {
  if (isVisible) {
    navigationDismissed.value = false
    returnFocus = document.activeElement as HTMLElement
    window.addEventListener('keydown', onKeydown)
    nextTick(() => panelRef.value?.focus({ preventScroll: true }))
  } else {
    window.removeEventListener('keydown', onKeydown)
    if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true })
  }
}, { immediate: true })

onBeforeUnmount(() => { window.removeEventListener('keydown', onKeydown); window.removeEventListener('resize', updateViewport); window.visualViewport?.removeEventListener('resize', updateViewport); window.visualViewport?.removeEventListener('scroll', updateViewport) })
</script>

<style scoped>
.responsive-dialog-panel { max-width: 100%; }
.responsive-dialog-body { overscroll-behavior: contain; }
.responsive-dialog-enter-active,
.responsive-dialog-leave-active { transition: opacity var(--ts-motion-normal) ease; }
.responsive-dialog-enter-active section,
.responsive-dialog-leave-active section { transition: transform var(--ts-motion-normal) var(--ts-ease), opacity var(--ts-motion-normal) ease; }
.responsive-dialog-enter-from,
.responsive-dialog-leave-to { opacity: 0; }
.responsive-dialog-enter-from section,
.responsive-dialog-leave-to section { transform: translateY(1.5rem); opacity: 0; }
@media (max-width: 767px) {
  .mobile-fullscreen { height: var(--dialog-viewport-height, 100dvh); }
  .sheet-drag-zone { touch-action: none; user-select: none; cursor: grab; }
  .sheet-drag-zone:active { cursor: grabbing; }
  .mobile-fullscreen .responsive-dialog-header {
    min-height: calc(3.5rem + var(--ts-safe-area-top));
    padding-top: var(--ts-safe-area-top);
  }
  .mobile-fullscreen .responsive-dialog-body {
    padding-bottom: calc(1rem + var(--ts-safe-area-bottom));
  }
  .responsive-dialog-enter-active .mobile-fullscreen,
  .responsive-dialog-leave-active .mobile-fullscreen {
    transition: transform var(--ts-motion-page) var(--ts-ease);
  }
  .responsive-dialog-enter-from .mobile-fullscreen,
  .responsive-dialog-leave-to .mobile-fullscreen {
    transform: translateX(100%);
    opacity: 1;
  }
}
@media (prefers-reduced-motion: reduce) {
  .responsive-dialog-enter-active, .responsive-dialog-leave-active,
  .responsive-dialog-enter-active section, .responsive-dialog-leave-active section { transition: none !important; }
}
@media (min-width: 768px) {
  .responsive-dialog-right { align-items: stretch; justify-content: flex-end; padding: 0; }
  .responsive-dialog-right .responsive-dialog-panel { height: 100dvh; max-height: 100dvh; border-radius: 0; }
  .responsive-dialog-panel { max-width: var(--responsive-dialog-max-width); }
  .responsive-dialog-enter-from section,
  .responsive-dialog-leave-to section { transform: translateY(0.5rem) scale(0.98); }
  .responsive-dialog-right.responsive-dialog-enter-from section,
  .responsive-dialog-right.responsive-dialog-leave-to section { transform: translateX(100%); }
}
</style>
