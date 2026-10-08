export function getMomentPhotos<T extends { id: number | string }>(photos: T[], ids?: (number | string)[]): T[] {
  if (!ids?.length) return photos.slice(0, 9)
  const byId = new Map(photos.map(photo => [photo.id, photo]))
  return ids.flatMap(id => {
    const photo = byId.get(id)
    return photo ? [photo] : []
  })
}

export function getMomentSinglePhotoSize(photo?: { width?: number; height?: number }) {
  const ratio = photo?.width && photo?.height ? photo.width / photo.height : 240 / 250
  const height = Math.min(240 / ratio, 250)
  return { width: Math.round(height * ratio), height: Math.round(height) }
}
