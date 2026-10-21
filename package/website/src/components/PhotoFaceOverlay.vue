<template>
  <div ref="root" class="absolute inset-0 z-20 pointer-events-none" aria-label="照片中的人物">
    <button v-for="face in positionedFaces" :key="face.id" type="button"
      :data-face-id="face.id" :aria-label="face.identity_name || '未标记的人脸'"
      :aria-pressed="selectedId === face.id" :style="face.style"
      class="photo-face-target absolute pointer-events-auto bg-transparent rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
      :class="selectedId === face.id ? 'border-primary-400 bg-primary-500/10' : (revealAll ? 'border-white/50 hover:border-primary-400' : 'border-transparent hover:border-primary-400')">
      <span class="photo-face-name absolute left-1/2 top-0 max-w-44 truncate rounded-md bg-black/80 px-2 py-1 text-xs text-white pointer-events-none"
        :class="{ 'photo-face-name-selected': selectedId === face.id, 'photo-face-name-revealed': revealAll }"
        :style="{ transform: `translateX(-50%) scale(${1 / zoom})`, transformOrigin: 'top center' }">{{ face.identity_name || '未标记' }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useResizeObserver } from '@vueuse/core'
import type { PhotoFace } from '@/api/face'
import { containFaceCircle } from '@/utils/photoFaces'

const props = defineProps<{
  faces: PhotoFace[]
  imageElement: HTMLImageElement | null
  selectedId: number | null
  zoom: number
  loaded: boolean
  revealAll: boolean
}>()
const root = ref<HTMLElement | null>(null)
const size = ref({ width: 0, height: 0 })
const measure = () => {
  size.value = { width: root.value?.clientWidth || 0, height: root.value?.clientHeight || 0 }
}
useResizeObserver(root, measure)
watch(() => [props.imageElement, props.loaded], measure, { flush: 'post' })
const positionedFaces = computed(() => props.faces.flatMap(face => {
  const image = props.imageElement
  if (!image || !props.loaded) return []
  const rect = containFaceCircle(face.face_rect, size.value.width, size.value.height, image.naturalWidth, image.naturalHeight)
  return rect ? [{ ...face, style: { left: `${rect.x}px`, top: `${rect.y}px`, width: `${rect.width}px`, height: `${rect.height}px` } }] : []
}))
</script>

<style scoped>
.photo-face-target { padding: 0; cursor: pointer; }
.photo-face-target:hover, .photo-face-target:focus-visible { z-index: 1; }
.photo-face-name { opacity: 0; }
.photo-face-target:hover .photo-face-name,
.photo-face-target:focus-visible .photo-face-name,
.photo-face-name-selected,
.photo-face-name-revealed { opacity: 1; }
</style>
