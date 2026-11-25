<template>
  <button v-bind="$attrs" type="button" class="block overflow-hidden p-0" :aria-label="`查看照片 ${alt}`" @click="open">
    <img :src="thumbnailUrl(photoId)" :alt="alt" loading="lazy" class="h-full w-full object-cover" />
  </button>
  <PhotoLightbox v-if="visible" :visible="visible" :image="images[index] || null" :images="images"
    :current-index="index" :has-prev="index > 0" :has-next="index < images.length - 1"
    @close="visible = false" @prev="index = Math.max(0, index - 1)" @next="index = Math.min(images.length - 1, index + 1)" />
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import { thumbnailUrl, thumbnailToFileUrl } from '@/utils/mediaUrl'
import type { AlbumImage } from '@/types/album'
defineOptions({ inheritAttrs: false })
const props = withDefaults(defineProps<{ photoId: string; alt?: string; photoIds?: string[] }>(), { alt: '', photoIds: () => [] })
const visible = ref(false)
const index = ref(0)
const images = computed<AlbumImage[]>(() => (props.photoIds.length ? props.photoIds : [props.photoId]).map(id => ({
  id, url: thumbnailToFileUrl(thumbnailUrl(id)), thumbnail: thumbnailUrl(id), preview: thumbnailUrl(id, 'medium'),
  srcset: '', timestamp: 0, hasPhotoTime: false, albumIds: [], file_type: 'image',
})))
const open = () => { index.value = Math.max(0, images.value.findIndex(photo => photo.id === props.photoId)); visible.value = true }
</script>
