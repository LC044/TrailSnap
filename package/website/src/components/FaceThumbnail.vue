<template>
  <div class="face-thumbnail relative overflow-hidden">
    <img v-if="!failed" :key="src" :src="src" class="absolute max-w-none" :style="getFaceCropStyle(face)"
      loading="lazy" :alt="alt" @error="failed = true" />
    <div v-else class="ts-muted flex h-full w-full flex-col items-center justify-center gap-1 text-xs">
      <ScanFace class="h-6 w-6" />
      <span>头像加载失败</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ScanFace } from 'lucide-vue-next'
import { getFaceCropStyle } from '@/utils/faceCrop'
import { thumbnailUrl } from '@/utils/mediaUrl'

const props = withDefaults(defineProps<{
  face: { photo_id: string; face_rect: number[] | null }
  alt?: string
}>(), { alt: '人脸头像' })
const src = computed(() => thumbnailUrl(props.face.photo_id, 'medium'))
const failed = ref(false)
watch(src, () => { failed.value = false })
</script>

<style scoped>
.face-thumbnail { background: var(--ts-color-surface-muted); }
</style>
