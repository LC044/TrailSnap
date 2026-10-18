import { computed, ref, watch } from 'vue'
import { usePhotoViewingStore } from '@/stores/photoViewing'
import type { AlbumImage } from '@/types/album'

export function useOriginalPhoto(props: { visible: boolean; image: AlbumImage | null }) {
  const preferences = usePhotoViewingStore()
  const showOriginal = ref(preferences.autoViewOriginal)

  // Each viewing starts from the saved preference; manual toggles only affect this photo.
  watch([() => props.visible, () => props.image?.id, () => preferences.autoViewOriginal], () => {
    if (props.visible) showOriginal.value = preferences.autoViewOriginal
  }, { immediate: true, flush: 'sync' })

  const displayImageSrc = computed(() => {
    if (!props.image) return ''
    return showOriginal.value ? props.image.url : props.image.preview || props.image.url
  })
  const toggleOriginal = () => { showOriginal.value = !showOriginal.value }

  return { showOriginal, displayImageSrc, toggleOriginal }
}
