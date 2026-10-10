/** Shared by manual uploads and Android gallery backup. No media conversion. */
export async function transferChunks(
  file: Blob, chunkSize: number, concurrency: number,
  send: (index: number, chunk: Blob, progress: (loaded: number) => void) => Promise<void>,
  onProgress: (loaded: number) => void,
) {
  if (chunkSize <= 0 || file.size <= 0) throw new Error('文件为空或分块大小无效')
  const count = Math.ceil(file.size / chunkSize)
  let next = 0
  let failure: unknown
  let loaded = 0
  const progressByIndex = new Map<number, number>()
  const worker = async () => {
    while (!failure) {
      const index = next++
      if (index >= count) return
      const chunk = file.slice(index * chunkSize, Math.min(file.size, (index + 1) * chunkSize))
      const report = (bytes: number) => {
        const current = Math.min(chunk.size, Math.max(0, bytes))
        loaded += current - (progressByIndex.get(index) ?? 0)
        progressByIndex.set(index, current)
        onProgress(loaded)
      }
      try {
        await send(index, chunk, report)
        report(chunk.size)
      } catch (error) { failure = error }
    }
  }
  await Promise.all(Array.from({ length: Math.min(count, Math.max(1, concurrency)) }, worker))
  if (failure) throw failure
  return count
}
