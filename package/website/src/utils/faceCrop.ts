import type { CSSProperties } from 'vue'

interface FaceCropInput {
  face_rect?: number[] | null
}

/**
 * Build an image style that centers a detected face in a square container.
 * `face_rect` uses relative coordinates: [x1, y1, x2, y2].
 */
export function getFaceCropStyle(cover?: FaceCropInput | null): CSSProperties {
  const rect = cover?.face_rect
  if (!rect || rect.length !== 4) return {}

  const [x1, y1, x2, y2] = rect
  const faceWidth = x2 - x1
  const faceHeight = y2 - y1
  if (faceWidth <= 0 || faceHeight <= 0) return {}

  // Keep the face at roughly 62.5% of the container's larger dimension.
  const scaleFactor = 1.6
  const widthPercent = 100 / (faceWidth * scaleFactor)
  const heightPercent = 100 / (faceHeight * scaleFactor)
  const leftPercent = ((x1 + x2) / 2) * 100
  const topPercent = ((y1 + y2) / 2) * 100

  const style: CSSProperties = {
    left: '50%',
    top: '50%',
    transform: `translate(-${leftPercent.toFixed(2)}%, -${topPercent.toFixed(2)}%)`,
  }

  if (widthPercent < heightPercent) {
    style.width = `${widthPercent.toFixed(2)}%`
    style.height = 'auto'
  } else {
    style.width = 'auto'
    style.height = `${heightPercent.toFixed(2)}%`
  }

  return style
}
