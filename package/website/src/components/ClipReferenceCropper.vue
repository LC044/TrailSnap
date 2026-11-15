<template>
  <ResponsiveDialog :model-value="modelValue" title="截取参考图片" description="拖动画面选取区域，也可用滑块调整。仅保存参考副本。" max-width="680px" mobile-mode="fullscreen" mobile-back @update:model-value="emit('update:modelValue', $event)">
    <p v-if="error" role="alert" class="mb-3 text-sm text-[var(--ts-color-danger)]">{{ error }}</p>
    <p v-if="!ready && !error" role="status" class="ts-muted mb-3 text-sm">正在加载图片…</p>
    <div class="flex min-h-32 justify-center overflow-hidden rounded-xl bg-[var(--ts-color-surface-muted)]">
      <div ref="surface" class="relative max-w-full touch-none select-none" @pointerdown="start" @pointermove="move" @pointerup="finish" @pointercancel="finish">
        <img ref="photo" :src="source" alt="待截取的参考图片" draggable="false" class="block max-h-[48dvh] max-w-full object-contain" @load="ready = true" @error="error = '图片加载失败，请重新选择'" />
        <div v-if="ready" class="pointer-events-none absolute border-2 border-primary-500 bg-primary-500/10" :style="{ left: `${box.x}%`, top: `${box.y}%`, width: `${box.width}%`, height: `${box.height}%`, boxShadow: '0 0 0 100vmax rgb(0 0 0 / 35%)' }" />
      </div>
    </div>
    <div v-if="ready" class="mt-5 grid grid-cols-1 gap-x-6 sm:grid-cols-2">
      <label class="ts-muted text-sm">左侧位置<el-slider v-model="box.x" :max="100 - box.width" :step="1" aria-label="裁剪左侧位置" /></label>
      <label class="ts-muted text-sm">顶部位置<el-slider v-model="box.y" :max="100 - box.height" :step="1" aria-label="裁剪顶部位置" /></label>
      <label class="ts-muted text-sm">区域宽度<el-slider v-model="box.width" :min="1" :max="100 - box.x" :step="1" aria-label="裁剪区域宽度" /></label>
      <label class="ts-muted text-sm">区域高度<el-slider v-model="box.height" :min="1" :max="100 - box.y" :step="1" aria-label="裁剪区域高度" /></label>
    </div>
    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <button class="ts-button ts-button-secondary" :disabled="!ready" @click="reset">重置为整张</button>
        <button class="ts-button ts-button-primary" :disabled="!ready" @click="confirm">使用此区域</button>
      </div>
    </template>
  </ResponsiveDialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'

const props = defineProps<{ modelValue: boolean; source: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; confirm: [image: string] }>()
const surface = ref<HTMLElement>()
const photo = ref<HTMLImageElement>()
const ready = ref(false)
const error = ref('')
const box = ref({ x: 0, y: 0, width: 100, height: 100 })
let anchor: { x: number; y: number; id: number } | undefined
const reset = () => { box.value = { x: 0, y: 0, width: 100, height: 100 } }
function point(event: PointerEvent) {
  const rect = surface.value!.getBoundingClientRect()
  return { x: Math.max(0, Math.min(99, (event.clientX - rect.left) / rect.width * 100)),
    y: Math.max(0, Math.min(99, (event.clientY - rect.top) / rect.height * 100)) }
}
function start(event: PointerEvent) {
  if (!ready.value || event.button !== 0 || anchor) return
  anchor = { ...point(event), id: event.pointerId }
  surface.value!.setPointerCapture(event.pointerId)
}
function move(event: PointerEvent) {
  if (!anchor || event.pointerId !== anchor.id) return
  const position = point(event)
  box.value = { x: Math.min(anchor.x, position.x), y: Math.min(anchor.y, position.y),
    width: Math.max(1, Math.abs(position.x - anchor.x)), height: Math.max(1, Math.abs(position.y - anchor.y)) }
}
function finish(event: PointerEvent) {
  if (!anchor || event.pointerId !== anchor.id) return
  anchor = undefined
  if (surface.value?.hasPointerCapture(event.pointerId)) surface.value.releasePointerCapture(event.pointerId)
}
function confirm() {
  const image = photo.value
  if (!ready.value || !image) return
  try {
    const width = Math.max(1, image.naturalWidth * box.value.width / 100)
    const height = Math.max(1, image.naturalHeight * box.value.height / 100)
    const scale = Math.min(1, 768 / Math.max(width, height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(width * scale))
    canvas.height = Math.max(1, Math.round(height * scale))
    const context = canvas.getContext('2d')
    if (!context) throw new Error('当前环境无法裁剪图片')
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.drawImage(image, image.naturalWidth * box.value.x / 100, image.naturalHeight * box.value.y / 100,
      width, height, 0, 0, canvas.width, canvas.height)
    const result = canvas.toDataURL('image/jpeg', 0.85)
    if (result.length > 699_000) throw new Error('参考图片过大，请缩小截取区域')
    emit('confirm', result)
  } catch (e) { error.value = e instanceof Error ? e.message : '图片裁剪失败，请重新选择' }
}
watch(() => [props.source, props.modelValue], () => {
  reset(); error.value = ''; anchor = undefined
  ready.value = !!photo.value?.complete && !!photo.value?.naturalWidth && photo.value?.getAttribute('src') === props.source
})
</script>
