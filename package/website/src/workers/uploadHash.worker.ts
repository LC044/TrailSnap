import { hashFileChunks } from '../utils/fileIntegrity'

let pending = 0
let release: (() => void) | undefined
self.onmessage = async (event: MessageEvent<{ file: File, chunkSize: number, streaming?: boolean, capacity?: number, ack?: boolean }>) => {
  if (event.data.ack) { pending--; release?.(); release = undefined; return }
  try {
    const result = await hashFileChunks(event.data.file, event.data.chunkSize, loaded => self.postMessage({ loaded }),
      event.data.streaming ? async (index, sha256) => {
        pending++
        self.postMessage({ index, sha256 })
        if (pending >= (event.data.capacity || 2)) await new Promise<void>(resolve => { release = resolve })
      } : undefined)
    self.postMessage({ result })
  } catch (error) {
    self.postMessage({ error: error instanceof Error ? error.message : '无法读取原始文件' })
  }
}
