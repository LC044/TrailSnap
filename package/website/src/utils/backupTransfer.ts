export interface BackupNetworkStatus {
  connected: boolean
  wifi: boolean
  unmetered: boolean
}

export interface TransferTuning {
  isLan: boolean
  metered: boolean
  hashConcurrency: number
  mediaConcurrency: number
  chunkConcurrency: number
  chunkSize: number
  maxInFlightBytes: number
  maxAttempts: number
}

export interface BackupPresence {
  existing: ReadonlySet<string>
  complete: ReadonlySet<string>
  livePhotos: ReadonlySet<string>
  hashes?: ReadonlySet<string>
}

export type BackupUploadAction = 'skip' | 'upload' | 'replace'

export function backupUploadAction(
  backupKey: string,
  isLivePhoto: boolean,
  presence: BackupPresence,
): BackupUploadAction {
  const complete = isLivePhoto
    ? presence.livePhotos.has(backupKey)
    : presence.complete.has(backupKey)
  if (complete) return 'skip'
  return presence.existing.has(backupKey) ? 'replace' : 'upload'
}

const MB = 1024 * 1024
const DEFAULT_CHUNK_THRESHOLD = 5 * MB
const LAN_CHUNK_THRESHOLD = 16 * MB

export function isLanServerUrl(value: string) {
  try {
    const hostname = new URL(value).hostname.toLowerCase().replace(/^\[|\]$/g, '')
    if (hostname === 'localhost' || hostname.endsWith('.local') || hostname === '::1') return true
    if (hostname.startsWith('10.') || hostname.startsWith('192.168.') || hostname.startsWith('127.')) return true
    const match = hostname.match(/^172\.(\d+)\./)
    if (match && Number(match[1]) >= 16 && Number(match[1]) <= 31) return true
    return hostname.startsWith('fc') || hostname.startsWith('fd') || hostname.startsWith('fe80:')
  } catch {
    return false
  }
}

export function initialTransferTuning(serverUrl: string, network: BackupNetworkStatus): TransferTuning {
  const isLan = network.wifi && isLanServerUrl(serverUrl)
  const metered = !network.unmetered
  if (isLan) {
    return {
      isLan, metered, hashConcurrency: 4, mediaConcurrency: 4, chunkConcurrency: 2,
      chunkSize: 8 * MB, maxInFlightBytes: 160 * MB, maxAttempts: 2,
    }
  }
  return {
    isLan, metered, hashConcurrency: metered ? 1 : 2, mediaConcurrency: 1, chunkConcurrency: 1,
    chunkSize: metered ? MB : 2 * MB,
    maxInFlightBytes: metered ? 16 * MB : 32 * MB,
    maxAttempts: 3,
  }
}

export function adaptTransferTuning(
  current: TransferTuning,
  speedBytesPerSecond: number,
  recentFailure = false,
): TransferTuning {
  if (recentFailure) {
    return {
      ...current,
      hashConcurrency: 1,
      mediaConcurrency: 1,
      chunkConcurrency: 1,
      chunkSize: Math.min(current.chunkSize, current.metered ? MB : 2 * MB),
      maxInFlightBytes: Math.min(current.maxInFlightBytes, current.metered ? 16 * MB : 32 * MB),
    }
  }
  if (speedBytesPerSecond <= 0) return current
  if (current.isLan) {
    if (speedBytesPerSecond >= 30 * MB) {
      return {
        ...current, hashConcurrency: 6, mediaConcurrency: 8, chunkConcurrency: 3,
        chunkSize: 16 * MB, maxInFlightBytes: 256 * MB,
      }
    }
    if (speedBytesPerSecond >= 12 * MB) {
      return {
        ...current, hashConcurrency: 4, mediaConcurrency: 6, chunkConcurrency: 2,
        chunkSize: 8 * MB, maxInFlightBytes: 192 * MB,
      }
    }
    if (speedBytesPerSecond < 3 * MB) {
      return {
        ...current, hashConcurrency: 2, mediaConcurrency: 3, chunkConcurrency: 1,
        chunkSize: 4 * MB, maxInFlightBytes: 64 * MB,
      }
    }
    return {
      ...current, hashConcurrency: 4, mediaConcurrency: 4, chunkConcurrency: 2,
      chunkSize: 8 * MB, maxInFlightBytes: 160 * MB,
    }
  }
  if (!current.metered && speedBytesPerSecond >= 5 * MB) {
    return { ...current, mediaConcurrency: 2, chunkConcurrency: 2, chunkSize: 4 * MB, maxInFlightBytes: 64 * MB }
  }
  return {
    ...current,
    mediaConcurrency: 1,
    chunkConcurrency: 1,
    chunkSize: current.metered ? MB : 2 * MB,
    maxInFlightBytes: current.metered ? 16 * MB : 32 * MB,
  }
}

export function shouldUseChunkedUpload(size: number, tuning: TransferTuning) {
  const threshold = tuning.isLan
    ? Math.max(LAN_CHUNK_THRESHOLD, tuning.chunkSize)
    : DEFAULT_CHUNK_THRESHOLD
  return size > threshold
}

export async function mapWithConcurrency<T, R>(
  items: readonly T[],
  concurrency: number,
  mapper: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  if (!items.length) return []
  const results = new Array<R>(items.length)
  let nextIndex = 0
  const worker = async () => {
    while (true) {
      const index = nextIndex++
      if (index >= items.length) return
      results[index] = await mapper(items[index], index)
    }
  }
  const workers = Math.min(items.length, Math.max(1, Math.floor(concurrency)))
  await Promise.all(Array.from({ length: workers }, worker))
  return results
}

export function takeTransferBatch<T extends { size: number }>(items: T[], tuning: TransferTuning) {
  if (!items.length) return []
  const batch: T[] = []
  let bytes = 0
  for (const item of items) {
    if (batch.length >= tuning.mediaConcurrency) break
    const size = Math.max(0, item.size)
    if (batch.length && bytes + size > tuning.maxInFlightBytes) break
    batch.push(item)
    bytes += size
  }
  return batch
}
