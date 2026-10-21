import { FACE_CROP_SCALE, getFaceCropRegion } from './faceCrop'

// Face coordinates refer to image pixels, excluding object-contain letterboxing.
export function containFaceRect(rect: number[] | null, width: number, height: number, naturalWidth: number, naturalHeight: number) {
  if (!rect || rect.length !== 4 || !rect.every(Number.isFinite) || Math.min(width, height, naturalWidth, naturalHeight) <= 0) return null
  const [x1, y1, x2, y2] = rect
  if (x1 < 0 || y1 < 0 || x2 > 1 || y2 > 1 || x2 <= x1 || y2 <= y1) return null
  const ratio = Math.min(width / naturalWidth, height / naturalHeight)
  const renderedWidth = naturalWidth * ratio
  const renderedHeight = naturalHeight * ratio
  return { x: (width - renderedWidth) / 2 + x1 * renderedWidth,
    y: (height - renderedHeight) / 2 + y1 * renderedHeight,
    width: (x2 - x1) * renderedWidth, height: (y2 - y1) * renderedHeight }
}

export function containFaceCircle(rect: number[] | null, width: number, height: number, naturalWidth: number, naturalHeight: number) {
  const region = getFaceCropRegion(rect)
  const box = containFaceRect(rect, width, height, naturalWidth, naturalHeight)
  if (!region || !box) return null
  const ratio = Math.min(width / naturalWidth, height / naturalHeight)
  const centerX = (width - naturalWidth * ratio) / 2 + region.centerX * naturalWidth * ratio
  const centerY = (height - naturalHeight * ratio) / 2 + region.centerY * naturalHeight * ratio
  const diameter = Math.max(box.width, box.height) * FACE_CROP_SCALE
  return { x: centerX - diameter / 2, y: centerY - diameter / 2, width: diameter, height: diameter }
}
