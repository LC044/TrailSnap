export interface BackupNetworkStatus {
  connected: boolean
  wifi: boolean
  unmetered: boolean
}

export interface TransferTuning {
  isLan: boolean
  metered: boolean
  mediaConcurrency: number
  chunkConcurrency: number
  chunkSize: number
  maxInFlightBytes: number
  maxAttempts: number
}

const MB = 1024 * 1024

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
      isLan, metered, mediaConcurrency: 3, chunkConcurrency: 2,
      chunkSize: 8 * MB, maxInFlightBytes: 96 * MB, maxAttempts: 2,
    }
  }
  return {
    isLan, metered, mediaConcurrency: 1, chunkConcurrency: 1,
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
      mediaConcurrency: 1,
      chunkConcurrency: 1,
      chunkSize: Math.min(current.chunkSize, current.metered ? MB : 2 * MB),
      maxInFlightBytes: Math.min(current.maxInFlightBytes, current.metered ? 16 * MB : 32 * MB),
    }
  }
  if (speedBytesPerSecond <= 0) return current
  if (current.isLan) {
    if (speedBytesPerSecond >= 20 * MB) {
      return { ...current, mediaConcurrency: 4, chunkConcurrency: 2, chunkSize: 8 * MB, maxInFlightBytes: 128 * MB }
    }
    if (speedBytesPerSecond < 2 * MB) {
      return { ...current, mediaConcurrency: 2, chunkConcurrency: 1, chunkSize: 4 * MB, maxInFlightBytes: 64 * MB }
    }
    return { ...current, mediaConcurrency: 3, chunkConcurrency: 2, chunkSize: 8 * MB, maxInFlightBytes: 96 * MB }
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
