export const conditionSearchLabels: Record<string, string> = {
  person: '人物', location: '地点', ocr: '文字', album: '相册',
  folder: '文件夹', filename: '文件', tag: '标签', scene: '景区', date: '日期',
}

export const isConditionSearch = (type: unknown): boolean =>
  typeof type === 'string' && Object.hasOwn(conditionSearchLabels, type)

export const formatConditionFilter = (key: string, value: string | number): string => {
  const labels: Record<string, Record<string, string>> = {
    file_types: { image: '图片', video: '视频', live_photo: '实况图', panorama: '360° 全景' },
    image_types: { Camera: '相机', Screenshot: '截屏', Other: '其他' },
  }
  if (key === 'years') return `${value}年`
  return labels[key]?.[String(value)] ?? String(value)
}
