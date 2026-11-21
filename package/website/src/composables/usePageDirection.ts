import { ref } from 'vue'
import type { Router } from 'vue-router'

/** Compare committed history positions so cancelled navigations keep the current direction. */
export const pageDirection = ref<'forward' | 'back'>('forward')

function positionOf(): number | null {
  const position = window.history.state?.position
  return typeof position === 'number' ? position : null
}

export function installPageDirection(router: Router) {
  let lastPosition = positionOf()
  router.afterEach((_to, _from, failure) => {
    if (failure) return
    const position = positionOf()
    pageDirection.value = position !== null && lastPosition !== null && position < lastPosition
      ? 'back'
      : 'forward'
    lastPosition = position
  })
}