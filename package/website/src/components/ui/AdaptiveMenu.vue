<template>
  <ResponsiveDialog v-if="mobile && mobilePresentation === 'sheet'" :model-value="modelValue" :title="title" @update:model-value="emit('update:modelValue', $event)" glass>
    <div class="ts-action-content" @click="closeAfterAction"><slot /></div>
  </ResponsiveDialog>
  <template v-else>
    <span ref="anchorRef" hidden />
    <Teleport to="body">
      <div v-if="modelValue" ref="menuRef" role="menu" :aria-label="title" class="ts-liquid-glass ts-desktop-menu" :style="menuStyle" @click="closeAfterAction"><slot /></div>
    </Teleport>
  </template>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed, onMounted, onBeforeUnmount } from 'vue'
import { useOverlayStack } from '@/composables/useOverlayStack'
import { useMediaQuery } from '@vueuse/core'
import ResponsiveDialog from './ResponsiveDialog.vue'
const props = withDefaults(defineProps<{ modelValue: boolean; title: string; glass?: boolean; closeOnAction?: boolean; mobilePresentation?: 'sheet' | 'popover' }>(), { closeOnAction: false, mobilePresentation: 'sheet' })
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const mobile = useMediaQuery('(max-width: 767px)')
const menuRef = ref<HTMLElement | null>(null)
const anchorRef = ref<HTMLElement | null>(null)
const menuStyle = ref<Record<string, string>>({ position: 'fixed', zIndex: '3000', marginTop: '0' })
const popoverVisible = computed(() => props.modelValue && !(mobile.value && props.mobilePresentation === 'sheet'))
useOverlayStack(popoverVisible, () => emit('update:modelValue', false))
const positionMenu = async () => {
  await nextTick()
  const anchor = anchorRef.value?.parentElement?.getBoundingClientRect()
  const menu = menuRef.value
  if (!anchor || !menu) return
  const viewport = window.visualViewport
  const viewportTop = viewport?.offsetTop ?? 0
  const viewportHeight = viewport?.height ?? window.innerHeight
  const menuWidth = menu.getBoundingClientRect().width
  const top = Math.max(viewportTop + 8, Math.min(anchor.bottom + 10, viewportTop + viewportHeight - menu.offsetHeight - 8))
  const left = Math.max(8, Math.min(anchor.right - menuWidth, window.innerWidth - menuWidth - 8))
  menuStyle.value = { position: 'fixed', zIndex: '3000', marginTop: '0', right: 'auto', top: `${top}px`, left: `${left}px`, maxHeight: `${viewportHeight - 16}px`, overflowY: 'auto' }
}
watch(popoverVisible, visible => { if (visible) void positionMenu() }, { flush: 'post' })
const dismiss = (event: PointerEvent | KeyboardEvent) => {
  if (!props.modelValue || (mobile.value && props.mobilePresentation === 'sheet')) return
  if (event instanceof KeyboardEvent) {
    if (event.key === 'Escape') emit('update:modelValue', false)
  } else if (menuRef.value && !menuRef.value.contains(event.target as Node) && !anchorRef.value?.parentElement?.contains(event.target as Node)) {
    emit('update:modelValue', false)
  }
}
const reposition = () => { if (popoverVisible.value) void positionMenu() }
onMounted(() => { document.addEventListener('pointerdown', dismiss); document.addEventListener('keydown', dismiss); window.addEventListener('resize', reposition); window.addEventListener('scroll', reposition, true) })
onBeforeUnmount(() => { document.removeEventListener('pointerdown', dismiss); document.removeEventListener('keydown', dismiss); window.removeEventListener('resize', reposition); window.removeEventListener('scroll', reposition, true) })
const closeAfterAction = (event: MouseEvent) => {
  if (props.closeOnAction && (event.target as HTMLElement).closest('button:not(:disabled)')) emit('update:modelValue', false)
}
</script>
