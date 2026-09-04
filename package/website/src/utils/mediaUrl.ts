import { toServerUrl } from '@/config/server'

export type ThumbnailSize = 'small' | 'medium'

function currentUserId(): string | null {
  try {
    const raw = localStorage.getItem('user_info')
    if (!raw) return null
    const value = JSON.parse(raw) as { id?: unknown }
    return typeof value.id === 'string' && value.id ? value.id : null
  } catch {
    return null
  }
}

/**
 * Build the canonical thumbnail URL.
 *
 * Owner-qualified URLs let FastAPI derive the on-disk thumbnail path without
 * querying the photos table. The legacy fallback keeps login/bootstrap and
 * older mocked responses working before user information is available.
 */
export function thumbnailUrl(
  photoId: string,
  size: ThumbnailSize = 'small',
  ownerId: string | null = currentUserId(),
): string {
  return toServerUrl(thumbnailPath(photoId, size, ownerId))
}

export function thumbnailPath(
  photoId: string,
  size: ThumbnailSize = 'small',
  ownerId: string | null = currentUserId(),
): string {
  const route = ownerId
    ? `/api/medias/${ownerId}/${photoId}/thumbnail`
    : `/api/medias/${photoId}/thumbnail`
  const query = size === 'small' ? '' : `?size=${size}`
  return `${route}${query}`
}

const UUID_PATTERN = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
const THUMBNAIL_PATTERN = new RegExp(
  `/medias/(?:${UUID_PATTERN}/)?(${UUID_PATTERN})/thumbnail(?:\\?[^#]*)?`,
  'i',
)

/** Convert either legacy or owner-qualified thumbnail URLs to the file route. */
export function thumbnailToFileUrl(url: string): string {
  return url.replace(THUMBNAIL_PATTERN, (_match, photoId: string) => `/medias/${photoId}/file`)
}

/** Extract the photo id without confusing an owner id for a photo id. */
export function photoIdFromMediaUrl(url: string): string | null {
  const thumbnailMatch = url.match(THUMBNAIL_PATTERN)
  if (thumbnailMatch?.[1]) return thumbnailMatch[1]
  const fileMatch = url.match(new RegExp(`/medias/(${UUID_PATTERN})(?:/file)?`, 'i'))
  return fileMatch?.[1] || null
}
