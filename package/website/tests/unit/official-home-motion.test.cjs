const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const source = fs.readFileSync(path.resolve(__dirname, '../../../official-site/.vitepress/theme/landing/home-motion.js'), 'utf8')

function element(extra = {}) {
  const properties = new Map()
  const classes = new Set()
  return {
    style: {
      setProperty: (name, value) => properties.set(name, String(value)),
      getPropertyValue: name => properties.get(name) || '',
    },
    classList: {
      contains: name => classes.has(name),
      add: name => classes.add(name),
      remove: (...names) => names.forEach(name => classes.delete(name)),
      toggle(name, enabled) {
        if (enabled) classes.add(name)
        else classes.delete(name)
      },
    },
    attributes: {},
    dataset: {},
    setAttribute(name, value) { this.attributes[name] = value },
    addEventListener() {},
    removeEventListener() {},
    getBoundingClientRect: () => ({ top: 0, left: 0, width: 1200, height: 900 }),
    offsetHeight: 900,
    clientWidth: 600,
    clientHeight: 400,
    querySelector: () => null,
    querySelectorAll: () => [],
    closest: () => null,
    ...extra,
  }
}

function harness({ reduced = false, pinned = true, viewports = [], innerWidth = 1440 } = {}) {
  const start = 1000
  const distance = 1800
  const memoryScene = element({ offsetHeight: 2700 })
  const memoryStage = element({ offsetHeight: 900 })
  memoryScene.getBoundingClientRect = () => ({ top: start - context.win.scrollY, left: 0, width: 1440, height: 900 })

  const revealElements = [element(), element()]
  const nodes = new Map([
    ['.memory-scene', memoryScene],
    ['.memory-stage', memoryStage],
  ])
  const root = element({
    querySelector: selector => nodes.get(selector) || null,
    querySelectorAll: selector => {
      if (selector === '[data-reveal]') return revealElements
      if (selector === '.desktop-viewport') return viewports
      return []
    },
  })

  const listeners = new Map()
  const frames = []
  const observerInstances = []
  const calls = []
  const matchMedia = query => {
    const reducedQuery = query.includes('prefers-reduced-motion: reduce')
    const pinnedQuery = query.includes('min-width: 1001px')
    return {
      matches: reducedQuery ? reduced : pinnedQuery ? pinned : false,
      addEventListener() {},
      removeEventListener() {},
    }
  }

  class IntersectionObserverMock {
    constructor(callback) {
      this.callback = callback
      this.observed = []
      observerInstances.push(this)
    }
    observe(target) { this.observed.push(target) }
    unobserve() {}
    disconnect() {}
  }

  const context = {
    AbortController,
    ResizeObserver: class { observe() {} disconnect() {} },
    IntersectionObserver: IntersectionObserverMock,
    console,
    requestAnimationFrame: fn => { frames.push(fn); return frames.length },
    cancelAnimationFrame() {},
    setTimeout: () => 0,
    clearTimeout() {},
    document: {
      body: element(),
      documentElement: { scrollHeight: 6000 },
    },
    window: {
      innerWidth,
      innerHeight: 900,
      scrollY: 0,
      scrollTo(options) { context.lastScrollTo = options },
      addEventListener: (name, fn) => listeners.set(name, fn),
      removeEventListener() {},
      matchMedia,
      IntersectionObserver: IntersectionObserverMock,
      setTimeout: () => 0,
      clearTimeout() {},
    },
  }
  context.win = context.window

  vm.createContext(context)
  vm.runInContext(source.replace('export function initHome', 'function initHome'), context)
  const api = context.initHome(root, { setMemoryPage: index => calls.push(index) })
  const flush = () => { while (frames.length) frames.shift()() }

  return {
    api,
    calls,
    context,
    flush,
    listeners,
    memoryScene,
    observerInstances,
    revealElements,
    root,
    start,
    distance,
    scrollToProgress(progress) {
      context.window.scrollY = start + progress * distance
      listeners.get('scroll')?.()
      flush()
    },
  }
}

