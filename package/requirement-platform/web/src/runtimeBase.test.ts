import { describe, expect, it } from 'vitest'

import { resolveBasePath } from './runtimeBase'


describe('deployment base path', () => {
  it('falls back to root when the container has not injected the token', () => {
    expect(resolveBasePath('__RP_BASE_PATH__/', 'https://example.com/issues/dashboard')).toBe('/')
    expect(resolveBasePath('/__RP_BASE_PATH__/', 'https://example.com/')).toBe('/')
    expect(resolveBasePath(null, 'https://example.com/')).toBe('/')
  })

  it('normalizes the injected href to a path with a trailing slash', () => {
    expect(resolveBasePath('/issues/', 'https://example.com/issues/dashboard')).toBe('/issues/')
    expect(resolveBasePath('/issues', 'https://example.com/issues/dashboard')).toBe('/issues/')
    expect(resolveBasePath('/feedback/issues/', 'https://example.com/')).toBe('/feedback/issues/')
    expect(resolveBasePath('/', 'https://example.com/dashboard')).toBe('/')
  })

  it('ignores the current SPA route when resolving the base', () => {
    expect(resolveBasePath('/issues/', 'https://example.com/issues/requirements/REQ-12')).toBe('/issues/')
    expect(resolveBasePath('/issues/', 'https://example.com/issues/settings/ai?x=1#hash')).toBe('/issues/')
  })

  it('degrades gracefully on an unusable document URL', () => {
    expect(resolveBasePath('/issues/', 'not-a-url')).toBe('/')
  })
})
