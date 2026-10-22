const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const source = fs.readFileSync(path.resolve(__dirname, '../../../official-site/.vitepress/theme/landing/home-motion.js'), 'utf8')

function element() {
  const properties = new Map()
  const classes = new Set()
  return {
    style: {
      setProperty: (name, value) => properties.set(name, value),
      getPropertyValue: name => properties.get(name) || '',
    },
    classList: {
      contains: name => classes.has(name),
      toggle(name, enabled) {
        if (enabled) classes.add(name)
        else classes.delete(name)
      },
      remove: name => classes.delete(name),
    },
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = value },
    addEventListener() {},
    getBoundingClientRect: () => ({ top: 81, left: 0, width: 1200, height: 900 }),
    offsetHeight: 900,
  }
}

function harness({ caption = false, emptyViewport = false } = {}) {
  const nodes = new Map()
  for (const selector of [
    '.scroll-scene', '.hero', '.hero-copy', '.hero-live',
    '.scene-progress span', '.memory-scene', '.memory-stage', '#memory-page-label',
  ]) nodes.set(selector, element())
  if (caption) nodes.set('.scene-caption', element())
  nodes.get('.scroll-scene').offsetHeight = 2300
  nodes.get('.memory-scene').offsetHeight = 2700
  const tabs = [0, 1, 2].map(index => ({
    ...element(), dataset: { memoryTab: String(index) },
  }))
  const copies = [0, 1, 2].map(index => ({
    ...element(), dataset: { memoryCopy: String(index) },
  }))
  const panels = [element(), element(), element()]
  const cards = [element(), element(), element()]
  const viewport = {
    clientWidth: 600,
    closest: () => null,
    querySelector: () => null,
  }
  const groups = {
    '.desktop-viewport': emptyViewport ? [viewport] : [],
    '[data-memory-tab]': tabs,
    '[data-memory-copy]': copies,
    '.memory-panel': panels,
    '.cap-grid article': cards,
    '.cap-heading,.cap-grid article,.start-grid article,.tools-heading,.tool-showcase,.trust-heading,.trust-grid article,.end': cards,
  }
  const root = {
    ...element(),
    querySelector: selector => nodes.get(selector) || null,
    querySelectorAll: selector => groups[selector] || [],
  }
  const listeners = new Map()
  const frames = []
  const context = {
    AbortController,
    ResizeObserver: class { observe() {} disconnect() {} },
    innerHeight: 900,
    scrollY: 0,
    requestAnimationFrame: fn => { frames.push(fn); return frames.length },
    cancelAnimationFrame() {},
    window: {
      innerWidth: 1440,
      document: { body: element() },
      matchMedia: () => ({ matches: true, addEventListener() {} }),
      addEventListener: (name, fn) => listeners.set(name, fn),
    },
  }
  vm.createContext(context)
  vm.runInContext(source.replace('export function initHome', 'function initHome'), context)
  const cleanup = context.initHome(root)
  return {
    nodes, root, tabs, panels, cards, cleanup,
    scrollToProgress(progress) {
      const memory = nodes.get('.memory-scene')
      const distance = memory.offsetHeight - nodes.get('.memory-stage').offsetHeight
      memory.getBoundingClientRect = () => ({ top: 81 - progress * distance })
      listeners.get('scroll')()
      while (frames.length) frames.shift()()
    },
  }
}

test('missing hero caption does not interrupt memory switching or card reveals', () => {
  const page = harness()
  assert.equal(page.root.classList.contains('motion-ready'), true)
  assert.notEqual(page.cards[0].style.getPropertyValue('--reveal-opacity'), '')
  for (const [progress, index] of [[0.4, 1], [0.8, 2], [0.1, 0]]) {
    page.scrollToProgress(progress)
    assert.equal(page.tabs[index].attributes['aria-selected'], 'true')
    assert.equal(page.panels[index].inert, false)
    assert.equal(page.nodes.get('#memory-page-label').textContent.startsWith(`0${index + 1}`), true)
  }
  page.cleanup()
  assert.equal(page.root.classList.contains('motion-ready'), false)
})

test('optional hero caption still receives scroll styles when present', () => {
  const page = harness({ caption: true })
  assert.notEqual(page.nodes.get('.scene-caption').style.opacity, undefined)
  page.scrollToProgress(0.8)
  assert.equal(page.tabs[2].attributes['aria-selected'], 'true')
  page.cleanup()
})

test('preview without an iframe does not prevent scroll initialization', () => {
  const page = harness({ emptyViewport: true })
  page.scrollToProgress(0.4)
  assert.equal(page.tabs[1].attributes['aria-selected'], 'true')
  page.cleanup()
})
