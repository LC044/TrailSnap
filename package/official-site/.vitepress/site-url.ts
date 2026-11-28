export const SITE_ORIGIN = 'https://trailsnap.cn'

// The hosting platform redirects .html URLs and normalizes directory indexes to a trailing slash.
export function sitePagePath(markdownPath: string): string {
  return '/' + markdownPath.replace(/\\/g, '/').replace(/^\/+/, '')
    .replace(/(^|\/)index\.md$/, '$1').replace(/\.md$/, '')
}
