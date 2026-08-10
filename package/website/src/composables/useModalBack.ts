import type { Ref } from 'vue'
import { useOverlayStack } from '@/composables/useOverlayStack'

export function useModalBack(visible: Ref<boolean>, onBack?: () => void) {
  useOverlayStack(visible, () => {
    visible.value = false
    onBack?.()
  })
}
