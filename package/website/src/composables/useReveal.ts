import type { App, Directive, DirectiveBinding } from 'vue'
import { reducedMotion } from '@/utils/motion'

/**
 * `v-reveal` — editorial scroll entrance.
 *
 * Adds `.ts-reveal` immediately, then `.is-revealed` the first time the element
 * scrolls into the viewport. CSS owns the motion; this only decides *when* so
 * the animation never fights with layout or with a page's own transitions.
 *
 *   <section v-reveal>…</section>
 *   <li v-reveal="index * 60">…</li>          // stagger by index (ms)
 *   <div v-reveal="{ delay: 120, y: 8 }">…</div>
 *
 * The observer is rooted at the viewport: IntersectionObserver already clips
 * against the app's scroll container, so it agrees with what the user sees.
 */
interface RevealOptions {
  /** Extra delay in ms, on top of the transition duration already in CSS. */
  delay?: number
  /** Distance in px the element travels while appearing. */
  y?: number
  /** Fraction of the element that must be visible. */
  threshold?: number
  /** Replay every time the element re-enters (default: once). */
  repeat?: boolean
  /** Skip the animation and simply show the element. */
  disabled?: boolean
}

type RevealValue = number | RevealOptions | undefined

interface RevealHost extends HTMLElement {
  __tsRevealObserver?: IntersectionObserver
}

function normalise(value: RevealValue): RevealOptions {
  if (typeof value === 'number') return { delay: value }
  return value ?? {}
}

function reveal(el: HTMLElement) {
  el.classList.add('is-revealed')
}

export const vReveal: Directive<RevealHost, RevealValue> = {
  mounted(el, binding: DirectiveBinding<RevealValue>) {
    const options = normalise(binding.value)
    el.classList.add('ts-reveal')
    if (options.y !== undefined) el.style.setProperty('--ts-reveal-y', `${options.y}px`)
    if (options.delay) el.style.setProperty('--ts-reveal-delay', `${options.delay}ms`)

    if (options.disabled || reducedMotion() || typeof IntersectionObserver === 'undefined') {
      reveal(el)
      return
    }

    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            reveal(el)
            if (!options.repeat) observer.unobserve(el)
          } else if (options.repeat) {
            el.classList.remove('is-revealed')
          }
        }
      },
      { threshold: options.threshold ?? 0.04, rootMargin: '0px 0px -4% 0px' },
    )
    observer.observe(el)
    el.__tsRevealObserver = observer
  },

  unmounted(el) {
    el.__tsRevealObserver?.disconnect()
    delete el.__tsRevealObserver
  },
}

/** Register once from main.ts. */
export function registerRevealDirective(app: App) {
  app.directive('reveal', vReveal)
}