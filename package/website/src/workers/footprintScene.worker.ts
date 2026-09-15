import { arcCoordinates, boundaryLines } from '@/utils/footprintScene'

self.onmessage = (event: MessageEvent) => {
  const { id, kind, payload } = event.data
  try {
    const result = kind === 'boundaries'
      ? boundaryLines(payload)
      : payload.routes.map((route: { from: [number, number]; to: [number, number] }) => arcCoordinates(route.from, route.to, payload.raised))
    self.postMessage({ id, result })
  } catch {
    self.postMessage({ id, error: '地图坐标处理失败' })
  }
}
