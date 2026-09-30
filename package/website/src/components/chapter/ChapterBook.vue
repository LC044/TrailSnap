<template>
  <div class="diary-book chapter-book" :class="{ 'book-mobile-right': mobileRight, 'book-animating': animating }" :aria-busy="animating">
    <nav v-if="!singlePage" class="book-side-tabs" aria-label="纸页选择">
      <button :disabled="animating" :aria-pressed="!mobileRight" @click="mobileRight = false">影像页</button>
      <button :disabled="animating" :aria-pressed="mobileRight" @click="mobileRight = true">文字页</button>
    </nav>
    <div ref="stage" class="book-stage">
      <div ref="live" class="diary-spread book-live" :class="{ 'diary-cover': cover }" :inert="animating || undefined"><slot /></div>
      <div ref="layer" class="book-animation" aria-hidden="true" inert />
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
// The typed source also includes the renderer lifecycle fix in our pnpm patch.
import { PageFlip } from 'page-flip/src/PageFlip'
import { SizeType } from 'page-flip/src/Settings'
const props = withDefaults(defineProps<{ pageKey: string | number; direction?: number; cover?: boolean; title?: string; singlePage?: boolean; ready?: boolean; duration?: number; portrait?: boolean }>(), { direction: 1, cover: false, title: '我的影像日记', singlePage: false, ready: true, duration: 900, portrait: false })
const emit = defineEmits<{ busy: [value: boolean] }>()
const stage = ref<HTMLElement>(), live = ref<HTMLElement>(), layer = ref<HTMLElement>()
const animating = ref(false), mobileRight = ref(false)
let engine: PageFlip | undefined, sequence = 0, finishTimer: ReturnType<typeof setTimeout> | undefined
let startTimer: ReturnType<typeof setTimeout> | undefined, observer: ResizeObserver | undefined
let contentReady: (() => void) | undefined
const imageTimers = new Set<ReturnType<typeof setTimeout>>()
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
function busy(value: boolean) { animating.value = value; emit('busy', value) }
function clearEngine() { clearTimeout(startTimer); clearTimeout(finishTimer); engine?.destroy(); engine = undefined; layer.value?.replaceChildren() }
function finish() { clearEngine(); busy(false) }
async function prepareContent() {
  if (!props.ready) await new Promise<void>((resolve) => { contentReady = resolve })
  await nextTick()
  // Lazy images in the hidden target page must load before it becomes a paper surface.
  await Promise.all(Array.from(live.value?.querySelectorAll('img') || []).map((image) => new Promise<void>((resolve) => {
    image.loading = 'eager'
    const timer = setTimeout(() => {
      imageTimers.delete(timer)
      image.dispatchEvent(new Event('error'))
      resolve()
    }, 5000)
    imageTimers.add(timer)
    void image.decode().catch(() => {}).finally(() => { clearTimeout(timer); imageTimers.delete(timer); resolve() })
  })))
  await nextTick()
}
watch(() => props.ready, (ready) => { if (ready) { contentReady?.(); contentReady = undefined } })
function snapshot(): HTMLElement[] {
  return Array.from(live.value?.children || []).filter((element) => getComputedStyle(element).display !== 'none').map((element) => {
    const clone = element.cloneNode(true) as HTMLElement
    clone.classList.remove('is-mobile-hidden')
    clone.querySelectorAll('[id]').forEach((node) => node.removeAttribute('id'))
    // Preserve the reading position when a long entry is turned over.
    const originals = element.querySelectorAll('.diary-page-content')
    clone.querySelectorAll('.diary-page-content').forEach((node, index) => { (node as HTMLElement).dataset.bookScroll = String(originals[index]?.scrollTop || 0) })
    return clone
  })
}
function hardCover(): HTMLElement {
  const page = document.createElement('section')
  page.className = 'book-hard-cover'
  page.dataset.density = 'hard'
  const label = document.createElement('p'); label.textContent = '行影集 · 影像日记'
  const title = document.createElement('h2'); title.textContent = props.title
  const hint = document.createElement('p'); hint.textContent = '把日子珍藏在这一册'
  const content = document.createElement('div')
  content.className = 'book-cover-content'
  content.append(label, title, hint)
  page.append(content)
  return page
}
function animate(before: HTMLElement[], after: HTMLElement[], opening = false, direction = props.direction) {
  if (!stage.value || !layer.value || !after.length) { finish(); return }
  clearEngine()
  const portrait = props.portrait || window.matchMedia('(max-width: 767px)').matches
  const bounds = stage.value.getBoundingClientRect()
  const mount = document.createElement('div')
  mount.style.width = '100%'; mount.style.height = '100%'
  layer.value.append(mount)
  let pages: HTMLElement[], startPage: number
  if (opening) { pages = [hardCover(), ...after]; startPage = 0 }
  else if (direction >= 0) { pages = [...before, ...after]; startPage = 0 }
  else { pages = [...after, ...before]; startPage = after.length }
  engine = new PageFlip(mount, {
    width: bounds.width / (portrait ? 1 : 2), height: bounds.height,
    size: SizeType.FIXED, usePortrait: portrait, autoSize: false,
    showCover: opening, startPage, flippingTime: opening ? Math.max(600, props.duration) : props.duration,
    drawShadow: true, maxShadowOpacity: .28, useMouseEvents: false,
    showPageCorners: false, mobileScrollSupport: false,
  })
  let started = false
  engine.on('changeState', (event: { data: string }) => {
    if (event.data === 'flipping') started = true
    if (started && event.data === 'read') finish()
  })
  engine.loadFromHTML(pages)
  mount.querySelectorAll<HTMLElement>('[data-book-scroll]').forEach((node) => { node.scrollTop = Number(node.dataset.bookScroll) })
  busy(true)
  startTimer = setTimeout(() => {
    if (opening || direction >= 0) engine?.flipNext('bottom')
    else engine?.flipPrev('bottom')
    finishTimer = setTimeout(finish, opening ? 1400 : 1200)
  }, opening ? 240 : 40)
}
async function turn(direction = props.direction) {
  if (reducedMotion()) { sequence++; finish(); return }
  const request = ++sequence
  contentReady?.(); contentReady = undefined
  const previous = snapshot()
  // Show the old spread while Vue prepares the next interactive page.
  clearEngine()
  if (layer.value) {
    const placeholder = document.createElement('div'); placeholder.className = 'diary-spread'
    previous.forEach((page) => placeholder.append(page.cloneNode(true)))
    layer.value.append(placeholder)
  }
  busy(true)
  await nextTick()
  await prepareContent()
  if (request !== sequence) return
  animate(previous, snapshot(), false, direction)
}
watch(() => props.pageKey, () => turn(), { flush: 'pre' })
watch(mobileRight, (value) => turn(value ? 1 : -1), { flush: 'pre' })
onMounted(async () => {
  await nextTick()
  observer = new ResizeObserver(() => { if (engine) { sequence++; finish() } })
  if (stage.value) observer.observe(stage.value)
  if (!reducedMotion()) {
    const request = ++sequence
    const placeholder = document.createElement('div'); placeholder.className = 'diary-spread'
    if (!props.portrait && !window.matchMedia('(max-width: 767px)').matches) placeholder.append(document.createElement('div'))
    placeholder.append(hardCover())
    layer.value?.append(placeholder)
    busy(true)
    startTimer = setTimeout(async () => {
      await prepareContent()
      if (request === sequence) animate([], snapshot(), true)
    }, 180)
  }
})
onBeforeUnmount(() => { sequence++; contentReady?.(); imageTimers.forEach(clearTimeout); observer?.disconnect(); clearEngine() })
</script>

<style src="./chapterBook.css" />
