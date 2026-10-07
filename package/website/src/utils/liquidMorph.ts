import { fluidEase } from './motion'

/** Gather a copy of the capsule surface in place, then carry the droplet into the panel. */
export function liquidFrames(from: DOMRect, to: DOMRect, radius: string, opening: boolean, surface: { backgroundColor: string; backdropFilter: string; boxShadow: string }): Keyframe[] {
  const capsule = opening ? from : to
  const panel = opening ? to : from
  const size = Math.min(24, capsule.height * .6)
  const x = capsule.left + (capsule.width - size) / 2
  const beadY = capsule.top + (capsule.height - size) / 2
  const frame = (left: number, top: number, width: number, height: number, round: string, offset: number): Keyframe => ({
    left: `${left}px`, top: `${top}px`, width: `${width}px`, height: `${height}px`, borderRadius: round, offset, easing: fluidEase,
  })
  const frames = [
    { ...frame(capsule.left, capsule.top, capsule.width, capsule.height, `${capsule.height / 2}px`, 0), backgroundColor: 'transparent', backdropFilter: 'none', boxShadow: 'none', opacity: opening ? 1 : 0 },
    { ...frame(capsule.left + capsule.width * .24, capsule.top + capsule.height * .06, capsule.width * .52, capsule.height * .88, `${capsule.height / 2}px`, .16), backgroundColor: 'transparent', backdropFilter: 'none', boxShadow: 'none' },
    { ...frame(x, beadY, size, size, `${size / 2}px`, .32), backgroundColor: surface.backgroundColor, backdropFilter: 'none', boxShadow: surface.boxShadow },
    frame(x + 1, Math.max(capsule.bottom + 6, panel.top), size - 2, size + 2, '46% 54% 50% 50% / 38% 38% 62% 62%', .44),
    frame(panel.left - panel.width * .012, panel.top - panel.height * .012, panel.width * 1.024, panel.height * 1.024, radius, .78),
    frame(panel.left + panel.width * .002, panel.top + panel.height * .002, panel.width * .996, panel.height * .996, radius, .91),
    frame(panel.left, panel.top, panel.width, panel.height, radius, 1),
  ]
  frames.forEach(item => {
    item.opacity ??= 1
    item.backgroundColor ??= surface.backgroundColor
    item.backdropFilter ??= surface.backdropFilter
    item.boxShadow ??= surface.boxShadow
  })
  if (opening) return frames
  return frames.reverse().map(item => ({ ...item, offset: 1 - Number(item.offset) }))
}