test('memory scene calls setMemoryPage while scrolling and resets on destroy', () => {
  const page = harness()
  page.flush()

  page.scrollToProgress(0.4)
  page.scrollToProgress(0.8)
  page.scrollToProgress(0.1)
  assert.deepEqual(page.calls, [1, 2, 0])

  page.api.chooseMemory(2)
  assert.deepEqual(page.calls, [1, 2, 0, 2])
  assert.equal(page.context.lastScrollTo.behavior, 'smooth')
  assert.equal(page.context.lastScrollTo.top > page.start, true)

  page.api.destroy()
  assert.equal(page.root.classList.contains('reveal-ready'), false)
})

test('reveal elements are marked when they enter the viewport', () => {
  const page = harness()
  assert.equal(page.root.classList.contains('reveal-ready'), true)

  const revealObserver = page.observerInstances[0]
  assert.equal(revealObserver.observed.length, 2)
  revealObserver.callback([{ isIntersecting: true, target: page.revealElements[0] }])
  revealObserver.callback([{ isIntersecting: false, target: page.revealElements[1] }])
  assert.equal(page.revealElements[0].classList.contains('is-in'), true)
  assert.equal(page.revealElements[1].classList.contains('is-in'), false)

  page.api.destroy()
})

test('reduced motion skips reveal setup', () => {
  const page = harness({ reduced: true })
  assert.equal(page.root.classList.contains('reveal-ready'), false)
  assert.equal(page.observerInstances.length, 0)
  page.api.destroy()
})

test('desktop preview frames scale to the native 1440 layout and handle empty viewports', () => {
  const frame = element({ hidden: false, id: 'live-home' })
  const viewport = element({
    clientWidth: 600,
    clientHeight: 400,
    querySelectorAll: selector => selector === 'iframe' ? [frame] : [],
  })
  const page = harness({ viewports: [viewport] })

  assert.equal(frame.style.width, '1440px')
  assert.equal(frame.style.height, '960px')
  assert.equal(String(frame.style.transform).startsWith('scale(0.4166'), true)
  assert.equal(frame.style.getPropertyValue('--preview-scale'), String(600 / 1440))

  const empty = element({ clientWidth: 0, clientHeight: 0, querySelectorAll: () => [] })
  const emptyPage = harness({ viewports: [empty] })
  assert.equal(emptyPage.calls.length, 0)
  assert.equal(emptyPage.root.classList.contains('reveal-ready'), true)

  page.api.destroy()
  emptyPage.api.destroy()
})

test('chooseMemory scrolls the visual into view when the page is not pinned', () => {
  const visual = element({ scrollIntoView() { visual.scrolled = true } })
  const page = harness({ pinned: false })
  page.memoryScene.querySelector = selector => selector === '.memory-visual' ? visual : null

  page.api.chooseMemory(1)
  assert.deepEqual(page.calls, [1])
  assert.equal(visual.scrolled, true)

  page.api.destroy()
})

test('mobile inline previews keep the PC 1440 canvas and its proportions', () => {
  const frame = element({ hidden: false, id: 'live-home' })
  const viewport = element({
    clientWidth: 360,
    clientHeight: 225,
    querySelectorAll: selector => selector === 'iframe' ? [frame] : [],
  })
  const page = harness({ innerWidth: 390, viewports: [viewport] })

  assert.equal(frame.style.width, '1440px')
  assert.equal(frame.style.height, '900px')
  assert.equal(frame.style.transform, 'scale(0.25)')
  assert.equal(frame.style.getPropertyValue('--preview-scale'), '0.25')

  page.api.destroy()
})

test('expanded mobile preview switches to its native mobile layout for touch', () => {
  const frame = element({ hidden: false, id: 'live-home' })
  const viewport = element({
    clientWidth: 360,
    clientHeight: 640,
    closest: selector => selector === '.expanded' ? {} : null,
    querySelectorAll: selector => selector === 'iframe' ? [frame] : [],
  })
  const page = harness({ innerWidth: 390, viewports: [viewport] })

  assert.equal(frame.style.width, '100%')
  assert.equal(frame.style.height, '100%')
  assert.equal(frame.style.transform, 'none')
  assert.equal(frame.style.getPropertyValue('--preview-scale'), '1')

  page.api.destroy()
})