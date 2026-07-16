// 照片网格「小/中/大」尺寸口径的唯一来源。
// 原照片页（composables/useVirtualLayout.ts）与文件夹页（views/album/folder）
// 均复用本文件，保证列数/间距完全一致，避免口径漂移。

export type ViewSize = 'sm' | 'md' | 'lg'

/**
 * 根据可用宽度与视图档位计算列数。
 * 断点与列数与原照片页保持一致：
 *   小 sm：4 / 6 / 8 / 12
 *   中 md：3 / 5 / 6 / 8
 *   大 lg：2 / 3 / 4 / 6
 * （断点：<640 / <768 / <1024 / 其余）
 */
export function getPhotoColumns(width: number, viewSize: ViewSize): number {
  const w = width || (typeof window !== 'undefined' ? window.innerWidth : 1024)
  if (viewSize === 'sm') return w < 640 ? 4 : (w < 768 ? 6 : (w < 1024 ? 8 : 12))
  if (viewSize === 'md') return w < 640 ? 3 : (w < 768 ? 5 : (w < 1024 ? 6 : 8))
  return w < 640 ? 2 : (w < 768 ? 3 : (w < 1024 ? 4 : 6))
}

/** 网格间距（px）：大图档 16，其余 8。与原照片页一致。 */
export function getPhotoGap(viewSize: ViewSize): number {
  return viewSize === 'lg' ? 16 : 8
}
