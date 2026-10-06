import { inject, onBeforeUnmount } from 'vue'
import { routerKey } from 'vue-router'

/** Dismiss local overlays on successful navigation, including reused route components. */
export function useRouteDismiss(close: () => void) {
  const router = inject(routerKey, null)
  const unregister = router?.afterEach((to, from, failure) => {
    if (!failure && to.fullPath !== from.fullPath) close()
  })
  onBeforeUnmount(() => unregister?.())
}
