import type { ObjectDirective } from 'vue'

const svgNamespace = 'http://www.w3.org/2000/svg'
const displacementScale = 56
const surfaces = new WeakMap<HTMLElement, () => void>()
let nextFilterId = 0

function createDisplacementMap(width: number, height: number, radius: number, rimOnly: boolean) {
  const resolution = Math.min(1, 360 / Math.max(width, height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(width * resolution))
  canvas.height = Math.max(1, Math.round(height * resolution))
  const context = canvas.getContext('2d')
  if (!context) return ''

  const image = context.createImageData(canvas.width, canvas.height)
  const halfWidth = width / 2
  const halfHeight = height / 2
  const rim = Math.min(14, halfHeight * .6, halfWidth * .6)
  const magnification = 1 + Math.min(.12, 30 / Math.max(width, height))
  const lensOffset = rimOnly ? 0 : 1 - 1 / magnification
  for (let row = 0; row < canvas.height; row++) {
    const y = (row + .5) * height / canvas.height - halfHeight
    for (let col = 0; col < canvas.width; col++) {
      const x = (col + .5) * width / canvas.width - halfWidth
      const edgeX = Math.abs(x) - (halfWidth - radius)
      const edgeY = Math.abs(y) - (halfHeight - radius)
      const cornerX = Math.max(edgeX, 0)
      const cornerY = Math.max(edgeY, 0)
      const cornerLength = Math.hypot(cornerX, cornerY)
      const distance = cornerLength + Math.min(Math.max(edgeX, edgeY), 0) - radius
      const depth = Math.min(1, Math.max(0, (distance + rim) / rim))
      const bend = 11 * depth * depth
      const normalX = Math.sign(x) * (cornerLength ? cornerX / cornerLength : Number(edgeX > edgeY))
      const normalY = Math.sign(y) * (cornerLength ? cornerY / cornerLength : Number(edgeX <= edgeY))
      const light = -normalX * .5 - normalY * .866
      const offset = (row * canvas.width + col) * 4
      // Red and green re-sample around the center. Blue carries the directional rim reflection.
      image.data[offset] = 127.5 - (x * lensOffset + normalX * bend) * 255 / displacementScale
      image.data[offset + 1] = 127.5 - (y * lensOffset + normalY * bend) * 255 / displacementScale
      image.data[offset + 2] = 255 * depth ** 3 * (Math.max(light, 0) ** 3 + .24 * Math.max(-light, 0) ** 4)
      image.data[offset + 3] = 255
    }
  }
  context.putImageData(image, 0, 0)
  return canvas.toDataURL()
}

function attachRefraction(element: HTMLElement, rimOnly: boolean) {
  // Recognizing the CSS syntax does not guarantee backdrop displacement.
  if (!/\b(?:Headless)?Chrom(?:e|ium)\//.test(navigator.userAgent) || !CSS.supports('backdrop-filter', 'url("#test")')) return

  const svg = document.createElementNS(svgNamespace, 'svg')
  const filter = document.createElementNS(svgNamespace, 'filter')
  const map = document.createElementNS(svgNamespace, 'feImage')
  const displacement = document.createElementNS(svgNamespace, 'feDisplacementMap')
  const reflection = document.createElementNS(svgNamespace, 'feColorMatrix')
  const composite = document.createElementNS(svgNamespace, 'feComposite')
  filter.id = `ts-glass-refraction-${++nextFilterId}`
  svg.setAttribute('aria-hidden', 'true')
  svg.setAttribute('width', '0')
  svg.setAttribute('height', '0')
  svg.style.position = 'absolute'
  filter.setAttribute('filterUnits', 'userSpaceOnUse')
  filter.setAttribute('x', '0')
  filter.setAttribute('y', '0')
  filter.setAttribute('color-interpolation-filters', 'sRGB')
  map.setAttribute('preserveAspectRatio', 'none')
  map.setAttribute('result', 'surface')
  displacement.setAttribute('in', 'SourceGraphic')
  displacement.setAttribute('in2', 'surface')
  displacement.setAttribute('scale', String(rimOnly ? displacementScale * .4 : displacementScale))
  displacement.setAttribute('xChannelSelector', 'R')
  displacement.setAttribute('yChannelSelector', 'G')
  displacement.setAttribute('result', 'lens')
  reflection.setAttribute('in', 'surface')
  reflection.setAttribute('values', '0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 .4 0 0')
  reflection.setAttribute('result', 'highlight')
  composite.setAttribute('in', 'highlight')
  composite.setAttribute('in2', 'lens')
  composite.setAttribute('operator', 'over')
  filter.append(map, displacement, reflection, composite)
  svg.append(filter)
  document.body.append(svg)

  const observer = new ResizeObserver(() => {
    const width = element.offsetWidth
    const height = element.offsetHeight
    if (!width || !height) return
    const borderRadius = Number.parseFloat(getComputedStyle(element).borderTopLeftRadius) || 0
    const radius = Math.min(borderRadius, width / 2, height / 2)
    const source = createDisplacementMap(width, height, radius, rimOnly)
    if (!source) return
    filter.setAttribute('width', String(width))
    filter.setAttribute('height', String(height))
    map.setAttribute('width', String(width))
    map.setAttribute('height', String(height))
    map.setAttribute('href', source)
    element.style.setProperty('--glass-refraction', `url("#${filter.id}")`)
  })
  observer.observe(element, { box: 'border-box' })

  surfaces.set(element, () => {
    observer.disconnect()
    svg.remove()
    element.style.removeProperty('--glass-refraction')
    surfaces.delete(element)
  })
}

export const glassRefraction: ObjectDirective<HTMLElement, boolean | undefined> = {
  mounted(element, binding) {
    if (binding.value !== false) attachRefraction(element, Boolean(binding.modifiers.rim))
  },
  updated(element, { oldValue, value, modifiers }) {
    if (oldValue === value) return
    if (value === false) surfaces.get(element)?.()
    else if (!surfaces.has(element)) attachRefraction(element, Boolean(modifiers.rim))
  },
  beforeUnmount(element) {
    surfaces.get(element)?.()
  },
}
