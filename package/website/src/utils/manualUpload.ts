import type { UploadIntegrity } from '@/api/album'
import { transferChunks } from './uploadTransfer'

export const MEDIA_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'tif', 'tiff', 'heic', 'heif', 'mp4', 'mov', 'avi', 'mkv', 'webm'])
export const MEDIA_ACCEPT = 'image/*,video/*,' + [...MEDIA_EXTENSIONS].map(ext => `.${ext}`).join(',')

export function isSupportedMedia(file: Pick<File, 'name' | 'type'>) {
  // Browsers often provide empty or application/octet-stream MIME for HEIC.
  const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
  return MEDIA_EXTENSIONS.has(extension)
}

export function manualTransferSettings(isLan: boolean) {
  return isLan
    ? { fileConcurrency: 4, chunkConcurrency: 2, chunkSize: 8 * 1024 * 1024 }
    : { fileConcurrency: 2, chunkConcurrency: 2, chunkSize: 4 * 1024 * 1024 }
}

export function uploadWindow(length: number, scrollTop: number, viewportHeight = 384) {
  const rowHeight = 88
  const start = Math.max(0, Math.floor(scrollTop / rowHeight) - 3)
  const end = Math.min(length, Math.ceil((scrollTop + viewportHeight) / rowHeight) + 3)
  return { start: Math.min(start, length), end, rowHeight }
}

export interface FileManifest { sha256: string, chunks: string[] }

/** Hash and transfer overlap; worker credits bound the number of prepared chunks. */
export async function uploadStreamingChunks(
  file: File, chunkSize: number, concurrency: number, signal: AbortSignal,
  send: (index: number, chunk: Blob, sha256: string, progress: (loaded: number) => void) => Promise<void>,
  onProgress: (loaded: number) => void,
): Promise<UploadIntegrity> {
  const worker = new Worker(new URL('../workers/uploadHash.worker.ts', import.meta.url), { type: 'module' })
  const active = new Set<Promise<void>>()
  const progress = new Map<number, number>()
  let loaded = 0
  let failed: unknown
  let rejectManifest: (error: unknown) => void = () => {}
  const abort = () => rejectManifest(new DOMException('Upload aborted', 'AbortError'))
  const manifest = new Promise<FileManifest>((resolve, reject) => {
    rejectManifest = reject
    worker.onerror = () => reject(new Error('读取文件校验信息失败'))
    worker.onmessage = event => {
      if (failed || signal.aborted) return
      if (event.data.error) { reject(new Error(event.data.error)); return }
      if (event.data.result) { resolve(event.data.result); return }
      if (event.data.sha256) {
        const { index, sha256 } = event.data
        const chunk = file.slice(index * chunkSize, Math.min(file.size, (index + 1) * chunkSize))
        const report = (bytes: number) => {
          const current = Math.min(chunk.size, Math.max(0, bytes))
          loaded += current - (progress.get(index) || 0)
          progress.set(index, current)
          onProgress(loaded)
        }
        const task = Promise.resolve().then(() => send(index, chunk, sha256, report))
          .then(() => { report(chunk.size); worker.postMessage({ ack: true }) })
          .catch(error => { failed = error; reject(error) })
          .finally(() => active.delete(task))
        active.add(task)
      }
    }
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) abort()
    else worker.postMessage({ file, chunkSize, streaming: true, capacity: Math.max(1, concurrency) })
  })
  try {
    const result = await manifest
    await Promise.all(active)
    if (failed) throw failed
    signal.throwIfAborted()
    return { size: file.size, chunks: result.chunks.length, sha256: result.sha256 }
  } finally {
    worker.terminate()
    signal.removeEventListener('abort', abort)
    await Promise.all(active)
  }
}

export function readFileManifest(file: File, chunkSize: number, signal: AbortSignal, progress: (loaded: number) => void): Promise<FileManifest> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL('../workers/uploadHash.worker.ts', import.meta.url), { type: 'module' })
    const finish = () => { worker.terminate(); signal.removeEventListener('abort', abort) }
    const abort = () => { finish(); reject(new DOMException('Upload aborted', 'AbortError')) }
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) { abort(); return }
    worker.onmessage = event => {
      if (event.data.error) { finish(); reject(new Error(event.data.error)) }
      else if (event.data.result) { finish(); resolve(event.data.result) }
      else progress(event.data.loaded)
    }
    worker.onerror = () => { finish(); reject(new Error('读取文件校验信息失败')) }
    worker.postMessage({ file, chunkSize })
  })
}

/** Index-based workers avoid queue.shift() costs and await every in-flight request. */
export async function uploadOriginalChunks(
  file: File, chunkSize: number, concurrency: number, manifest: FileManifest,
  send: (index: number, chunk: Blob, sha256: string, progress: (loaded: number) => void) => Promise<void>,
  onProgress: (loaded: number) => void,
): Promise<UploadIntegrity> {
  const count = Math.ceil(file.size / chunkSize)
  if (manifest.chunks.length !== count) throw new Error('文件分块校验信息不完整')
  await transferChunks(file, chunkSize, concurrency, (index, chunk, progress) =>
    send(index, chunk, manifest.chunks[index]!, progress), onProgress)
  return { size: file.size, chunks: count, sha256: manifest.sha256 }
}
