/**
 * The deployment URL prefix is injected into <base href> by the web container
 * at startup. Reading it at runtime lets a single prebuilt image work at "/"
 * or "/issues" without rebuilding the bundle.
 */
const PLACEHOLDER = '__RP_BASE_PATH__'

/** Pure helper so URL derivation can be unit tested without a DOM. */
export function resolveBasePath(baseHref: string | null | undefined, currentHref: string): string {
  // An unreplaced token means the bundle is served without the container
  // entrypoint (vite preview, static preview, tests) — fall back to root.
  if (!baseHref || baseHref.includes(PLACEHOLDER)) return '/'
  try {
    const path = new URL(baseHref, currentHref).pathname
    return path.endsWith('/') ? path : `${path}/`
  } catch {
    return '/'
  }
}

const detected = typeof document === 'undefined'
  ? '/'
  : resolveBasePath(document.querySelector('base')?.getAttribute('href'), window.location.href)

/** Always ends with "/": "/" at the root, "/issues/" under a prefix. */
export const APP_BASE_PATH = detected

const origin = typeof window === 'undefined' ? '' : window.location.origin
/** Site root without a trailing slash: "https://host" or "https://host/issues". */
export const APP_SITE_URL = `${origin}${APP_BASE_PATH}`.replace(/\/+$/, '')

/** Full external URL for an app page. `path` is relative to the prefix. */
export function appUrl(path = ''): string {
  return `${APP_SITE_URL}/${path.replace(/^\/+/, '')}`
}

/** Axios / fetch base URL. An explicit override still wins (cross-origin API). */
export const API_BASE_URL = import.meta.env.VITE_REQUIREMENT_API_URL || `${APP_BASE_PATH}api`
