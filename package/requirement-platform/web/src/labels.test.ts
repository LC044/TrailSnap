import { describe, expect, it } from 'vitest'

import { formatDateTime, parseServerDate } from './labels'


describe('server timestamp formatting', () => {
  it('treats timezone-less SQLite timestamps as UTC', () => {
    expect(parseServerDate('2026-09-09T17:07:07').toISOString()).toBe('2026-09-09T17:07:07.000Z')
    expect(formatDateTime('2026-09-09T17:07:07')).toContain('2026/09/10 01:07:07')
  })

  it('preserves timestamps that already include a timezone', () => {
    expect(parseServerDate('2026-09-10T01:07:07+08:00').toISOString()).toBe('2026-09-09T17:07:07.000Z')
  })
})
