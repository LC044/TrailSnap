<template>
  <ResponsiveDialog v-if="mobile && mobilePresentation === 'sheet'" :model-value="modelValue" :title="title" @update:model-value="emit('update:modelValue', $event)" glass>
    <div class="ts-action-content" @click="closeAfterAction"><slot /></div>
  </ResponsiveDialog>
  <template v-else>
    <span ref="anchorRef" hidden />
    <Teleport to="body">
      <Transition :css="false" @enter="morphEnter" @leave="morphLeave" @enter-cancelled="interruptMorph" @leave-cancelled="interruptMorph">
        <div v-if="modelValue" ref="menuRef" role="menu" :aria-label="title" class="ts-liquid-glass ts-desktop-menu" :style="menuStyle" @click="closeAfterAction"><div class="ts-menu-content"><slot /></div></div>
      </Transition>
    </Teleport>
  </template>
</template>

<script setup lang="ts">
import { ref, nextTick, computed, onMounted, onBeforeUnmount, onDeactivated, onActivated } from 'vue'
import { useOverlayStack } from '@/composables/useOverlayStack'
import { useMediaQuery } from '@vueuse/core'
import ResponsiveDialog from './ResponsiveDialog.vue'
import { useZIndex } from 'element-plus'
import { nextDialogZIndex } from '@/utils/pickerDate'
import { reducedMotion } from '@/utils/motion'
import { useRouteDismiss } from '@/composables/useRouteDismiss'
const props = withDefaults(defineProps<{ modelValue: boolean; title: string; glass?: boolean; closeOnAction?: boolean; mobilePresentation?: 'sheet' | 'popover' }>(), { closeOnAction: false, mobilePresentation: 'sheet' })
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const mobile = useMediaQuery('(max-width: 767px)')
const menuRef = ref<HTMLElement | null>(null)
const anchorRef = ref<HTMLElement | null>(null)
const menuStyle = ref<Record<string, string>>({ position: 'fixed', zIndex: '3000', marginTop: '0' })
const { nextZIndex } = useZIndex()
let layerZIndex = 3000
const popoverVisible = computed(() => props.modelValue && !(mobile.value && props.mobilePresentation === 'sheet'))
useOverlayStack(popoverVisible, () => emit('update:modelValue', false))
const trigger = () => {
  const sibling = anchorRef.value?.previousElementSibling
  return sibling instanceof HTMLElement && sibling.matches('button, [role="button"]')
    ? sibling : anchorRef.value?.parentElement?.querySelector<HTMLElement>('button[aria-expanded]')
}
const positionMenu = async () => {
  await nextTick()
  const control = trigger()
  const anchor = (control?.closest<HTMLElement>('.ts-glass-toolbar') ?? control ?? anchorRef.value?.parentElement)?.getBoundingClientRect()
  const menu = menuRef.value
  if (!anchor || !menu) return
  const viewport = window.visualViewport
  const viewportTop = viewport?.offsetTop ?? 0
  const viewportHeight = viewport?.height ?? window.innerHeight
  // Measure layout size, not the temporarily scaled animation bounds.
  const menuWidth = menu.offsetWidth
  const top = Math.max(viewportTop + 8, Math.min(anchor.bottom + 10, viewportTop + viewportHeight - menu.offsetHeight - 8))
  const left = Math.max(8, Math.min(anchor.left + anchor.width / 2 - menuWidth / 2, window.innerWidth - menuWidth - 8))
  const controlRect = control?.getBoundingClientRect() ?? anchor
  const originX = Math.max(0, Math.min(controlRect.left + controlRect.width / 2 - left, menuWidth))
  const originY = controlRect.bottom <= top ? '0%' : '100%'
  menuStyle.value = { position: 'fixed', zIndex: String(layerZIndex), marginTop: '0', right: 'auto', top: `${top}px`, left: `${left}px`, maxHeight: `${viewportHeight - 16}px`, overflowY: 'auto', transformOrigin: `${originX}px ${originY}` }
}
let animations: Animation[] = []
let animatedPanel: HTMLElement | null = null
let panelWillChange = ''
let frozenShape: Keyframe | null = null
let finishMorph: (() => void) | null = null
let suppressMotion = false
let enterSequence = 0
const cancelMorph = () => {
  const finish = finishMorph
  finishMorph = null
  animations.forEach(animation => animation.cancel())
  animations = []
  if (animatedPanel) animatedPanel.style.willChange = panelWillChange
  animatedPanel = null
  finish?.()
}
const interruptMorph = () => {
  enterSequence++
  if (animatedPanel) {
    const style = getComputedStyle(animatedPanel)
    frozenShape = { transform: style.transform, opacity: style.opacity }
  }
  cancelMorph()
}
const morph = (element: Element, opening: boolean, done: () => void) => {
  const panel = element as HTMLElement
  const control = trigger()
  const start = frozenShape
  frozenShape = null
  cancelMorph()
  if (suppressMotion || !control?.isConnected || reducedMotion()) { done(); return }
  animatedPanel = panel
  panelWillChange = panel.style.willChange
  panel.style.willChange = 'transform, opacity'
  const direction = panel.style.transformOrigin.endsWith('100%') ? 1 : -1
  const collapsed = { transform: `translateY(${direction * 8}px) scale(.96)`, opacity: 0 }
  const expanded = { transform: 'translateY(0px) scale(1)', opacity: 1 }
  // Keep geometry and glass filters static so menu contents never reflow per frame.
  const shape = panel.animate([
    start ?? (opening ? collapsed : expanded),
    opening ? expanded : collapsed,
  ], { duration: opening ? 200 : 140, easing: opening ? 'cubic-bezier(.22, 1, .36, 1)' : 'cubic-bezier(.4, 0, 1, 1)', fill: 'both' })
  animations = [shape]
  finishMorph = done
  shape.onfinish = cancelMorph
}
const morphEnter = async (element: Element, done: () => void) => {
  const sequence = ++enterSequence
  layerZIndex = nextDialogZIndex(nextZIndex)
  await positionMenu()
  await nextTick()
  if (sequence !== enterSequence || !props.modelValue || !element.isConnected) { done(); return }
  morph(element, true, done)
}
const morphLeave = (element: Element, done: () => void) => morph(element, false, done)
const dismiss = (event: PointerEvent | KeyboardEvent) => {
  if (!props.modelValue || (mobile.value && props.mobilePresentation === 'sheet')) return
  if (event instanceof KeyboardEvent) {
    if (event.key === 'Escape') emit('update:modelValue', false)
  } else if (menuRef.value && !menuRef.value.contains(event.target as Node) && !anchorRef.value?.parentElement?.contains(event.target as Node)) {
    emit('update:modelValue', false)
  }
}
const reposition = () => { if (popoverVisible.value) void positionMenu() }
const dismissImmediately = () => {
  enterSequence++
  suppressMotion = true
  if (animatedPanel) animatedPanel.hidden = true
  cancelMorph()
  frozenShape = null
  if (props.modelValue) emit('update:modelValue', false)
  // The leave hook runs in the next render; later openings may animate again.
  void nextTick(() => { if (anchorRef.value?.isConnected) suppressMotion = false })
}
useRouteDismiss(dismissImmediately)
onDeactivated(dismissImmediately)
onActivated(() => { suppressMotion = false })
onMounted(() => { document.addEventListener('pointerdown', dismiss); document.addEventListener('keydown', dismiss); window.addEventListener('resize', reposition); window.addEventListener('scroll', reposition, true); if (popoverVisible.value) void positionMenu() })
onBeforeUnmount(() => { suppressMotion = true; cancelMorph(); document.removeEventListener('pointerdown', dismiss); document.removeEventListener('keydown', dismiss); window.removeEventListener('resize', reposition); window.removeEventListener('scroll', reposition, true) })
const closeAfterAction = (event: MouseEvent) => {
  if (props.closeOnAction && (event.target as HTMLElement).closest('button:not(:disabled)')) emit('update:modelValue', false)
}
</script>
