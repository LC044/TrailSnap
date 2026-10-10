import { sha256 } from '@noble/hashes/sha256'
import { bytesToHex } from '@noble/hashes/utils'

/** Read bounded slices; never decode or transform the media bytes. */
export async function hashFileChunks(file: Blob, chunkSize: number, onProgress: (loaded: number) => void = () => {}, onChunk?: (index: number, sha256: string) => Promise<void>) {
  if (chunkSize <= 0 || file.size <= 0) throw new Error('文件为空或分块大小无效')
  const hash = sha256.create()
  const chunks: string[] = []
  for (let start = 0; start < file.size; start += chunkSize) {
    const bytes = new Uint8Array(await file.slice(start, start + chunkSize).arrayBuffer())
    hash.update(bytes)
    const digest = bytesToHex(sha256(bytes))
    chunks.push(digest)
    await onChunk?.(chunks.length - 1, digest)
    onProgress(Math.min(start + chunkSize, file.size))
  }
  return { sha256: bytesToHex(hash.digest()), chunks }
}
