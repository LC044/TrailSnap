/** Wrap complete text into paper-sized leaves without dropping Unicode characters. */
export function paginateDiaryText(text: string, width: number, linesPerPage: number, measure: (text: string) => number): string[] {
  const lines: string[] = []
  let line = ''
  for (const character of Array.from(text.replaceAll('\r', ''))) {
    if (character === '\n') { lines.push(line); line = ''; continue }
    if (line && measure(line + character) > Math.max(1, width)) {
      lines.push(line)
      line = character
    } else line += character
  }
  lines.push(line)
  const count = Math.max(1, Math.floor(linesPerPage))
  const pages: string[] = []
  for (let index = 0; index < lines.length; index += count) pages.push(lines.slice(index, index + count).join('\n'))
  return pages
}

/** A deliberate horizontal or vertical swipe turns a page; taps/diagonals do not. */
export function diarySwipeDirection(dx: number, dy: number, duration: number): number {
  const horizontal = Math.abs(dx) > Math.abs(dy) * 1.15
  const vertical = Math.abs(dy) > Math.abs(dx) * 1.15
  const distance = horizontal ? dx : vertical ? dy : 0
  return Math.abs(distance) >= (duration < 280 ? 18 : 30) ? (distance < 0 ? 1 : -1) : 0
}
