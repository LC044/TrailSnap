/** Motion primitives shared by pointer gestures and controls. Velocities are px/ms. */
export const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
export const fluidEase = 'cubic-bezier(.22, .82, .24, 1)'

export function rubberBand(value: number, min: number, max: number) {
  const edge = Math.max(min, Math.min(max, value))
  const distance = value - edge
  return edge + Math.sign(distance) * (1 - 1 / (Math.abs(distance) / 180 + 1)) * 72
}

export function snapAnchor(position: number, velocity: number, anchors: number[]) {
  const projected = position + Math.max(-2.5, Math.min(2.5, velocity)) * 180
  return anchors.reduce((best, anchor) => Math.abs(anchor - projected) < Math.abs(best - projected) ? anchor : best)
}

export function spring(from: number, to: number, velocity: number, update: (value: number) => void, done = () => {}) {
  let frame = 0, last = performance.now(), value = from, speed = velocity * 1000
  if (reducedMotion()) { update(to); done(); return () => {} }
  const tick = (now: number) => {
    const dt = Math.min((now - last) / 1000, .032)
    last = now
    // Substeps keep the damped spring stable after a dropped frame.
    const steps = Math.max(1, Math.ceil(dt / .008))
    for (let i = 0; i < steps; i++) {
      speed += ((to - value) * 380 - speed * 34) * dt / steps
      value += speed * dt / steps
    }
    update(value)
    if (Math.abs(to - value) < .3 && Math.abs(speed) < 3) { update(to); done() }
    else frame = requestAnimationFrame(tick)
  }
  frame = requestAnimationFrame(tick)
  return () => cancelAnimationFrame(frame)
}
