import type { CSSProperties } from 'vue'

interface FaceCropInput {
  face_rect?: number[] | null
}

export const FACE_CROP_SCALE = 1.6

export function getFaceCropRegion(rect?: number[] | null) {
  if (!rect || rect.length !== 4 || !rect.every(Number.isFinite)) return null
  const [x1, y1, x2, y2] = rect
  if (x2 <= x1 || y2 <= y1) return null
  return { centerX: (x1 + x2) / 2, centerY: (y1 + y2) / 2, width: x2 - x1, height: y2 - y1 }
}

/**
 * Build an image style that centers a detected face in a square container.
 * `face_rect` uses relative coordinates: [x1, y1, x2, y2].
 */
export function getFaceCropStyle(cover?: FaceCropInput | null): CSSProperties {
  const region = getFaceCropRegion(cover?.face_rect)
  if (!region) return {}
  const { width: faceWidth, height: faceHeight, centerX, centerY } = region

  // Keep the face at roughly 62.5% of the container's larger dimension.
  const scaleFactor = FACE_CROP_SCALE
  const widthPercent = 100 / (faceWidth * scaleFactor)
  const heightPercent = 100 / (faceHeight * scaleFactor)
  const leftPercent = centerX * 100
  const topPercent = centerY * 100

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
