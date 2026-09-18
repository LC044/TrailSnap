<template>
    <div
    class="relative w-12 aspect-square rounded-full overflow-hidden border-2 transition-all duration-300 bg-gray-100 dark:bg-gray-800"
    :class="['border-transparent group-hover:border-gray-300 dark:group-hover:border-gray-600']"
    >
        <img
            v-if="person.cover_photo"
            :src="getPhotoUrl(person.cover_photo.photo_id)"
            class="absolute max-w-none transition-transform duration-500 group-hover:scale-110"
            :style="getFaceCropStyle(person.cover_photo)"
            loading="lazy"
        />
        <div v-else class="w-full h-full flex items-center justify-center text-gray-400">
            <User class="w-1/2 h-1/2" />
        </div>
    </div>
</template>

<script setup lang="ts">
import { User } from '@element-plus/icons-vue'
import type { FaceIdentity } from '@/types/album'
import { getFaceCropStyle } from '@/utils/faceCrop'
import { thumbnailUrl } from '@/utils/mediaUrl'

defineProps({
  person: {
    type: Object as () => FaceIdentity,
    required: true,
    default: () => ({})
  }
})

const getPhotoUrl = (photoId: string) => {
  return thumbnailUrl(photoId, 'medium')
}

</script>
