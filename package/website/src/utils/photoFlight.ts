import { reducedMotion } from './motion'

/**
 * The photo flight — 「把相片从相册里抽出来」.
 *
 * A thumbnail does not simply make way for a viewer: it is lifted out of the
 * page, carried to the centre of the screen and only then replaced by the real
 * viewer. Closing plays the same journey in reverse, so the photo visibly
 * returns to the frame it came from. That continuity is what makes clicking a
 * photograph feel physical rather than like swapping screens.
 *
 * Implementation is a FLIP: a fixed ghost is laid out at the destination and
 * starts with an inverse transform, so the whole journey is one compositor-only
 * transform transition. The viewer's own image is held invisible for the length
 * of the flight and revealed at the exact frame the ghost lands.
 */

const GHOST_CLASS = 'ts-fly-ghost'
const MORPH_ATTRIBUTE = 'data-ts-photo-flying'
const FLIGHT_MS = 420
const GHOST_Z = 4000

/** Concurrent flights must not reveal the viewer photo early. */
let activeFlights = 0

interface Rect { left: number; top: number; width: number; height: number }

const asRect = (rect: DOMRect): Rect => ({
  left: rect.left,
  top: rect.top,
  width: rect.width,
  height: rect.height,
})

/** Where the photo actually paints inside an `object-fit: cover|contain` box. */
function contentRect(image: HTMLImageElement, fallbackRatio: number, mode: 'cover' | 'contain'): Rect | null {
  const rect = image.getBoundingClientRect()
  if (rect.width < 2 || rect.height < 2) return null
  const natural = image.naturalWidth > 0 && image.naturalHeight > 0
    ? image.naturalWidth / image.naturalHeight
    : fallbackRatio
  const ratio = natural > 0 ? natural : 1
  if (mode === 'cover') return asRect(rect)
  let width = rect.width
  let height = width / ratio
  if (height > rect.height) {
    height = rect.height
    width = height * ratio
  }
  return {
    left: rect.left + (rect.width - width) / 2,
    top: rect.top + (rect.height - height) / 2,
    width,
    height,
  }
}

/** The visible photo inside the lightbox, in viewport coordinates. */
function viewerPhotoRect(ratio: number): Rect | null {
  const image = document.querySelector<HTMLImageElement>(
    '[data-testid="photo-lightbox-current-image"], [data-testid="photo-lightbox-preview"]',
  )
  return image ? contentRect(image, ratio, 'contain') : null
}

function thumbnailOf(host: HTMLElement | null | undefined): HTMLImageElement | null {
  if (!host) return null
  if (host instanceof HTMLImageElement) return host
  return host.querySelector('img')
}

/**
 * The rect the photo is actually visible in: a hovered thumbnail is scaled
 * beyond its frame, and the frame clips it, so the frame is what the eye
 * perceives as "the photo".
 */
function visibleRect(image: HTMLImageElement): Rect {
  let rect = image.getBoundingClientRect()
  let node = image.parentElement
  while (node && node !== document.body) {
    const style = getComputedStyle(node)
    if (style.overflow === 'hidden' || style.overflow === 'clip' || style.overflowX === 'hidden') {
      const box = node.getBoundingClientRect()
      const left = Math.max(rect.left, box.left)
      const top = Math.max(rect.top, box.top)
      const right = Math.min(rect.right, box.right)
      const bottom = Math.min(rect.bottom, box.bottom)
      if (right - left > 8 && bottom - top > 8) rect = new DOMRect(left, top, right - left, bottom - top)
      break
    }
    node = node.parentElement
  }
  return asRect(rect)
}

function createGhost(image: HTMLImageElement, rect: Rect): HTMLImageElement {
  const ghost = document.createElement('img')
  ghost.src = image.currentSrc || image.src
  ghost.alt = ''
  ghost.decoding = 'async'
  ghost.className = GHOST_CLASS
  ghost.style.left = `${rect.left}px`
  ghost.style.top = `${rect.top}px`
  ghost.style.width = `${rect.width}px`
  ghost.style.height = `${rect.height}px`
  ghost.style.zIndex = String(GHOST_Z)
  // No transition yet: the ghost must *arrive* at its starting pose instantly.
  ghost.style.transition = 'none'
  document.body.append(ghost)
  return ghost
}

/**
 * Lay the ghost at `to`, then release it towards `from`'s geometry next frame.
 * Both directions reuse the same code path: the only difference is which rect
 * the journey starts at.
 */
