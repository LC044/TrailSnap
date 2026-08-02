import { App } from '@capacitor/app'
import type { Router } from 'vue-router'
import { isNativeApp } from '@/config/server'

let registered = false
let navigatingBack = false

/**
 * Android hardware/gesture back behavior:
 * 1. pop a modal's synthetic history entry;
 * 2. navigate to the previous Vue route;
 * 3. minimize the app at the root instead of terminating its Activity.
 */
export async function registerNativeBackButton(router: Router): Promise<void> {
  if (!isNativeApp() || registered) return
  registered = true

  await App.addListener('backButton', async () => {
    if (navigatingBack) return

    const state = window.history.state as { back?: string | null; modalOpen?: boolean } | null
    const path = router.currentRoute.value.path
    const isHome = path === '/'
    const canNavigateBack = state?.modalOpen || (!isHome && Boolean(state?.back))

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
