import type { Router } from 'vue-router'
import { useNavigationStore } from '@/stores/navigation'

// Register before auth/capability guards, so their waits and redirects are covered.
export function installNavigationFeedback(router: Router) {
  router.beforeEach(to => { useNavigationStore().start(to) })
  router.afterEach(to => { useNavigationStore().finish(to) })
  router.onError((_error, to) => { useNavigationStore().fail(to) })
}
