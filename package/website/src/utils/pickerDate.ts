export const padDatePart = (value: number) => String(value).padStart(2, '0')

export function daysInMonth(year: number, month: number) {
  return new Date(year, month, 0).getDate()
}

// Local calendar values must not pass through UTC when editing photo/ticket dates.
export function parsePickerDate(value: unknown, fallback = new Date()): Date {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return new Date(value)
  if (typeof value === 'number') {
    const date = new Date(value)
    if (!Number.isNaN(date.getTime())) return date
  }
  if (typeof value === 'string' && value) {
    const match = value.match(/^(\d{4})-(\d{2})(?:-(\d{2}))?(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?$/)
    if (match) return new Date(+match[1]!, +match[2]! - 1, +(match[3] || 1), +(match[4] || 0), +(match[5] || 0), +(match[6] || 0))
    const date = new Date(value)
    if (!Number.isNaN(date.getTime())) return date
  }
  return new Date(fallback)
}

export function formatPickerDate(date: Date, pattern: string) {
  const parts: Record<string, string> = {
    YYYY: String(date.getFullYear()), MM: padDatePart(date.getMonth() + 1), DD: padDatePart(date.getDate()),
    HH: padDatePart(date.getHours()), mm: padDatePart(date.getMinutes()), ss: padDatePart(date.getSeconds()),
  }
  return pattern.replace(/YYYY|MM|DD|HH|mm|ss/g, token => parts[token]!)
}

/** Keep new dialogs above already-open panels, including photo fullscreen overlays. */
export function nextDialogZIndex(nextZIndex: () => number) {
  let highest = 0
  document.querySelectorAll<HTMLElement>('[role="dialog"], .ts-desktop-menu, .photo-lightbox-shell').forEach(panel => {
    if (!panel.getClientRects().length) return
    for (let node: HTMLElement | null = panel; node; node = node.parentElement) {
      highest = Math.max(highest, Number.parseInt(getComputedStyle(node).zIndex) || 0)
    }
  })
  let value = nextZIndex()
  while (value <= highest) value = nextZIndex()
  return value
}
