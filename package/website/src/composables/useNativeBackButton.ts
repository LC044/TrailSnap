import { App } from '@capacitor/app'
import type { Router } from 'vue-router'
import { isNativeApp } from '@/config/server'
import { closeTopOverlay } from '@/composables/useOverlayStack'

let registered = false
let navigatingBack = false

/**
 * Android hardware/gesture back behavior:
 * 1. close the top-most app overlay;
 * 2. navigate to the previous Vue route;
 * 3. minimize the app at the root instead of terminating its Activity.
 */
export async function registerNativeBackButton(router: Router): Promise<void> {
  if (!isNativeApp() || registered) return
  registered = true

  await App.addListener('backButton', async () => {
    if (navigatingBack) return

    if (await closeTopOverlay()) return

    const state = window.history.state as { back?: string | null } | null
    const path = router.currentRoute.value.path
    const isHome = path === '/'
    const canNavigateBack = !isHome && Boolean(state?.back)

    if (canNavigateBack) {
      navigatingBack = true
      window.history.back()
      window.setTimeout(() => { navigatingBack = false }, 300)
      return
    }

    // On Android this moves the task to the background. It preserves the
    // WebView/router state, so reopening TrailSnap resumes where the user left.
    await App.minimizeApp()
  })
}
