export interface ZoomViewport { width: number; height: number }
export interface PhotoPan { x: number; y: number }

export function constrainPhotoPan(pan: PhotoPan, scale: number, viewport: ZoomViewport, image: ZoomViewport): PhotoPan {
  if (scale <= 1 || !viewport.width || !viewport.height || !image.width || !image.height) return { x: 0, y: 0 }
  const fit = Math.min(viewport.width / image.width, viewport.height / image.height)
  const maxX = Math.max(0, (image.width * fit * scale - viewport.width) / 2)
  const maxY = Math.max(0, (image.height * fit * scale - viewport.height) / 2)
  return { x: maxX ? Math.max(-maxX, Math.min(maxX, pan.x)) : 0, y: maxY ? Math.max(-maxY, Math.min(maxY, pan.y)) : 0 }
}

// Translations are screen pixels: translating before scaling avoids multiplying drag speed.
export function zoomPhotoAt(pan: PhotoPan, oldScale: number, newScale: number, point: PhotoPan): PhotoPan {
  const ratio = newScale / oldScale
  return { x: point.x + (pan.x - point.x) * ratio, y: point.y + (pan.y - point.y) * ratio }
}
