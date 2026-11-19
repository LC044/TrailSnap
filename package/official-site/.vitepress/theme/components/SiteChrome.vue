<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useData } from 'vitepress'

const props = withDefaults(defineProps<{ current?: 'download' | 'cli' | '' }>(), { current: '' })
const { isDark } = useData()
const menuOpen = ref(false)
const scrolled = ref(false)
const themeLabel = computed(() => (isDark.value ? '切换浅色模式' : '切换深色模式'))
let onScroll: (() => void) | undefined
let onKeydown: ((event: KeyboardEvent) => void) | undefined
let onResize: (() => void) | undefined

function closeMenu() {
  if (typeof document !== 'undefined') document.body.style.overflow = ''
  menuOpen.value = false
}

function toggleTheme(event: MouseEvent) {
  const next = !isDark.value
  const doc = document as Document & { startViewTransition?: (cb: () => Promise<void> | void) => void }
  if (!doc.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    isDark.value = next
    return
  }
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  document.documentElement.style.setProperty('--theme-x', `${rect.left + rect.width / 2}px`)
  document.documentElement.style.setProperty('--theme-y', `${rect.top + rect.height / 2}px`)
  doc.startViewTransition(async () => {
    isDark.value = next
    await nextTick()
  })
}

watch(menuOpen, (open) => {
  if (typeof document === 'undefined') return
  document.body.style.overflow = open ? 'hidden' : ''
})

onMounted(() => {
  onScroll = () => { scrolled.value = window.scrollY > 12 }
  onKeydown = (event: KeyboardEvent) => {
    if (event.key === 'Escape' && menuOpen.value) closeMenu()
  }
  onResize = () => { if (window.innerWidth > 1000) closeMenu() }
  onScroll()
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  if (onScroll) window.removeEventListener('scroll', onScroll)
  if (onKeydown) window.removeEventListener('keydown', onKeydown)
  if (onResize) window.removeEventListener('resize', onResize)
  document.body.style.overflow = ''
})
</script>

<template>
  <div class="grain" aria-hidden="true"></div>
  <header class="site-header subpage-header" :class="{ 'is-scrolled': scrolled }">
    <div class="wrap header-inner">
      <a class="brand" href="/" aria-label="行影集首页">
        <img src="/logo.svg" alt="" width="34" height="34">
        <span class="brand-text"><strong>行影集</strong><small>TRAILSNAP</small></span>
      </a>
      <nav class="nav-links subpage-nav" aria-label="主导航">
        <a href="/" :class="{ 'is-active': props.current === '' }">首页</a>
        <a href="/download" :class="{ 'is-active': props.current === 'download' }">下载</a>
        <a href="/cli" :class="{ 'is-active': props.current === 'cli' }">CLI</a>
        <a href="/docs/guide/install">文档 <span aria-hidden="true">↗</span></a>
      </nav>
      <div class="nav-actions">
        <button class="theme-toggle" type="button" :aria-pressed="isDark" :aria-label="themeLabel" @click="toggleTheme">
          <svg class="icon-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.2A8.2 8.2 0 0 1 9.8 4 8.5 8.5 0 1 0 20 14.2Z" /></svg>
          <svg class="icon-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2" /><path d="M12 2v2.4M12 19.6V22M4.9 4.9l1.7 1.7M17.4 17.4l1.7 1.7M2 12h2.4M19.6 12H22M4.9 19.1l1.7-1.7M17.4 6.6l1.7-1.7" /></svg>
        </button>
        <a class="btn btn-primary btn-sm nav-cta" href="https://demo.trailsnap.cn" target="_blank" rel="noopener">在线体验 <span class="btn-arrow" aria-hidden="true">↗</span></a>
        <button class="menu-toggle" type="button" :aria-expanded="menuOpen" aria-controls="subpage-menu" :aria-label="menuOpen ? '关闭菜单' : '打开菜单'" @click="menuOpen = !menuOpen">
          <span></span><span></span>
        </button>
      </div>
    </div>
  </header>

  <div id="subpage-menu" class="mobile-menu" :class="{ 'is-open': menuOpen }" :aria-hidden="!menuOpen">
    <div class="mobile-menu-inner">
      <p class="mobile-menu-kicker">行影集 · TRAILSNAP</p>
      <nav aria-label="移动端主导航">
        <a href="/" @click="closeMenu"><span>01</span>首页</a>
        <a href="/download" @click="closeMenu"><span>02</span>下载行影集</a>
        <a href="/cli" @click="closeMenu"><span>03</span>命令行 CLI</a>
        <a href="/docs/guide/install" @click="closeMenu"><span>04</span>使用文档 <i aria-hidden="true">↗</i></a>
        <a href="https://demo.trailsnap.cn" target="_blank" rel="noopener" @click="closeMenu"><span>05</span>在线体验 <i aria-hidden="true">↗</i></a>
      </nav>
      <div class="mobile-menu-foot">
        <a class="btn btn-primary" href="/download" @click="closeMenu">下载行影集 <span class="btn-arrow" aria-hidden="true">↓</span></a>
      </div>
    </div>
  </div>
</template>