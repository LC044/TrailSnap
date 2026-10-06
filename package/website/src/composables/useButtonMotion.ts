import { reducedMotion } from '@/utils/motion'

/** Delegate feedback so teleported and dynamically created controls share it. */
export function registerButtonMotion() {
  const selector = '.ts-button, .ts-icon-button, .ts-glass-button, .el-button, .ts-action-row'
  const animations = new WeakMap<HTMLElement, Animation>()
  const pressed = new Map<number | string, HTMLElement>()
  const control = (target: EventTarget | null) => {
    const button = target instanceof Element ? target.closest<HTMLElement>(selector) : null
    return button && !button.matches(':disabled, [aria-disabled="true"], .is-disabled')
      ? button.closest<HTMLElement>('.ts-glass-toolbar') ?? button : null
  }
  const animate = (button: HTMLElement, down: boolean) => {
    const current = getComputedStyle(button).scale
    animations.get(button)?.cancel()
    button.classList.toggle('ts-is-pressed', down)
    if (reducedMotion()) return
    const frames = down ? [{ scale: current === 'none' ? '1' : current }, { scale: '.96' }]
      : [{ scale: current === 'none' ? '.96' : current }, { scale: '1.018', offset: .55 }, { scale: '1' }]
    const animation = button.animate(frames, { duration: down ? 120 : 360, easing: down ? 'cubic-bezier(.2,.8,.2,1)' : 'cubic-bezier(.22,.7,.3,1)', fill: 'forwards' })
    animations.set(button, animation)
    if (!down) animation.onfinish = () => { animation.cancel(); animations.delete(button) }
  }
  const release = (key: number | string) => {
    const button = pressed.get(key)
    if (!button) return
    pressed.delete(key)
    if (![...pressed.values()].includes(button)) animate(button, false)
  }
  document.addEventListener('pointerdown', event => {
    if (event.button !== 0 || !event.isPrimary) return
    const button = control(event.target)
    if (button) { pressed.set(event.pointerId, button); animate(button, true) }
  }, true)
  document.addEventListener('pointerup', event => release(event.pointerId), true)
  document.addEventListener('pointercancel', event => release(event.pointerId), true)
  document.addEventListener('keydown', event => {
    if (event.repeat || !['Enter', ' '].includes(event.key)) return
    const button = control(event.target)
    if (button) { pressed.set(event.key, button); animate(button, true) }
  }, true)
  document.addEventListener('keyup', event => release(event.key), true)
  const releaseAll = () => [...pressed.keys()].forEach(release)
  window.addEventListener('blur', releaseAll)
  document.addEventListener('visibilitychange', () => { if (document.hidden) releaseAll() })
  document.addEventListener('focusout', () => { release('Enter'); release(' ') })
}
