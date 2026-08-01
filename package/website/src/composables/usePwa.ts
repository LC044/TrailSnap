import { computed, ref } from 'vue'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}

const deferredPrompt = ref<BeforeInstallPromptEvent | null>(null)
const isOnline = ref(navigator.onLine)
const updateAvailable = ref(false)
const isInstalled = ref(window.matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone === true)
let registration: ServiceWorkerRegistration | undefined
let updateRequested = false

const isIos = /iPad|iPhone|iPod/.test(navigator.userAgent)
const canInstall = computed(() => !!deferredPrompt.value)

window.addEventListener('online', () => { isOnline.value = true })
window.addEventListener('offline', () => { isOnline.value = false })
window.addEventListener('beforeinstallprompt', (event) => {
  event.preventDefault()
  deferredPrompt.value = event as BeforeInstallPromptEvent
})
window.addEventListener('appinstalled', () => {
  deferredPrompt.value = null
  isInstalled.value = true
})

export function registerPwa() {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return

  window.addEventListener('load', async () => {
    registration = await navigator.serviceWorker.register('/sw.js')
    if (registration.waiting) updateAvailable.value = true
    registration.addEventListener('updatefound', () => {
      const worker = registration?.installing
      worker?.addEventListener('statechange', () => {
        if (worker.state === 'installed' && navigator.serviceWorker.controller) updateAvailable.value = true
      })
    })
  }, { once: true })

  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (updateRequested) window.location.reload()
  })
}

export async function installPwa() {
  const prompt = deferredPrompt.value
  if (!prompt) return false

  await prompt.prompt()
  const { outcome } = await prompt.userChoice
  deferredPrompt.value = null
  return outcome === 'accepted'
}

export function applyPwaUpdate() {
  const waitingWorker = registration?.waiting
  if (!waitingWorker) return

  updateRequested = true
  waitingWorker.postMessage({ type: 'SKIP_WAITING' })
}

export function usePwa() {
  return { canInstall, isInstalled, isIos, isOnline, updateAvailable, installPwa, applyPwaUpdate }
}
