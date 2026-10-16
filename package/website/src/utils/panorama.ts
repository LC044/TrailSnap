export interface PanoramaGeometry {
  fullWidth: number
  fullHeight: number
  croppedWidth: number
  croppedHeight: number
  croppedX: number
  croppedY: number
  poseHeading?: number
  posePitch?: number
  poseRoll?: number
  initialHeading?: number
  initialPitch?: number
  initialFov?: number
}

export function textureGeometry(data: PanoramaGeometry, width: number, height: number, high = false) {
  const scale = high ? 1 : Math.min(1, 4096 / data.fullWidth)
  const textureWidth = Math.max(1, Math.round(width * scale))
  const textureHeight = Math.max(1, Math.round(height * scale))
  const sx = textureWidth / data.croppedWidth, sy = textureHeight / data.croppedHeight
  return {
    isEquirectangular: true as const,
    initialHeading: data.initialHeading, initialPitch: data.initialPitch, initialFov: data.initialFov,
    fullWidth: Math.round(data.fullWidth * sx), fullHeight: Math.round(data.fullHeight * sy),
    croppedWidth: textureWidth, croppedHeight: textureHeight,
    croppedX: Math.round(data.croppedX * sx), croppedY: Math.round(data.croppedY * sy),
    poseHeading: data.poseHeading || 0, posePitch: data.posePitch || 0, poseRoll: data.poseRoll || 0,
  }
}

export function canUseHighResolution(width: number, height: number, maxTexture: number, memory = 4) {
  return width > 0 && height > 0 && Math.max(width, height) > 4096
    && Math.max(width, height) <= Math.min(8192, maxTexture)
    && width * height <= 33554432 && memory >= 4
}
