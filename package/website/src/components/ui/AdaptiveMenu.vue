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
import { liquidFrames } from '@/utils/liquidMorph'
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
  const menuWidth = menu.getBoundingClientRect().width
  const top = Math.max(viewportTop + 8, Math.min(anchor.bottom + 10, viewportTop + viewportHeight - menu.offsetHeight - 8))
  const left = Math.max(8, Math.min(anchor.left + anchor.width / 2 - menuWidth / 2, window.innerWidth - menuWidth - 8))
  menuStyle.value = { position: 'fixed', zIndex: String(layerZIndex), marginTop: '0', right: 'auto', top: `${top}px`, left: `${left}px`, maxHeight: `${viewportHeight - 16}px`, overflowY: 'auto' }
}
let animations: Animation[] = []
let animatedPanel: HTMLElement | null = null
let panelOverflow = ''
let panelOverflowX = ''
let frozenShape: Keyframe | null = null
let frozenContentOpacity: string | null = null
let contentWidth = ''
let finishMorph: (() => void) | null = null
let suppressMotion = false
const cancelMorph = () => {
  const finish = finishMorph
  finishMorph = null
  animations.forEach(animation => animation.cancel())
  animations = []
  if (animatedPanel) {
    animatedPanel.style.overflowY = panelOverflow
    animatedPanel.style.overflowX = panelOverflowX
    const content = animatedPanel.firstElementChild as HTMLElement
    content.style.minWidth = contentWidth
  }
  animatedPanel = null
  finish?.()
}
const interruptMorph = () => {
  if (animatedPanel) {
    const rect = animatedPanel.getBoundingClientRect()
    frozenShape = { left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`, height: `${rect.height}px`, borderRadius: getComputedStyle(animatedPanel).borderRadius }
    frozenContentOpacity = getComputedStyle(animatedPanel.firstElementChild as HTMLElement).opacity
  }
  cancelMorph()
}
const morph = (element: Element, opening: boolean, done: () => void) => {
  const panel = element as HTMLElement
  const control = trigger()
  const button = control?.closest<HTMLElement>('.ts-glass-toolbar') ?? control
  const interrupted = animations.length > 0 || frozenShape !== null
  const current = panel.getBoundingClientRect()
  const currentRadius = getComputedStyle(panel).borderRadius
  const currentContentOpacity = frozenContentOpacity ?? getComputedStyle(panel.firstElementChild as HTMLElement).opacity
  cancelMorph()
  if (suppressMotion || !button?.isConnected || reducedMotion()) { frozenShape = null; frozenContentOpacity = null; done(); return }
  const from = button.getBoundingClientRect()
  const to = panel.getBoundingClientRect()
  const expanded = { left: `${to.left}px`, top: `${to.top}px`, width: `${to.width}px`, height: `${to.height}px`, borderRadius: getComputedStyle(panel).borderRadius, padding: getComputedStyle(panel).padding, opacity: 1 }
  const content = panel.firstElementChild as HTMLElement
  const naturalContentWidth = content.getBoundingClientRect().width
  animatedPanel = panel
  panelOverflow = panel.style.overflowY
  panelOverflowX = panel.style.overflowX
  panel.style.overflowY = 'hidden'
  panel.style.overflowX = 'hidden'
  const start = frozenShape ?? (interrupted ? { left: `${current.left}px`, top: `${current.top}px`, width: `${current.width}px`, height: `${current.height}px`, borderRadius: currentRadius, opacity: getComputedStyle(panel).opacity } : null)
  frozenShape = null
  frozenContentOpacity = null
  const duration = opening ? 560 : 460
  const panelStyle = getComputedStyle(panel)
  const frames = liquidFrames(opening ? from : to, opening ? to : from, expanded.borderRadius, opening, {
    backgroundColor: panelStyle.backgroundColor, backdropFilter: panelStyle.backdropFilter, boxShadow: panelStyle.boxShadow,
  })
  if (start) frames[0] = { ...frames[0], ...start, offset: 0 }
  frames.forEach(frame => { frame.padding = '0px' })
  frames[opening ? frames.length - 1 : 0]!.padding = expanded.padding
  const shape = panel.animate(frames, { duration, fill: 'both' })
  contentWidth = content.style.minWidth
  content.style.minWidth = `${naturalContentWidth}px`
  const fade = content.animate([{ opacity: interrupted ? currentContentOpacity : opening ? 0 : 1 }, { opacity: opening ? 1 : 0 }], { duration: opening ? 180 : 100, delay: opening && !interrupted ? 260 : 0, fill: 'both' })
  animations = [shape, fade]
  finishMorph = done
  shape.onfinish = cancelMorph
}
const morphEnter = async (element: Element, done: () => void) => {
  layerZIndex = nextDialogZIndex(nextZIndex)
  await positionMenu()
  await nextTick()
  if (!props.modelValue || !element.isConnected) { done(); return }
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
  suppressMotion = true
  if (animatedPanel) animatedPanel.hidden = true
  cancelMorph()
  frozenShape = null
  frozenContentOpacity = null
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
