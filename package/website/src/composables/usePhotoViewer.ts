import { computed, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import type { AlbumImage } from '@/types/album'

/** Track the photo by ID so inserts and deletions do not silently change the current photo. */
export function usePhotoViewer(photos: MaybeRefOrGetter<AlbumImage[]>, options: { onNextAtEnd?: () => void } = {}) {
  const currentId = ref<string | null>(null)
  const items = computed(() => toValue(photos))
  const currentIndex = computed(() => items.value.findIndex(photo => photo.id === currentId.value))
  const currentPhoto = computed<AlbumImage | null>({
    get: () => items.value[currentIndex.value] || null,
    set: photo => { currentId.value = photo?.id ?? null },
  })
  const visible = computed({ get: () => currentId.value !== null, set: value => { if (!value) currentId.value = null } })
  const index = computed({
    get: () => Math.max(0, currentIndex.value),
    set: value => { currentId.value = items.value[value]?.id ?? null },
  })
  const hasPrev = computed(() => currentIndex.value > 0)
  const hasNext = computed(() => currentIndex.value >= 0 && currentIndex.value < items.value.length - 1)
  const open = (photo: AlbumImage | number) => {
    const target = typeof photo === 'number' ? items.value[photo] : photo
    if (target && items.value.some(item => item.id === target.id)) currentId.value = target.id
  }
  const close = () => { currentId.value = null }
  const prev = () => { if (hasPrev.value) index.value = currentIndex.value - 1 }
  const next = () => { if (hasNext.value) index.value = currentIndex.value + 1; else options.onNextAtEnd?.() }
  watch(() => items.value.map(photo => photo.id), (ids, previousIds) => {
    if (currentId.value === null || ids.includes(currentId.value)) return
    const previousIndex = previousIds.indexOf(currentId.value)
    currentId.value = ids[Math.min(Math.max(0, previousIndex), ids.length - 1)] ?? null
  }, { flush: 'sync' })
  return { currentPhoto, currentIndex, index, visible, hasPrev, hasNext, open, close, prev, next }
}