function glide(ghost: HTMLImageElement, from: Rect, to: Rect, onLand: () => void) {
  let landed = false
  const land = () => {
    if (landed) return
    landed = true
    onLand()
    // Drop the print's shadow at the same instant the real photo takes over,
    // then dissolve the last sliver of the ghost. Fading a large shadow would
    // read as a blink on a light viewer background.
    ghost.style.boxShadow = 'none'
    ghost.style.opacity = '0'
    window.setTimeout(() => ghost.remove(), 170)
  }

  /* The ghost is an inset of the destination: scaling by the smaller ratio keeps
     it inside the frame it came from, so a portrait print lifts cleanly out of a
     landscape thumbnail instead of overshooting it. */
  const scale = Math.min(from.width / to.width, from.height / to.height) || 1
  const dx = (from.left + from.width / 2) - (to.left + to.width / 2)
  const dy = (from.top + from.height / 2) - (to.top + to.height / 2)
  ghost.style.left = `${to.left}px`
  ghost.style.top = `${to.top}px`
  ghost.style.width = `${to.width}px`
  ghost.style.height = `${to.height}px`
  ghost.style.transform = `translate3d(${dx}px, ${dy}px, 0) scale(${scale})`

  // Commit the starting pose without a transition, then hand control back to
  // the stylesheet so the release frame is the only animated change.
  void ghost.offsetWidth
  ghost.style.transition = ''
  requestAnimationFrame(() => {
    ghost.style.transform = 'translate3d(0, 0, 0) scale(1)'
    ghost.style.borderRadius = '2px'
  })
  ghost.addEventListener('transitionend', event => {
    if (event.propertyName === 'transform') land()
  })
  // A dropped frame or a cancelled transition must never strand the ghost.
  window.setTimeout(land, FLIGHT_MS + 480)
}

function holdViewerPhoto() {
  activeFlights += 1
  if (activeFlights === 1) document.documentElement.setAttribute(MORPH_ATTRIBUTE, '')
  return () => {
    activeFlights = Math.max(0, activeFlights - 1)
    if (activeFlights === 0) document.documentElement.removeAttribute(MORPH_ATTRIBUTE)
  }
}

/**
 * Lift the thumbnail out of `source`, open the viewer, and fly the photo into
 * the exact rect the viewer paints it at. Falls back to a plain open whenever
 * anything about the journey cannot be measured.
 */
export function flyPhotoIntoViewer(
  source: HTMLElement | null | undefined,
  ratio: number,
  open: () => void,
) {
  const image = thumbnailOf(source)
  if (!source || !image || reducedMotion() || !image.complete || image.naturalWidth === 0) {
    open()
    return
  }
  const from = visibleRect(image)
  if (from.width < 48 || from.height < 48) {
    open()
    return
  }

  const ghost = createGhost(image, from)
  const release = holdViewerPhoto()
  open()

  /* Some viewers open on the next frame, others after fetching a page of
     photos. The print waits at the frame it came from until the destination
     exists, then travels — so the journey is never cut short. */
  const deadline = performance.now() + 600
  const depart = () => {
    const to = viewerPhotoRect(ratio)
    if (to && to.width >= 2) {
      glide(ghost, from, to, release)
      return
    }
    if (performance.now() > deadline) {
      release()
      ghost.remove()
      return
    }
    requestAnimationFrame(depart)
  }
  requestAnimationFrame(depart)
}

/**
 * Return the photo to its frame while the viewer dissolves away. The viewer's
 * own copy is held invisible for the length of the return, so the print the
 * reader sees travelling is the only copy of the photo on screen.
 */
export function flyPhotoBackTo(source: HTMLElement | null | undefined, ratio: number) {
  if (!source || !source.isConnected || reducedMotion()) return
  const image = thumbnailOf(source)
  const target = image ? visibleRect(image) : null
  if (!target || target.width < 48 || target.height < 48) return
  const from = viewerPhotoRect(ratio)
  if (!from) return

  const release = holdViewerPhoto()
  const ghost = createGhost(image!, from)
  glide(ghost, from, target, () => {
    release()
    // The frame receives the print with a single soft ring.
    source.classList.remove('ts-print-landed')
    void source.offsetWidth
    source.classList.add('ts-print-landed')
    window.setTimeout(() => source.classList.remove('ts-print-landed'), 700)
  })
}

/** Small helper so call sites do not repeat the aspect maths. */
export function aspectOf(width?: number | null, height?: number | null): number {
  return width && height ? width / height : 0
}