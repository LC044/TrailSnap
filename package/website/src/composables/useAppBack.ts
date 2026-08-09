import { useRouter, type RouteLocationRaw } from 'vue-router'
import { closeTopOverlay } from '@/composables/useOverlayStack'

type BackFallback = RouteLocationRaw | (() => void | Promise<void>)

export function useAppBack(fallback: BackFallback = '/') {
  const router = useRouter()

  return async () => {
    if (await closeTopOverlay()) return

    const state = window.history.state as { back?: string | null } | null
    if (state?.back) {
      router.back()
      return
    }

    if (typeof fallback === 'function') {
      await fallback()
    } else {
      await router.replace(fallback)
    }
  }
}
