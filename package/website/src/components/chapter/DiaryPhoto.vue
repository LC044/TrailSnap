<template>
  <div class="relative h-full w-full overflow-hidden bg-gray-100 dark:bg-gray-800">
    <img v-if="!broken" :src="thumbnailUrl(id, size)" :alt="alt" class="h-full w-full" :class="contain ? 'object-contain' : 'object-cover'" loading="lazy" @error="broken = true" />
    <span v-else class="absolute inset-0 flex items-center justify-center gap-2 px-4 text-xs text-gray-500 dark:text-gray-400"><ImageOff :size="18" />照片暂时无法显示</span>
  </div>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue'
import { ImageOff } from 'lucide-vue-next'
import { thumbnailUrl } from '@/utils/mediaUrl'
const props = withDefaults(defineProps<{ id: string; alt: string; size?: 'small' | 'medium'; contain?: boolean }>(), { size: 'small', contain: false })
const broken = ref(false)
watch(() => props.id, () => { broken.value = false })
</script>
