<template>
  <AlbumSelector
    v-model:visible="albumVisible"
    :photo-ids="photoIds"
    @success="finishAlbum"
  />
  <FolderSelectionDialog
    v-model:visible="folderVisible"
    action="move"
    :photo-ids="photoIds"
    :default-sub-folder="defaultSubFolder"
    @success="finishTransfer"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AlbumSelector from '@/components/AlbumSelector.vue'
import FolderSelectionDialog from '@/components/FolderSelectionDialog.vue'

const props = withDefaults(defineProps<{ defaultSubFolder?: string }>(), {
  defaultSubFolder: '',
})

const emit = defineEmits<{
  (event: 'album-success'): void
  (event: 'transfer-success'): void
}>()

const photoIds = ref<string[]>([])
const albumVisible = ref(false)
const folderVisible = ref(false)

const openAlbum = (photoId: string) => {
  if (!photoId) return
  photoIds.value = [photoId]
  albumVisible.value = true
}

const openMove = (photoId: string) => {
  if (!photoId) return
  photoIds.value = [photoId]
  folderVisible.value = true
}

const reset = () => {
  photoIds.value = []
}

const finishAlbum = () => {
  albumVisible.value = false
  reset()
  emit('album-success')
}

const finishTransfer = () => {
  folderVisible.value = false
  reset()
  emit('transfer-success')
}

defineExpose({ openAlbum, openMove })
</script>
