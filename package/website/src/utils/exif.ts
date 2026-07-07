import piexif from 'piexifjs'

/**
 * 将 ArrayBuffer 转为二进制字符串（piexifjs 的 load/dump/insert 都基于二进制字符串）。
 * 分块处理以避免 String.fromCharCode.apply 栈溢出。
 */
function arrayBufferToBinaryString(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  const CHUNK = 0x8000
  let binary = ''
  for (let i = 0; i < bytes.length; i += CHUNK) {
    const slice = bytes.subarray(i, i + CHUNK)
    binary += String.fromCharCode.apply(null, Array.from(slice) as unknown as number[])
  }
  return binary
}

/** 将二进制字符串转回 Uint8Array。 */
function binaryStringToUint8Array(binary: string): Uint8Array {
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

/** 读取一个图片 Blob 的实际像素尺寸。 */
async function getBlobDimensions(blob: Blob): Promise<{ width: number; height: number } | null> {
  const url = URL.createObjectURL(blob)
  try {
    const img = new Image()
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('decode failed'))
      img.src = url
    })
    return { width: img.naturalWidth, height: img.naturalHeight }
  } catch {
    return null
  } finally {
    URL.revokeObjectURL(url)
  }
}

/**
 * 将原图的 EXIF 元数据（相机型号、GPS、拍摄时间、参数等）重新嵌入到编辑后的 JPEG 上。
 *
 * 背景：Canvas 导出（toDataURL）会丢失全部 EXIF。这里从原图读取 EXIF 并写回编辑结果，
 * 这样「替换原图」时磁盘文件保留 EXIF，「另存为新图」时后端也能从文件中重新提取到元数据。
 *
 * 关键处理：
 *  - 丢弃 Orientation（方向）标签：现代浏览器解码 <img> 时默认按 EXIF 方向校正（image-orientation: from-image），
 *    因此 Canvas 里的像素已是正向的；若再保留 Orientation，查看器会二次旋转导致方向错误。
 *  - 丢弃 thumbnail：原 EXIF 缩略图对应原图，编辑后已失效。
 *  - 更新 PixelXDimension/PixelYDimension 为编辑后实际尺寸，避免尺寸元数据陈旧。
 *
 * 任意环节失败时返回原始 editedBlob（即不嵌入 EXIF），保证保存流程不中断。
 */
export async function embedExifFromUrl(originalUrl: string, editedBlob: Blob): Promise<Blob> {
  // 仅 JPEG 支持写入 EXIF；编辑器导出的就是 JPEG
  if (!editedBlob.type.includes('jpeg') && !editedBlob.type.includes('jpg')) {
    return editedBlob
  }

  // 1. 读取原图 EXIF
  let origBinary: string
  try {
    const resp = await fetch(originalUrl, { credentials: 'include' })
    if (!resp.ok) throw new Error(`fetch original failed: ${resp.status}`)
    origBinary = arrayBufferToBinaryString(await resp.arrayBuffer())
  } catch (e) {
    console.warn('[exif] 读取原图失败，跳过 EXIF 嵌入:', e)
    return editedBlob
  }

  let exifDict: piexif.ExifDict
  try {
    exifDict = piexif.load(origBinary)
  } catch (e) {
    // 原图无 EXIF 或为非 JPEG（如 PNG/HEIC），piexif.load 会抛错 —— 直接返回编辑结果
    return editedBlob
  }

  // 2. 清理会因编辑而失效的标签
  if (exifDict['0th']) {
    delete exifDict['0th'][piexif.ImageIFD.Orientation]
  }
  // 丢弃陈旧缩略图
  exifDict.thumbnail = undefined

  // 3. 更新尺寸标签为编辑后的实际尺寸
  const dims = await getBlobDimensions(editedBlob)
  if (dims) {
    if (!exifDict.Exif) exifDict.Exif = {}
    exifDict.Exif[piexif.ExifIFD.PixelXDimension] = dims.width
    exifDict.Exif[piexif.ExifIFD.PixelYDimension] = dims.height
  }

  // 4. dump + insert
  try {
    const exifBytes = piexif.dump(exifDict)
    const editedBinary = arrayBufferToBinaryString(await editedBlob.arrayBuffer())
    const newJpegBinary = piexif.insert(exifBytes, editedBinary)
    return new Blob([binaryStringToUint8Array(newJpegBinary)], { type: 'image/jpeg' })
  } catch (e) {
    console.warn('[exif] 嵌入 EXIF 失败，保存不含 EXIF:', e)
    return editedBlob
  }
}
